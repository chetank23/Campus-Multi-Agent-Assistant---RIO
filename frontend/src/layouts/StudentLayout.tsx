/**
 * layouts/StudentLayout.tsx
 * --------------------------
 * Dedicated visual layout for the RIO-MJP Student Portal.
 * Inspired by the pastel powder-blue floating-surface visual reference:
 * - Pale powder-blue canvas (#EAF2FF) with soft ambient arcs & dot matrix
 * - Floating crisp white application surface with 32px rounded corners & soft blue shadow
 * - Compact left-side student navigation (RIO/University branding, Overview, My Timetable, Sign Out pill)
 * - Light welcoming header with actual student greeting, status pill, search, notifications, & avatar
 * - Clean responsive behavior across desktop, tablet, and mobile
 */

import React, { useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutGrid,
  CalendarDays,
  BookOpen,
  Megaphone,
  Bell,
  Search,
  Menu,
  X,
  LogOut,
  GraduationCap,
} from 'lucide-react';
import { useAuth } from '@/auth/AuthProvider';
import { apiGetMe } from '@/api/auth';
import { getStudentMyTimetable } from '@/api/timetable';
import { SignOutConfirmDialog } from '@/components/common';
import { CampusAssistantDrawer } from '@/components/chat';
import { NotificationBellDropdown } from '@/components/notifications/NotificationBellDropdown';

