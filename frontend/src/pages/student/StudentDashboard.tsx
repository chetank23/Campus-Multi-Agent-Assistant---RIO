/**
 * pages/student/StudentDashboard.tsx
 * -------------------------------------
 * Student dashboard. Shows identity from /auth/me and explains what's coming.
 */

import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, XCircle, User, Mail, Building2, GraduationCap } from 'lucide-react';
import { apiGetMe } from '@/api/auth';
import { useAuth } from '@/auth/AuthProvider';

export function StudentDashboard() {
  const { user: ctxUser } = useAuth();

  const { data: me, isLoading, isError, error } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: apiGetMe,
    staleTime: 60_000,
    retry: 1,
  });

  const user = me ?? ctxUser;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-xl font-bold text-gray-900">
          Hello, {user?.name?.split(' ')[0] ?? 'Student'} 👋
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          Your account information is shown below. Timetable views will be available in Stage 6B.
        </p>
      </div>

      {/* API status */}
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
            ? `Backend error: ${(error as Error)?.message}`
            : isLoading
            ? 'Loading account…'
            : 'Connected to Campus AI backend.'}
        </span>
      </div>

      {user && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-50">
            <h3 className="text-sm font-semibold text-gray-800">Student Account</h3>
          </div>
          <div className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center shrink-0">
                <User size={15} className="text-emerald-600" />
              </div>
              <div>
                <p className="text-xs text-gray-400">Name</p>
                <p className="text-sm font-semibold text-gray-900">{user.name}</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center shrink-0">
                <Mail size={15} className="text-emerald-600" />
              </div>
              <div>
                <p className="text-xs text-gray-400">Email</p>
                <p className="text-sm font-semibold text-gray-900 break-all">{user.email}</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center shrink-0">
                <GraduationCap size={15} className="text-emerald-600" />
              </div>
              <div>
                <p className="text-xs text-gray-400">Role</p>
                <p className="text-sm font-semibold text-gray-900">{user.role}</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center shrink-0">
                <Building2 size={15} className="text-emerald-600" />
              </div>
              <div>
                <p className="text-xs text-gray-400">Department ID</p>
                <p className="text-sm font-semibold text-gray-900">
                  {user.department_id ?? 'Not assigned'}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="bg-emerald-50 border border-emerald-100 rounded-xl px-5 py-4 text-sm text-emerald-700">
        <p className="font-semibold mb-1">My Timetable — Coming Soon</p>
        <p className="text-emerald-600 text-xs leading-relaxed">
          Your personal class schedule will be viewable here in Stage 6B once the timetable
          viewing interface is implemented.
        </p>
      </div>
    </div>
  );
}
