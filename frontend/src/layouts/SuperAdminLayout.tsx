/**
 * layouts/SuperAdminLayout.tsx
 * ----------------------------
 * Dedicated executive visual layout for the RIO-MJP Super Admin Portal.
 * Theme: Executive Deep Indigo / Violet (#1E1B4B & #2E2866) with amber/gold accents (#F59E0B).
 */

import React, { useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  Award,
  Users2,
  BookOpen,
  Inbox,
  ShieldCheck,
  LogOut,
  Sparkles,
  Menu,
  X,
  School,
} from 'lucide-react';
import { useAuth } from '@/auth/useAuth';
import { apiGetMe } from '@/api/auth';
import { SignOutConfirmDialog } from '@/components/common';
import { NotificationBellDropdown } from '@/components/notifications/NotificationBellDropdown';
import { CampusAssistantDrawer } from '@/components/chat';

interface NavItem {
  label: string;
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
}

const navItems: NavItem[] = [
  { label: 'Executive Overview', to: '/super-admin', icon: LayoutDashboard },
  { label: 'Academic Regulations', to: '/super-admin/regulations', icon: Award },
  { label: 'Admission Cohorts', to: '/super-admin/cohorts', icon: Users2 },
  { label: 'Curriculum Versions', to: '/super-admin/curriculum-versions', icon: BookOpen },
  { label: 'AI Syllabus Studio', to: '/super-admin/extraction', icon: Sparkles, badge: 'AI' },
  { label: 'Admin Requests', to: '/super-admin/requests', icon: Inbox },
  { label: 'Governance Audit', to: '/super-admin/audit', icon: ShieldCheck },
];

export const SuperAdminLayout: React.FC = () => {
  const { user: ctxUser, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [showSignOutConfirm, setShowSignOutConfirm] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const { data: me } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: apiGetMe,
    staleTime: 60_000,
  });

  const userName = me?.name || ctxUser?.name || 'Super Administrator';
  const userEmail = me?.email || ctxUser?.email || 'superadmin@campus.edu';

  const handleSignOut = async () => {
    setIsLoggingOut(true);
    try {
      await logout();
      navigate('/login');
    } finally {
      setIsLoggingOut(false);
      setShowSignOutConfirm(false);
    }
  };

  return (
    <div className="flex h-screen bg-[#F8FAFC] text-slate-800 antialiased overflow-hidden">
      {/* ── Left Sidebar (Executive Deep Indigo #1E1B4B) ────────────── */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 bg-[#1E1B4B] text-white flex flex-col transition-transform duration-200 lg:static lg:translate-x-0 ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-0 max-lg:-translate-x-full'
        }`}
      >
        {/* Brand Header */}
        <div className="flex items-center justify-between px-5 h-16 border-b border-indigo-900/60 bg-[#17143A]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-amber-500/20 border border-amber-400/40 flex items-center justify-center text-amber-400 shadow-sm">
              <School className="w-5 h-5" />
            </div>
            <div>
              <span className="font-bold text-sm tracking-wide text-white block">RIO CENTRAL</span>
              <span className="text-[10px] tracking-wider font-semibold text-amber-400 uppercase">Super Admin Portal</span>
            </div>
          </div>
          <button
            onClick={() => setMobileMenuOpen(false)}
            className="lg:hidden p-1 rounded-lg text-slate-400 hover:text-white hover:bg-indigo-900/40"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Institution Badge */}
        <div className="px-4 py-3 bg-indigo-950/40 border-b border-indigo-900/40">
          <div className="flex items-center justify-between text-xs">
            <span className="text-indigo-200 text-[11px] font-medium">Institution Scope</span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
              ALL DEPARTMENTS
            </span>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isExact = location.pathname === item.to;
            const isActive = isExact || (item.to !== '/super-admin' && location.pathname.startsWith(item.to));

            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setMobileMenuOpen(false)}
                className={`flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 font-semibold shadow-md shadow-amber-500/20'
                    : 'text-indigo-100/80 hover:text-white hover:bg-white/5'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-slate-950' : 'text-indigo-300'}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge && (
                  <span
                    className={`px-1.5 py-0.5 text-[9px] font-bold rounded-md uppercase tracking-wider ${
                      isActive ? 'bg-slate-950 text-amber-400' : 'bg-indigo-700/60 text-indigo-200'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* User Identity & Logout Footer */}
        <div className="p-3 border-t border-indigo-900/60 bg-[#17143A]/60">
          <div className="p-2.5 rounded-xl bg-indigo-900/30 border border-indigo-800/40 flex items-center justify-between">
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-white truncate">{userName}</p>
              <p className="text-[11px] text-indigo-300/80 truncate">{userEmail}</p>
            </div>
            <button
              onClick={() => setShowSignOutConfirm(true)}
              title="Sign Out"
              className="p-1.5 ml-2 rounded-lg text-indigo-300 hover:text-amber-400 hover:bg-white/10 transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main Workspace ─────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Navbar */}
        <header className="h-16 bg-white border-b border-slate-200 px-6 flex items-center justify-between flex-shrink-0 z-10 shadow-sm">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-2 rounded-lg text-slate-600 hover:bg-slate-100"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div>
              <h1 className="text-base font-bold text-slate-900">
                Central Curriculum & Academic Structure Management
              </h1>
              <p className="text-xs text-slate-500 hidden sm:block">
                Institution-wide governance, syllabus verification & timetable coordination
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <NotificationBellDropdown />
            <div className="h-8 w-px bg-slate-200 mx-1 hidden sm:block" />
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-950 text-xs font-semibold">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              SUPER ADMIN
            </div>
          </div>
        </header>

        {/* Content Outlet */}
        <main className="flex-1 overflow-y-auto p-6 md:p-8 bg-[#F8FAFC]">
          <Outlet />
        </main>
      </div>

      {/* Sign Out Modal */}
      <SignOutConfirmDialog
        isOpen={showSignOutConfirm}
        onCancel={() => setShowSignOutConfirm(false)}
        onConfirm={handleSignOut}
        isProcessing={isLoggingOut}
      />

      {/* RIO AI Assistant Drawer */}
      <CampusAssistantDrawer />
    </div>
  );
};
