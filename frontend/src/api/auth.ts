/**
 * api/auth.ts
 * -----------
 * Auth-specific API calls that map to the ACTUAL backend endpoints discovered
 * in backend/routes/auth.py:
 *
 *   POST /auth/login   → { access_token, token_type }  + sets httpOnly cookie
 *   POST /auth/refresh → { access_token, token_type }  uses httpOnly cookie
 *   POST /auth/logout  → clears httpOnly cookie
 *   GET  /auth/me      → { id, name, email, role, department_id }
 */

import { apiClient } from './client';
import type { LoginRequest, TokenResponse, UserResponse } from '@/auth/auth.types';

export async function apiLogin(credentials: LoginRequest): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>('/auth/login', credentials);
  return data;
}

export async function apiRefreshToken(): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>('/auth/refresh');
  return data;
}

export async function apiLogout(): Promise<void> {
  await apiClient.post('/auth/logout');
}

export async function apiGetMe(): Promise<UserResponse> {
  const { data } = await apiClient.get<UserResponse>('/auth/me');
  return data;
}
