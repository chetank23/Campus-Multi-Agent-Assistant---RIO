/**
 * layouts/FacultyLayout.tsx
 * --------------------------
 * Dedicated visual layout for the RIO-MJP Faculty Portal.
 * Follows the attached Faculty reference mockup:
 * - Full-height deep navy left sidebar (#142542) with secondary surface (#1D3152)
 * - RIO Campus Portal logo with cyan cap emblem
 * - Faculty navigation (Dashboard, My Timetable, Department Timetable) with active blue pill state (#3975D1)
 * - Bottom faculty profile badge with real authenticated identity (name, designation) & Sign out action
 * - Crisp light pale-blue workspace background (#F1F6FD)
 * - Topbar with search control, notification bell, and user avatar
 * - Full responsive drawer on mobile/tablet viewports
 */

import React, { useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  CalendarDays,
  Building2,
  Clock,
  Boxes,
  ClipboardList,
  Bell,
  Sparkles,
  UserCheck,
  Search,
  Menu,
  X,
  LogOut,
  GraduationCap,
  ChevronRight,
} from 'lucide-react';
import { useAuth } from '@/auth/AuthProvider';
import { apiGetMe } from '@/api/auth';
import { getFacultyMyTimetable } from '@/api/timetable';
import { SignOutConfirmDialog } from '@/components/common';
import { CampusAssistantDrawer } from '@/components/chat';
import { NotificationBellDropdown } from '@/components/notifications/NotificationBellDropdown';

