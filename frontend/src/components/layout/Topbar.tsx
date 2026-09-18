/**
 * components/layout/Topbar.tsx
 * -----------------------------
 * Top navigation bar: user info, role chip, and logout button.
 */

import { LogOut, ChevronDown } from 'lucide-react';
import { useState } from 'react';
import { useAuth } from '@/auth/AuthProvider';
import type { UserRole } from '@/auth/auth.types';

const roleLabel: Record<UserRole, string> = {
  ADMIN: 'Administrator',
  FACULTY: 'Faculty',
  STUDENT: 'Student',
};

const roleColor: Record<UserRole, string> = {
  ADMIN: 'bg-violet-100 text-violet-700 border-violet-200',
  FACULTY: 'bg-blue-100 text-blue-700 border-blue-200',
  STUDENT: 'bg-emerald-100 text-emerald-700 border-emerald-200',
};

export function Topbar({ title }: { title?: string }) {
  const { user, logout } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      setLoggingOut(false);
    }
  }

  if (!user) return null;

  const initials = user.name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0">
      {/* Page title */}
      <h1 className="text-base font-semibold text-gray-800 hidden sm:block">
        {title ?? 'Dashboard'}
      </h1>

      {/* Right side */}
      <div className="ml-auto flex items-center gap-3">
        {/* Role chip */}
        <span
          className={`hidden sm:inline-flex text-xs font-semibold px-2.5 py-1 rounded-full border ${roleColor[user.role]}`}
        >
          {roleLabel[user.role]}
        </span>

        {/* User menu */}
        <div className="relative">
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-gray-50 transition-colors"
            aria-haspopup="true"
            aria-expanded={menuOpen}
          >
            {/* Avatar */}
            <div className="w-8 h-8 rounded-full bg-primary-600 flex items-center justify-center text-white text-sm font-semibold shrink-0">
              {initials}
            </div>
            <div className="hidden sm:block text-left">
              <p className="text-sm font-medium text-gray-900 leading-tight">{user.name}</p>
              <p className="text-xs text-gray-500 leading-tight truncate max-w-[160px]">{user.email}</p>
            </div>
            <ChevronDown size={14} className="text-gray-400 hidden sm:block" />
          </button>

          {/* Dropdown */}
          {menuOpen && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setMenuOpen(false)}
                aria-hidden="true"
              />
              <div className="absolute right-0 mt-1 w-56 bg-white rounded-xl shadow-lg border border-gray-100 z-20 overflow-hidden">
                {/* User info header */}
                <div className="px-4 py-3 border-b border-gray-50">
                  <p className="text-sm font-semibold text-gray-900">{user.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5 truncate">{user.email}</p>
                  {user.department_id && (
                    <p className="text-xs text-gray-400 mt-0.5">Dept. #{user.department_id}</p>
                  )}
                </div>

                {/* Actions */}
                <div className="py-1">
                  <button
                    onClick={handleLogout}
                    disabled={loggingOut}
                    className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                  >
                    <LogOut size={15} />
                    {loggingOut ? 'Signing out…' : 'Sign out'}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
