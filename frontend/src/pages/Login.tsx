/**
 * pages/Login.tsx
 * ----------------
 * Login page. Submits to POST /auth/login via the real backend.
 * On success, redirects the user to their role-appropriate dashboard.
 * If already authenticated, redirects immediately.
 */

import { useState, type FormEvent } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useAuth, extractApiError } from '@/auth/AuthProvider';
import type { UserRole } from '@/auth/auth.types';

const roleHome: Record<UserRole, string> = {
  ADMIN: '/admin',
  FACULTY: '/faculty',
  STUDENT: '/student',
};

export function Login() {
  const { isAuthenticated, isLoading, login, user } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Already logged in — redirect immediately
  if (!isLoading && isAuthenticated && user) {
    return <Navigate to={roleHome[user.role]} replace />;
  }

  // Still checking session
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!email.trim() || !password) {
      setError('Email and password are required.');
      return;
    }

    setSubmitting(true);
    try {
      await login({ email: email.trim(), password });
      // After login, user is set in context — get fresh value to redirect
      // We navigate to a role-detection route that reads from context
      navigate('/app', { replace: true });
    } catch (err) {
      setError(extractApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col justify-center items-center p-4 selection:bg-primary-900 selection:text-white relative overflow-hidden">
      {/* Subtle academic background accent */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-slate-950 pointer-events-none" />

      <div className="w-full max-w-sm relative z-10">
        {/* Academic Card */}
        <div className="bg-white rounded-2xl shadow-modal border border-slate-200/90 p-8">
          {/* Institution Brand */}
          <div className="flex flex-col items-center mb-7">
            <div className="w-12 h-12 rounded-xl bg-primary-700 flex items-center justify-center shadow-card mb-3.5 border border-primary-600/30">
              <span className="text-white text-xl font-bold tracking-wider">R</span>
            </div>
            <div className="flex items-center gap-1.5 mb-1">
              <h1 className="text-xl font-bold tracking-tight text-slate-900">RIO-MJP</h1>
              <span className="text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded border border-slate-200">
                ERP
              </span>
            </div>
            <p className="text-xs text-slate-500 text-center">
              Campus Intelligence & Timetable Management
            </p>
          </div>

          {/* Error Alert */}
          {error && (
            <div className="mb-5 rounded-lg bg-rose-50 border border-rose-200/90 px-3.5 py-2.5 text-xs text-rose-700 font-medium leading-relaxed" role="alert">
              {error}
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
                University Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-3.5 py-2 rounded-lg border border-slate-300 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-600 focus:border-primary-600 transition-colors"
                placeholder="user@university.edu"
                disabled={submitting}
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full px-3.5 py-2 rounded-lg border border-slate-300 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-600 focus:border-primary-600 transition-colors"
                placeholder="••••••••"
                disabled={submitting}
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-primary-600 hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-lg transition-colors text-xs uppercase tracking-wider shadow-xs focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2"
            >
              {submitting ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Authenticating…
                </span>
              ) : (
                'Sign In to Portal'
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-[11px] text-slate-400">
            Authorized academic personnel only. Contact campus administrator for access.
          </p>
        </div>

        <p className="text-center text-xs text-slate-400 mt-5">
          RIO-MJP Academic Information System • ERP
        </p>
      </div>
    </div>
  );
}
