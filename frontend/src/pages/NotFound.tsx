/**
 * pages/NotFound.tsx
 * -------------------
 * Generic 404 page for nonexistent campus routes.
 * Academic enterprise styling.
 */

import { Link } from 'react-router-dom';
import { FileQuestion, ArrowLeft } from 'lucide-react';
import { useAuth } from '@/auth/AuthProvider';
import type { UserRole } from '@/auth/auth.types';

const roleHome: Record<UserRole, string> = {
  ADMIN: '/admin',
  FACULTY: '/faculty',
  STUDENT: '/student',
};

export function NotFound() {
  const { user } = useAuth();
  const home = user ? roleHome[user.role] : '/login';

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200/90 shadow-card p-8 text-center">
        <div className="w-12 h-12 rounded-xl bg-slate-100 border border-slate-200 text-slate-500 flex items-center justify-center mx-auto mb-4">
          <FileQuestion size={24} />
        </div>
        <p className="text-3xl font-black text-slate-300 font-tabular mb-1">404</p>
        <h1 className="text-xl font-bold text-slate-900 tracking-tight mb-2">Page Not Found</h1>
        <p className="text-slate-500 text-xs leading-relaxed mb-6 max-w-sm mx-auto">
          The requested campus resource or navigation route does not exist or has been relocated.
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
