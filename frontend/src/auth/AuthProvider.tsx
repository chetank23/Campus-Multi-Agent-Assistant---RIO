/**
 * auth/AuthProvider.tsx
 * ----------------------
 * Single source of truth for authentication state.
 *
 * Strategy:
 * 1. On mount, attempt a silent token refresh via the httpOnly refresh_token cookie.
 *    If it succeeds the user is still logged in (session restoration after refresh).
 * 2. On login, call POST /auth/login, store the access_token in memory, then
 *    fetch the current user from GET /auth/me.
 * 3. On logout, call POST /auth/logout (which clears the httpOnly cookie) and
 *    wipe in-memory state.
 * 4. When the Axios interceptor fires a session-expired event, clear state so
 *    the router redirects to /login.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { apiGetMe, apiLogin, apiLogout, apiRefreshToken } from '@/api/auth';
import { setAccessToken } from '@/api/client';
import { AuthContext } from './AuthContext';
import type { AuthContextValue, LoginRequest, UserResponse } from './auth.types';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true); // true until initial refresh resolves

  // ── Session restoration ───────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      try {
        // Attempt to get a new access token using the httpOnly refresh cookie
        const { access_token } = await apiRefreshToken();
        setAccessToken(access_token);
        const me = await apiGetMe();
        if (!cancelled) setUser(me);
      } catch {
        // No valid session — user will need to log in
        setAccessToken(null);
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    restoreSession();
    return () => { cancelled = true; };
  }, []);

  // ── Session expiry event from Axios interceptor ───────────────────────────
  useEffect(() => {
    function handleExpiry() {
      setUser(null);
      setAccessToken(null);
    }
    window.addEventListener('auth:session-expired', handleExpiry);
    return () => window.removeEventListener('auth:session-expired', handleExpiry);
  }, []);

  // ── Login ─────────────────────────────────────────────────────────────────
  const login = useCallback(async (credentials: LoginRequest) => {
    const { access_token } = await apiLogin(credentials);
    setAccessToken(access_token);
    const me = await apiGetMe();
    setUser(me);
  }, []);

  // ── Logout ────────────────────────────────────────────────────────────────
  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const value: AuthContextValue = {
    user,
    isAuthenticated: user !== null,
    isLoading,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