export const StudentLayout: React.FC = () => {
  const { user: ctxUser, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [showSignOutConfirm, setShowSignOutConfirm] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  // Fetch student identity and timetable academic context
  const { data: me } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: apiGetMe,
    staleTime: 60_000,
  });

  const { data: timetable } = useQuery({
    queryKey: ['student', 'my-timetable'],
    queryFn: () => getStudentMyTimetable(),
    staleTime: 60_000,
  });

  const user = me ?? ctxUser;
  const studentName = user?.name || 'Student';

  // Build academic context subtitle from real data
  const academicContext = React.useMemo(() => {
    const parts: string[] = [];
    if (timetable?.program_name) parts.push(timetable.program_name);
    if (timetable?.semester_number) parts.push(`Semester ${timetable.semester_number}`);
    if (timetable?.section_name) parts.push(`Section ${timetable.section_name}`);
    if (timetable?.batch_name) parts.push(`Batch ${timetable.batch_name}`);
    return parts.length > 0 ? parts.join(' • ') : 'Academic Portal • Class Schedule & Records';
  }, [timetable]);

  const handleSignOutClick = () => {
    setMobileMenuOpen(false);
    setShowSignOutConfirm(true);
  };

  const handleLogoutConfirm = async () => {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    try {
      await logout();
      setShowSignOutConfirm(false);
      navigate('/login');
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      setIsLoggingOut(false);
    }
  };

  const navItems = [
    {
      to: '/student',
      label: 'Overview',
      icon: <LayoutGrid size={18} />,
      end: true,
    },
    {
      to: '/student/timetable',
      label: 'My Timetable',
      icon: <CalendarDays size={18} />,
      end: false,
    },
    {
      to: '/student/courses',
      label: 'My Courses',
      icon: <BookOpen size={18} />,
      end: false,
    },
    {
      to: '/student/announcements',
      label: 'Announcements',
      icon: <Megaphone size={18} />,
      end: false,
    },
    {
      to: '/student/notifications',
      label: 'Notifications',
      icon: <Bell size={18} />,
      end: false,
    },
  ];

  return (
    <div className="min-h-screen bg-[#EAF2FF] text-[#17243B] font-sans relative overflow-x-hidden selection:bg-[#D8E9FE] selection:text-[#174786]">
      {/* ── Background Ambient Decorative Elements ── */}
      {/* Top-left curved blue ring */}
      <div
        className="pointer-events-none absolute -top-24 -left-24 w-96 h-96 rounded-full border-[32px] border-[#D6E6FE] opacity-60"
        aria-hidden="true"
      />
      {/* Bottom-right curved blue ring */}
      <div
        className="pointer-events-none absolute -bottom-36 -right-36 w-[520px] h-[520px] rounded-full border-[40px] border-[#D8E8FE] opacity-50"
        aria-hidden="true"
      />
      {/* Subtle dotted matrix on left canvas */}
      <div
        className="pointer-events-none absolute top-48 left-6 hidden xl:grid grid-cols-4 gap-2.5 opacity-50"
        aria-hidden="true"
      >
        {Array.from({ length: 32 }).map((_, i) => (
          <span key={i} className="w-1.5 h-1.5 rounded-full bg-[#95BDEE]" />
        ))}
      </div>

      {/* ── Main Centered Canvas Container ── */}
      <div className="relative z-10 max-w-[1600px] mx-auto p-3 sm:p-5 lg:p-7 min-h-screen flex flex-col justify-center">
        {/* Floating White Surface */}
        <div className="bg-white rounded-[24px] sm:rounded-[32px] border border-[#E5ECF5] shadow-[0_20px_60px_-15px_rgba(75,131,209,0.14)] p-4 sm:p-6 lg:p-7 flex flex-col md:flex-row gap-5 lg:gap-7 transition-all">
          {/* ── Left Navigation Column (Desktop) ── */}
          <aside className="hidden md:flex w-[190px] lg:w-[210px] shrink-0 bg-white rounded-[24px] border border-[#E5ECF5] p-5 flex-col justify-between shadow-xs">
            {/* Top Branding */}
            <div>
              <div className="flex flex-col items-center text-center pb-6 border-b border-[#E5ECF5]">
                {/* University Emblem Shield */}
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[#EBF3FE] to-[#DDEBFF] border border-[#CDE1FB] flex items-center justify-center text-[#4B83D1] shadow-xs mb-2.5">
                  <GraduationCap size={28} className="text-[#4B83D1]" />
                </div>
                <h1 className="text-sm font-bold text-[#17243B] tracking-tight">RIO Campus</h1>
                <p className="text-[11px] font-medium text-[#71819A]">Student Portal</p>
              </div>

              {/* Navigation Links */}
              <nav className="mt-6 space-y-1.5" aria-label="Student Navigation">
                {navItems.map((item) => {
                  const isActive = item.end
                    ? location.pathname === item.to
                    : location.pathname.startsWith(item.to);

                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.end}
                      className={({ isActive: active }) =>
                        `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-all duration-150 ${
                          active
                            ? 'bg-[#F1F6FF] text-[#4B83D1] shadow-xs'
                            : 'text-[#71819A] hover:text-[#17243B] hover:bg-[#F8FAFC]'
                        }`
                      }
                    >
                      <span className={isActive ? 'text-[#4B83D1]' : 'text-[#71819A]'}>
                        {item.icon}
                      </span>
                      <span>{item.label}</span>
                    </NavLink>
                  );
                })}
              </nav>
            </div>

            {/* Bottom Sign Out Pill Button */}
            <div className="pt-6 border-t border-[#E5ECF5]">
              <button
                type="button"
                onClick={handleSignOutClick}
                disabled={isLoggingOut}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-full bg-[#4B83D1] hover:bg-[#3D71BD] text-white text-xs font-semibold shadow-xs transition-colors duration-150 active:scale-[0.98] disabled:opacity-50"
              >
                <LogOut size={13} />
                <span>Sign Out</span>
              </button>
            </div>
          </aside>

          {/* ── Mobile Navigation Header & Drawer (Small Screens) ── */}
          <div className="md:hidden flex items-center justify-between pb-3 border-b border-[#E5ECF5]">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-[#EBF3FE] border border-[#CDE1FB] flex items-center justify-center text-[#4B83D1]">
                <GraduationCap size={18} />
              </div>
              <div>
                <p className="text-xs font-bold text-[#17243B]">RIO Campus</p>
                <p className="text-[10px] text-[#71819A]">Student Portal</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setMobileMenuOpen((prev) => !prev)}
                className="p-2 rounded-xl border border-[#E5ECF5] text-[#17243B] hover:bg-[#F8FAFC]"
                aria-label="Toggle Navigation Menu"
              >
                {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
              </button>
            </div>
          </div>

          {/* Mobile Drawer Dropdown */}
          {mobileMenuOpen && (
            <div className="md:hidden bg-[#F8FAFC] rounded-2xl border border-[#E5ECF5] p-3 space-y-2 mb-2 animate-in fade-in slide-in-from-top-2 duration-150">
              <nav className="space-y-1" aria-label="Mobile Student Navigation">
                {navItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    onClick={() => setMobileMenuOpen(false)}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-colors ${
                        isActive
                          ? 'bg-[#F1F6FF] text-[#4B83D1] shadow-xs'
                          : 'text-[#71819A] hover:text-[#17243B]'
                      }`
                    }
                  >
                    {item.icon}
                    <span>{item.label}</span>
                  </NavLink>
                ))}
              </nav>
              <div className="pt-2 border-t border-[#E5ECF5]">
                <button
                  type="button"
                  onClick={handleSignOutClick}
                  disabled={isLoggingOut}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-full bg-[#4B83D1] text-white text-xs font-semibold shadow-xs disabled:opacity-50"
                >
                  <LogOut size={13} />
                  <span>Sign Out</span>
                </button>
              </div>
            </div>
          )}

          {/* ── Main Content Workspace ── */}
          <main className="flex-1 min-w-0 flex flex-col">
            {/* ── Top Header Area ── */}
            <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 mb-2 border-b border-[#E5ECF5]/80">
              {/* Left Greeting & Context */}
              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-2xl sm:text-3xl font-extrabold text-[#17243B] tracking-tight">
                    Welcome, {studentName}!
                  </h2>
                  <span className="inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full text-xs font-semibold bg-[#DDF7EC] text-[#1B7A53] border border-[#C6F2DF] shadow-xs">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#1B7A53]" />
                    Active
                  </span>
                </div>
                <p className="text-xs sm:text-sm text-[#71819A] mt-1 font-medium">
                  {academicContext}
                </p>
              </div>

              {/* Right Action Icons & Avatar */}
              <div className="flex items-center gap-3 self-end sm:self-auto">
                {/* Search control button */}
                <button
                  type="button"
                  title="Search timetable or courses"
                  aria-label="Search"
                  className="w-10 h-10 rounded-full border border-[#E5ECF5] text-[#71819A] hover:text-[#17243B] hover:bg-[#F1F6FF] flex items-center justify-center transition-colors shadow-xs"
                >
                  <Search size={16} />
                </button>

                {/* Notification Bell Dropdown */}
                <NotificationBellDropdown
                  buttonClassName="w-10 h-10 rounded-full border border-[#E5ECF5] text-[#71819A] hover:text-[#17243B] hover:bg-[#F1F6FF] flex items-center justify-center transition-colors shadow-xs relative"
                  badgeClassName="absolute -top-1 -right-1 min-w-[16px] h-[16px] px-1 bg-[#4B83D1] text-white text-[9px] font-bold rounded-full flex items-center justify-center ring-2 ring-white shadow-xs"
                  iconSize={16}
                />

                {/* Student Avatar */}
                <div className="flex items-center gap-2.5 pl-1">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-[#4B83D1] to-[#6099E6] text-white font-bold flex items-center justify-center text-sm shadow-xs ring-2 ring-white">
                    {studentName.charAt(0).toUpperCase()}
                  </div>
                  <div className="hidden lg:block text-left">
                    <p className="text-xs font-bold text-[#17243B] truncate max-w-[120px]">
                      {studentName}
                    </p>
                    <p className="text-[10px] text-[#71819A] uppercase tracking-wider font-semibold">
                      Student
                    </p>
                  </div>
                </div>
              </div>
            </header>

            {/* ── Dynamic Child Route Content (Outlet) ── */}
            <div className="flex-1 pt-2">
              <Outlet />
            </div>
          </main>
        </div>
      </div>

      <SignOutConfirmDialog
        isOpen={showSignOutConfirm}
        isProcessing={isLoggingOut}
        onConfirm={handleLogoutConfirm}
        onCancel={() => setShowSignOutConfirm(false)}
      />

      <CampusAssistantDrawer />
    </div>
  );
};

export default StudentLayout;
