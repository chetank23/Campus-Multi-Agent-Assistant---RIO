/**
 * pages/Unauthorized.tsx
 * -----------------------
 * Shown when a user tries to access a route not permitted for their role.
 */

import { Link } from 'react-router-dom';
import { ShieldX } from 'lucide-react';
import { useAuth } from '@/auth/AuthProvider';
import type { UserRole } from '@/auth/auth.types';

const roleHome: Record<UserRole, string> = {
  ADMIN: '/admin',
  FACULTY: '/faculty',
  STUDENT: '/student',
};

export function Unauthorized() {
  const { user } = useAuth();
  const home = user ? roleHome[user.role] : '/login';

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="text-center max-w-sm">
        <div className="w-16 h-16 rounded-2xl bg-red-100 flex items-center justify-center mx-auto mb-5">
          <ShieldX className="text-red-500" size={32} />
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Access Denied</h1>
        <p className="text-gray-500 text-sm mb-6">
          You don't have permission to view this page.
          {user && ` Your role (${user.role}) is not authorized here.`}
        </p>
        <Link
          to={home}
          className="inline-flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white font-semibold px-5 py-2.5 rounded-lg text-sm transition-colors"
        >
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
