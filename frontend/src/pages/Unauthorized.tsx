/**
 * pages/Unauthorized.tsx
 * -----------------------
 * Shown when a user tries to access a route not permitted for their role.
 * Academic enterprise presentation.
 */

import { Link } from 'react-router-dom';
import { ShieldX, ArrowLeft } from 'lucide-react';
import { useAuth } from '@/auth/useAuth';
import type { UserRole } from '@/auth/auth.types';

const roleHome: Record<UserRole, string> = {
  SUPER_ADMIN: '/super-admin',
  ADMIN: '/admin',
  FACULTY: '/faculty',
  STUDENT: '/student',
};

export function Unauthorized() {
  const { user } = useAuth();
  const home = user ? roleHome[user.role] : '/login';

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200/90 shadow-card p-8 text-center">
        <div className="w-12 h-12 rounded-xl bg-rose-50 border border-rose-200/80 text-rose-600 flex items-center justify-center mx-auto mb-4">
          <ShieldX size={24} />
        </div>
        <h1 className="text-xl font-bold text-slate-900 tracking-tight mb-2">Access Restricted</h1>
        <p className="text-slate-500 text-xs leading-relaxed mb-6 max-w-sm mx-auto">
          You do not have the required institutional authorization to view this module.
          {user && ` Your current authenticated role is ${user.role}.`}
        </p>
        <Link
          to={home}
          className="inline-flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white font-semibold px-4 py-2.5 rounded-lg text-xs uppercase tracking-wider transition-colors shadow-xs focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2"
        >
          <ArrowLeft size={14} />
          <span>Return to Dashboard</span>
        </Link>
      </div>
    </div>
  );
}