export const FacultyLayout: React.FC = () => {
  const { user: ctxUser, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showSignOutConfirm, setShowSignOutConfirm] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  // Fetch real authenticated faculty identity and timetable context
  const { data: me } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: apiGetMe,
    staleTime: 60_000,
  });

  const { data: timetable } = useQuery({
    queryKey: ['faculty', 'my-timetable'],
    queryFn: () => getFacultyMyTimetable(),
    staleTime: 60_000,
  });

  const user = me ?? ctxUser;
  const facultyName = user?.name || 'Faculty Member';
  const designation = timetable?.designation || (user?.role === 'FACULTY' ? 'Faculty Member' : 'Instructor');
  const departmentName = timetable?.department_name || (user?.department_id ? `Department #${user.department_id}` : 'Academic Faculty');

  // Compute initials for the avatar
  const initials = React.useMemo(() => {
    if (!facultyName) return 'F';
    const parts = facultyName.trim().split(/\s+/);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return facultyName.slice(0, 2).toUpperCase();
  }, [facultyName]);

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
      to: '/faculty',
      label: 'Dashboard',
      icon: <LayoutDashboard size={18} />,
      end: true,
    },
    {
      to: '/faculty/timetable',
      label: 'My Timetable',
      icon: <CalendarDays size={18} />,
      end: false,
    },
    {
      to: '/faculty/dept-timetable',
      label: 'Dept. Timetable',
      icon: <Building2 size={18} />,
      end: false,
    },
    {
      to: '/faculty/availability',
      label: 'Availability',
      icon: <Clock size={18} />,
      end: false,
    },
    {
      to: '/faculty/resources',
      label: 'Campus Resources',
      icon: <Boxes size={18} />,
      end: false,
    },
    {
      to: '/faculty/events',
      label: 'Clubs & Events',
      icon: <Sparkles size={18} />,
      end: false,
    },
    {
      to: '/faculty/substitutions',
      label: 'Substitutions',
      icon: <UserCheck size={18} />,
      end: false,
    },
    {
      to: '/faculty/requests',
      label: 'Change Requests',
      icon: <ClipboardList size={18} />,
      end: false,
    },
    {
      to: '/faculty/notifications',
      label: 'Notifications',
      icon: <Bell size={18} />,
      end: false,
    },
  ];

  return (
    <div className="min-h-screen bg-[#F1F6FD] text-[#101D36] font-sans flex antialiased selection:bg-[#E4EEFF] selection:text-[#174786]">
      {/* ── Left Sidebar (Desktop: Full Height Deep Navy #142542) ── */}
      <aside className="hidden md:flex w-[240px] lg:w-[260px] shrink-0 bg-[#142542] text-white flex-col justify-between py-6 px-4 border-r border-[#1D3152] select-none z-30 sticky top-0 h-screen">
        <div className="flex-1 min-h-0 flex flex-col">
          {/* Brand Area */}
          <div className="flex items-center gap-3 px-3 pb-6 border-b border-[#1D3152]/80 shrink-0">
            <div className="w-10 h-10 rounded-xl bg-[#1D3152] border border-[#2B426B] flex items-center justify-center text-[#38BDF8] shadow-xs">
              <GraduationCap size={22} className="text-[#38BDF8]" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-lg font-black tracking-tight text-white">RIO</span>
              </div>
              <p className="text-[11px] font-medium text-[#8FA3BF] tracking-wide">Campus Portal</p>
            </div>
          </div>

          {/* Section Heading */}
          <div className="mt-6 mb-2 px-3 shrink-0">
            <p className="text-[10px] font-bold tracking-wider text-[#647795] uppercase">
              FACULTY PORTAL
            </p>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-1.5 overflow-y-auto flex-1 pr-1" aria-label="Faculty Navigation">
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
                        ? 'bg-[#3975D1] text-white shadow-xs'
                        : 'text-[#A2B4CC] hover:text-white hover:bg-[#1D3152]'
                    }`
                  }
                >
                  <span className={isActive ? 'text-white' : 'text-[#8FA3BF]'}>
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>

        {/* Bottom Profile Badge & Sign Out */}
        <div className="space-y-3 pt-4 border-t border-[#1D3152]/80 shrink-0">
          {/* Faculty User Badge */}
          <div className="p-2.5 rounded-xl bg-[#1D3152]/70 border border-[#2B426B]/60 flex items-center justify-between gap-2.5 hover:bg-[#1D3152] transition-colors">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-8 h-8 rounded-full bg-white text-[#142542] font-black text-xs flex items-center justify-center shrink-0 shadow-xs">
                {initials}
              </div>
              <div className="min-w-0 text-left">
                <p className="text-xs font-bold text-white truncate">{facultyName}</p>
                <p className="text-[10px] text-[#8FA3BF] truncate">{designation}</p>
              </div>
            </div>
            <ChevronRight size={14} className="text-[#647795] shrink-0" />
          </div>

          {/* Sign Out Button */}
          <button
            type="button"
            onClick={handleSignOutClick}
            disabled={isLoggingOut}
            className="w-full flex items-center gap-2.5 px-3.5 py-2 rounded-xl text-xs font-medium text-[#A2B4CC] hover:text-white hover:bg-[#1D3152] transition-colors duration-150 disabled:opacity-50"
          >
            <LogOut size={15} className="text-[#8FA3BF]" />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      {/* ── Main Content Area ── */}
      <div className="flex-1 min-w-0 flex flex-col min-h-screen">
        {/* Topbar */}
        <header className="h-16 px-4 sm:px-6 lg:px-8 bg-white border-b border-[#E3EBF6] flex items-center justify-between gap-4 sticky top-0 z-20 shadow-2xs">
          {/* Left: Mobile Drawer Toggle & Breadcrumb/Identity */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileMenuOpen((prev) => !prev)}
              className="md:hidden p-2 rounded-xl border border-[#E3EBF6] text-[#101D36] hover:bg-[#F1F6FD]"
              aria-label="Toggle Navigation Drawer"
            >
              {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
            </button>

            <div className="hidden sm:block">
              <span className="text-xs font-bold uppercase tracking-wider text-[#3975D1]">
                Faculty Portal
              </span>
              <span className="text-xs text-[#647795] mx-1.5">•</span>
              <span className="text-xs font-medium text-[#647795]">{departmentName}</span>
            </div>
          </div>

          {/* Right Controls: Search, Notifications & Avatar */}
          <div className="flex items-center gap-3">
            {/* Search Input Box */}
            <div className="relative hidden sm:block w-48 md:w-64">
              <Search
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[#647795]"
              />
              <input
                type="text"
                placeholder="Search..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 rounded-full border border-[#E3EBF6] bg-[#F8FAFD] text-xs text-[#101D36] placeholder-[#647795] focus:outline-none focus:ring-2 focus:ring-[#3975D1] focus:bg-white transition-all"
              />
            </div>

            {/* Notification Bell Dropdown */}
            <NotificationBellDropdown
              buttonClassName="w-9 h-9 rounded-full border border-[#E3EBF6] bg-white text-[#647795] hover:text-[#101D36] hover:bg-[#F1F6FD] flex items-center justify-center transition-colors relative shadow-2xs"
              badgeClassName="absolute -top-1 -right-1 min-w-[16px] h-[16px] px-1 bg-[#3975D1] text-white text-[9px] font-bold rounded-full flex items-center justify-center ring-2 ring-white shadow-xs"
              iconSize={15}
            />

            {/* Faculty Initial Avatar */}
            <div className="w-9 h-9 rounded-full bg-[#142542] text-white font-bold flex items-center justify-center text-xs shadow-xs ring-2 ring-[#E3EBF6]">
              {initials}
            </div>
          </div>
        </header>

        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="md:hidden bg-[#142542] text-white p-4 space-y-3 border-b border-[#1D3152] animate-in fade-in slide-in-from-top-2 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-[#1D3152]">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-[#1D3152] flex items-center justify-center text-[#38BDF8]">
                  <GraduationCap size={18} />
                </div>
                <div>
                  <p className="text-xs font-bold text-white">RIO Campus</p>
                  <p className="text-[10px] text-[#8FA3BF]">Faculty Portal</p>
                </div>
              </div>
            </div>

            <nav className="space-y-1" aria-label="Mobile Faculty Navigation">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-colors ${
                      isActive
                        ? 'bg-[#3975D1] text-white shadow-xs'
                        : 'text-[#A2B4CC] hover:text-white'
                    }`
                  }
                >
                  {item.icon}
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </nav>

            <div className="pt-2 border-t border-[#1D3152] flex items-center justify-between">
              <span className="text-xs text-[#8FA3BF] truncate">{facultyName}</span>
              <button
                type="button"
                onClick={handleSignOutClick}
                disabled={isLoggingOut}
                className="text-xs font-semibold text-[#38BDF8] hover:underline disabled:opacity-50"
              >
                Sign out
              </button>
            </div>
          </div>
        )}

        {/* Dynamic Page Content */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-[1600px] w-full mx-auto">
          <Outlet />
        </main>
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

export default FacultyLayout;
