import React, { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  LogOut,
  ChevronDown,
  Menu,
  Bell,
  Shield,
  Building,
  Search,
  Calendar,
} from 'lucide-react';
import { useAuth } from '@/auth/AuthProvider';
import { academicYearsApi } from '@/api/academicYears';
import type { UserRole } from '@/auth/auth.types';

interface TopbarProps {
  title?: string;
  onToggleMobile?: () => void;
}

const roleLabel: Record<UserRole, string> = {
  ADMIN: 'System Admin',
  FACULTY: 'Faculty Member',
  STUDENT: 'Enrolled Student',
};

export const Topbar: React.FC<TopbarProps> = ({ onToggleMobile }) => {
  const { user, logout } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);

  // Fetch real active academic year for context pill
  const { data: academicYears } = useQuery({
    queryKey: ['academicYears'],
    queryFn: academicYearsApi.getAll,
    staleTime: 300_000,
  });

  const activeYear = academicYears?.find((y) => y.is_active) || academicYears?.[0];
  const yearDisplayName = activeYear?.year_name || '2026 – 2027';

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
    .slice(0, 2) || 'AD';

  return (
    <header className="h-[70px] bg-white border-b border-[#E4EAF2] flex items-center justify-between px-4 sm:px-6 shrink-0 sticky top-0 z-30 shadow-[0_1px_2px_rgba(0,0,0,0.02)]">
      {/* Left: Mobile menu toggle + Global Search bar */}
      <div className="flex items-center gap-3 flex-1 min-w-0 mr-4">
        {onToggleMobile && (
          <button
            type="button"
            onClick={onToggleMobile}
            className="lg:hidden p-2 rounded-lg text-[#536783] hover:text-[#111D35] hover:bg-[#F4F7FB] transition-colors focus:outline-none focus:ring-2 focus:ring-[#93B5E8]"
            aria-label="Toggle navigation menu"
          >
            <Menu size={20} />
          </button>
        )}

        <div className="relative w-full max-w-md hidden sm:block">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#8190A5]">
            <Search size={15} />
          </div>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search for students, faculty, rooms, courses..."
            className="w-full pl-9 pr-4 py-2 bg-[#F4F7FB] border border-[#E4EAF2] rounded-lg text-xs text-[#111D35] placeholder-[#8190A5] focus:outline-none focus:ring-2 focus:ring-[#93B5E8] focus:border-[#2563EB] transition-colors"
          />
        </div>
      </div>

      {/* Right: Academic Year Dropdown, Notifications, User Profile */}
      <div className="flex items-center gap-3 sm:gap-4 shrink-0">
        {/* Academic Year Selector Pill */}
        <div className="hidden md:flex items-center gap-2.5 px-3 py-1.5 rounded-lg border border-[#E4EAF2] bg-white hover:bg-[#F8FAFC] transition-colors shadow-2xs">
          <div className="text-[#536783]">
            <Calendar size={15} />
          </div>
          <div className="text-left">
            <span className="text-[10px] uppercase font-semibold text-[#8190A5] tracking-wide block leading-none">
              Academic Year
            </span>
            <span className="text-xs font-bold text-[#111D35] leading-tight block mt-0.5">
              {yearDisplayName}
            </span>
          </div>
          <ChevronDown size={14} className="text-[#8190A5] ml-1" />
        </div>

        {/* Notifications Icon Button */}
        <div className="relative">
          <button
            type="button"
            className="p-2 rounded-lg text-[#536783] hover:text-[#111D35] hover:bg-[#F4F7FB] transition-colors relative focus:outline-none focus:ring-2 focus:ring-[#93B5E8]"
            aria-label="View notifications"
            title="Notifications"
          >
            <Bell size={18} />
          </button>
        </div>

        {/* User Profile Menu */}
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2.5 rounded-lg p-1.5 hover:bg-[#F4F7FB] transition-colors focus:outline-none focus:ring-2 focus:ring-[#93B5E8]"
            aria-haspopup="true"
            aria-expanded={menuOpen}
          >
            {/* Deep Navy Avatar with bold initials */}
            <div className="w-9 h-9 rounded-full bg-[#10243A] flex items-center justify-center text-white text-xs font-bold shrink-0 shadow-xs ring-1 ring-[#2B4057]/40">
              {initials}
            </div>

            <div className="hidden sm:block text-left">
              <p className="text-xs font-bold text-[#111D35] leading-tight truncate max-w-[140px]">
                {user.name}
              </p>
              <p className="text-[11px] text-[#536783] leading-tight truncate max-w-[140px]">
                {roleLabel[user.role]}
              </p>
            </div>

            <ChevronDown size={14} className="text-[#8190A5] hidden sm:block transition-transform duration-150" />
          </button>

          {/* Profile Dropdown */}
          {menuOpen && (
            <div className="absolute right-0 mt-2 w-64 bg-white rounded-xl shadow-modal border border-[#E4EAF2] z-40 overflow-hidden animate-in fade-in zoom-in-95 duration-100">
              {/* User Identity Header */}
              <div className="p-4 border-b border-[#E4EAF2] bg-[#F8FAFC]">
                <p className="text-xs font-bold text-[#111D35] truncate">{user.name}</p>
                <p className="text-xs text-[#536783] mt-0.5 truncate">{user.email}</p>

                <div className="flex items-center gap-2 mt-2 pt-2 border-t border-[#E4EAF2] text-[11px] text-[#536783]">
                  <Shield size={12} className="text-[#8190A5] shrink-0" />
                  <span>Role: {roleLabel[user.role]}</span>
                </div>
                {user.department_id && (
                  <div className="flex items-center gap-2 mt-1 text-[11px] text-[#536783]">
                    <Building size={12} className="text-[#8190A5] shrink-0" />
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
