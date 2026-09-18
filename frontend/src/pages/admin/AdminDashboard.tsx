/**
 * pages/admin/AdminDashboard.tsx
 * --------------------------------
 * Admin dashboard. Shows authenticated user identity and system connection status.
 * Does NOT display invented metrics — only data actually available from the backend.
 */

import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, XCircle, User, Mail, Building2, Shield } from 'lucide-react';
import { apiGetMe } from '@/api/auth';
import { useAuth } from '@/auth/AuthProvider';

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 px-5 py-4">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">{label}</p>
      <p className="text-lg font-semibold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export function AdminDashboard() {
  const { user: ctxUser } = useAuth();

  // Verify backend connection by calling /auth/me through React Query
  const { data: me, isLoading, isError, error } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: apiGetMe,
    staleTime: 60_000,
    retry: 1,
  });

  const user = me ?? ctxUser;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-xl font-bold text-gray-900">Admin Dashboard</h2>
        <p className="text-sm text-gray-500 mt-1">
          Overview of your administrative account and system status.
        </p>
      </div>

      {/* System status banner */}
      <div
        className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium border ${
          isError
            ? 'bg-red-50 border-red-200 text-red-700'
            : isLoading
            ? 'bg-yellow-50 border-yellow-200 text-yellow-700'
            : 'bg-emerald-50 border-emerald-200 text-emerald-700'
        }`}
      >
        {isError ? (
          <XCircle size={18} />
        ) : isLoading ? (
          <div className="w-4 h-4 border-2 border-yellow-500 border-t-transparent rounded-full animate-spin" />
        ) : (
          <CheckCircle2 size={18} />
        )}
        <span>
          {isError
            ? `Backend connection failed: ${(error as Error)?.message ?? 'Unknown error'}`
            : isLoading
            ? 'Verifying backend connection…'
            : 'Backend API connected and responding.'}
        </span>
      </div>

      {/* Account info */}
      {user && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-50">
            <h3 className="text-sm font-semibold text-gray-800">Your Account</h3>
          </div>
          <div className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-primary-50 flex items-center justify-center shrink-0 mt-0.5">
                <User size={15} className="text-primary-600" />
              </div>
              <div>
                <p className="text-xs text-gray-400 font-medium">Full name</p>
                <p className="text-sm font-semibold text-gray-900">{user.name}</p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-primary-50 flex items-center justify-center shrink-0 mt-0.5">
                <Mail size={15} className="text-primary-600" />
              </div>
              <div>
                <p className="text-xs text-gray-400 font-medium">Email</p>
                <p className="text-sm font-semibold text-gray-900 break-all">{user.email}</p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-violet-50 flex items-center justify-center shrink-0 mt-0.5">
                <Shield size={15} className="text-violet-600" />
              </div>
              <div>
                <p className="text-xs text-gray-400 font-medium">Role</p>
                <p className="text-sm font-semibold text-gray-900">{user.role}</p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-primary-50 flex items-center justify-center shrink-0 mt-0.5">
                <Building2 size={15} className="text-primary-600" />
              </div>
              <div>
                <p className="text-xs text-gray-400 font-medium">Department ID</p>
                <p className="text-sm font-semibold text-gray-900">
                  {user.department_id ?? 'All departments (Admin)'}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Quick-look tiles — sourced from actual context data only */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="User ID" value={`#${user?.id ?? '—'}`} sub="Database record" />
        <StatCard label="Role" value={user?.role ?? '—'} sub="System role" />
        <StatCard label="Stage" value="6A" sub="Frontend foundation" />
        <StatCard label="Backend" value={isError ? 'Offline' : isLoading ? '…' : 'Online'} sub="API status" />
      </div>

      {/* Future module placeholder notice */}
      <div className="bg-primary-50 border border-primary-100 rounded-xl px-5 py-4 text-sm text-primary-700">
        <p className="font-semibold mb-1">Stage 6A — Foundation only</p>
        <p className="text-primary-600 text-xs leading-relaxed">
          Full CRUD management panels for Academic, Faculty, Students, Courses, Rooms,
          Timetable, Resources, and Audit Logs will be available in Stage 6B+.
          Sidebar items marked "Soon" are navigation placeholders only.
        </p>
      </div>
    </div>
  );
}
