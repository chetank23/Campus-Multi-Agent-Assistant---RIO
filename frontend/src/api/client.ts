/**
 * api/client.ts
 * -------------
 * Single central Axios instance.
 *
 * During development the Vite dev-server proxies `/api/*` → backend,
 * so cookies are on the same origin and CORS wildcard+credentials issues
 * are avoided entirely.  The base URL is therefore just `/api`.
 *
 * The Authorization header is injected by the request interceptor using the
 * access token stored in memory (set by AuthProvider).  The token is never
 * written to localStorage to reduce XSS risk.
 */

import axios, {
  type AxiosError,
  type InternalAxiosRequestConfig,
} from 'axios';

// In-memory token store — the only source of truth.
// Exported setters so AuthProvider can update them without circular imports.
let _accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  _accessToken = token;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

export const apiClient = axios.create({
  // All API traffic goes through the Vite proxy at /api → backend root
  baseURL: '/api',
  withCredentials: true, // send the httpOnly refresh_token cookie
  headers: {
    'Content-Type': 'application/json',
  },
});

// ── Request interceptor ───────────────────────────────────────────────────────
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (_accessToken) {
    config.headers['Authorization'] = `Bearer ${_accessToken}`;
  }
  return config;
});

// ── Response interceptor ─────────────────────────────────────────────────────
// On 401: attempt a silent token refresh via the httpOnly cookie, then retry.
// If the refresh also fails, clear the token so AuthProvider redirects to login.
let _isRefreshing = false;
let _refreshQueue: Array<{
  resolve: (value: string) => void;
  reject: (reason: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null) {
  _refreshQueue.forEach(({ resolve, reject }) =>
    error ? reject(error) : resolve(token as string)
  );
  _refreshQueue = [];
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // Only attempt refresh on 401 for non-auth endpoints
    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/auth/login') &&
      !originalRequest.url?.includes('/auth/refresh')
    ) {
      if (_isRefreshing) {
        // Queue the request until refresh completes
        return new Promise<string>((resolve, reject) => {
          _refreshQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers['Authorization'] = `Bearer ${token}`;
            return apiClient(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      _isRefreshing = true;

      try {
        const { data } = await apiClient.post<{ access_token: string }>(
          '/auth/refresh'
        );
        const newToken = data.access_token;
        setAccessToken(newToken);
        processQueue(null, newToken);
        originalRequest.headers['Authorization'] = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        setAccessToken(null);
        // Dispatch a custom event so AuthProvider can react
        window.dispatchEvent(new CustomEvent('auth:session-expired'));
        return Promise.reject(refreshError);
      } finally {
        _isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);
