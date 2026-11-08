import { useContext } from 'react';
import type { AxiosError } from 'axios';
import { AuthContext } from './AuthContext';
import type { AuthContextValue } from './auth.types';

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

export function extractApiError(err: unknown): string {
  const axiosErr = err as AxiosError<{ detail: unknown }>;
  const detail = axiosErr?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => (d as { msg: string }).msg).join(', ');
  return 'An unexpected error occurred. Please try again.';
}
