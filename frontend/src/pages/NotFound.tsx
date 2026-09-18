/**
 * pages/NotFound.tsx
 * -------------------
 * Generic 404 page.
 */

import { Link } from 'react-router-dom';
import { FileQuestion } from 'lucide-react';
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
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="text-center max-w-sm">
        <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-5">
          <FileQuestion className="text-gray-400" size={32} />
        </div>
        <h1 className="text-5xl font-black text-gray-200 mb-2">404</h1>
        <h2 className="text-xl font-bold text-gray-900 mb-2">Page not found</h2>
        <p className="text-gray-500 text-sm mb-6">
          The page you're looking for doesn't exist or has been moved.
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
