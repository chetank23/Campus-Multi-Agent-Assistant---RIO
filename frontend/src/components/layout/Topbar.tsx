/**
 * components/layout/Topbar.tsx
 * -----------------------------
 * Top navigation bar: mobile menu toggle, current academic context,
 * notification indicator, user profile menu, and sign out control.
 */

import React, { useState, useEffect, useRef } from 'react';
import { LogOut, ChevronDown, Menu, Bell, Shield, Building } from 'lucide-react';
import { useAuth } from '@/auth/AuthProvider';
import type { UserRole } from '@/auth/auth.types';
import { IconButton } from '@/components/common/IconButton';

interface TopbarProps {
  title?: string;
  onToggleMobile?: () => void;
}

const roleLabel: Record<UserRole, string> = {
  ADMIN: 'Administrator',
  FACULTY: 'Faculty',
  STUDENT: 'Student',
};

const roleColor: Record<UserRole, string> = {
  ADMIN: 'bg-slate-900 text-white border-slate-800',
  FACULTY: 'bg-primary-50 text-primary-800 border-primary-200',
  STUDENT: 'bg-emerald-50 text-emerald-800 border-emerald-200',
};

export const Topbar: React.FC<TopbarProps> = ({ title, onToggleMobile }) => {
  const { user, logout } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click or escape
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMenuOpen(false);
      }
    }
    if (menuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [menuOpen]);

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
    .filter(Boolean)
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <header className="h-16 bg-white/95 backdrop-blur-xs border-b border-slate-200/90 flex items-center justify-between px-4 sm:px-6 shrink-0 sticky top-0 z-30">
      {/* Left Side: Mobile Menu Button + Context Title */}
      <div className="flex items-center gap-3">
        {onToggleMobile && (
          <button
            type="button"
            onClick={onToggleMobile}
            className="lg:hidden p-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-600"
            aria-label="Toggle navigation menu"
          >
            <Menu size={20} />
          </button>
        )}

        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-primary-700 bg-primary-50 px-2 py-0.5 rounded border border-primary-100 hidden md:inline-block">
            CAMPUS AI
          </span>
          <span className="text-slate-300 hidden md:inline-block">/</span>
          <h1 className="text-sm sm:text-base font-bold text-slate-800 tracking-tight truncate">
            {title ?? 'Portal Overview'}
          </h1>
        </div>
      </div>

      {/* Right Side: Term Pill, Notifications, Role Chip, User Menu */}
      <div className="flex items-center gap-2 sm:gap-3">
        {/* System Active Term Chip */}
        <div className="hidden xl:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100 border border-slate-200 text-xs text-slate-600">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="font-medium">System Online</span>
        </div>

        {/* Notification Bell (Presentation only) */}
        <div className="relative">
          <IconButton
            icon={<Bell size={16} />}
            aria-label="View notifications"
            variant="ghost"
            size="md"
            title="Notifications"
            className="text-slate-500 hover:text-slate-800"
          />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-primary-600 ring-2 ring-white" />
        </div>

        {/* Role Chip */}
        <span
          className={`hidden sm:inline-flex text-xs font-semibold px-2.5 py-0.5 rounded-full border shadow-2xs ${roleColor[user.role]}`}
        >
          {roleLabel[user.role]}
        </span>

        {/* User Profile Menu */}
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2 rounded-lg p-1.5 hover:bg-slate-100/80 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-1"
            aria-haspopup="true"
            aria-expanded={menuOpen}
          >
            {/* Avatar with ring */}
            <div className="w-8 h-8 rounded-full bg-primary-700 flex items-center justify-center text-white text-xs font-bold shrink-0 ring-1 ring-primary-800 shadow-xs">
              {initials}
            </div>

            <div className="hidden sm:block text-left">
              <p className="text-xs font-semibold text-slate-800 leading-tight truncate max-w-[130px]">
                {user.name}
              </p>
              <p className="text-[11px] text-slate-400 leading-tight truncate max-w-[130px]">
                {user.email}
              </p>
            </div>

            <ChevronDown size={14} className="text-slate-400 hidden sm:block transition-transform duration-150" />
          </button>

          {/* Profile Dropdown */}
          {menuOpen && (
            <div className="absolute right-0 mt-2 w-64 bg-white rounded-xl shadow-modal border border-slate-200/90 z-40 overflow-hidden animate-in fade-in zoom-in-95 duration-100">
              {/* User Identity Header */}
              <div className="p-4 border-b border-slate-100 bg-slate-50/50">
                <p className="text-xs font-bold text-slate-900 truncate">{user.name}</p>
                <p className="text-xs text-slate-500 mt-0.5 truncate">{user.email}</p>

                <div className="flex items-center gap-2 mt-2 pt-2 border-t border-slate-200/60 text-[11px] text-slate-600">
                  <Shield size={12} className="text-slate-400 shrink-0" />
                  <span>Role: {user.role}</span>
                </div>
                {user.department_id && (
                  <div className="flex items-center gap-2 mt-1 text-[11px] text-slate-600">
                    <Building size={12} className="text-slate-400 shrink-0" />
                    <span>Dept. #{user.department_id}</span>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="p-1.5">
                <button
                  type="button"
                  onClick={handleLogout}
                  disabled={loggingOut}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs font-semibold text-rose-600 hover:bg-rose-50 rounded-lg transition-colors disabled:opacity-50"
                >
                  <LogOut size={14} />
                  <span>{loggingOut ? 'Signing out…' : 'Sign out of portal'}</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
