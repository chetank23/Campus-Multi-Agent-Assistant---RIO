/**
 * components/layout/Sidebar.tsx
 * ------------------------------
 * Role-aware left navigation sidebar for RIO-MJP.
 * High-fidelity academic ERP design with grouped navigation,
 * clear active states, semantic Lucide icons, and mobile drawer support.
 */

import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  GraduationCap,
  Users,
  BookOpen,
  Building2,
  CalendarDays,
  DoorOpen,
  School,
  Package,
  FileText,
  Bell,
  ClipboardList,
  Sparkles,
  X,
  Layers,
} from 'lucide-react';
import type { UserRole } from '@/auth/auth.types';

interface NavItem {
  label: string;
  icon: React.ReactNode;
  to: string;
  implemented: boolean;
}

interface NavGroup {
  groupTitle?: string;
  items: NavItem[];
}

function getNavGroups(role: UserRole): NavGroup[] {
  switch (role) {
    case 'ADMIN':
      return [
        {
          groupTitle: 'Overview',
          items: [
            { label: 'Dashboard', icon: <LayoutDashboard size={17} />, to: '/admin', implemented: true },
          ],
        },
        {
          groupTitle: 'Academic Architecture',
          items: [
            { label: 'Departments', icon: <Building2 size={17} />, to: '/admin/academic/departments', implemented: true },
            { label: 'Programs', icon: <GraduationCap size={17} />, to: '/admin/academic/programs', implemented: true },
            { label: 'Academic Years', icon: <CalendarDays size={17} />, to: '/admin/academic/years', implemented: true },
            { label: 'Semesters', icon: <Layers size={17} />, to: '/admin/academic/semesters', implemented: true },
            { label: 'Batches', icon: <Users size={17} />, to: '/admin/academic/batches', implemented: true },
            { label: 'Sections', icon: <BookOpen size={17} />, to: '/admin/academic/sections', implemented: true },
          ],
        },
        {
          groupTitle: 'Campus & Catalog',
          items: [
            { label: 'Courses', icon: <BookOpen size={17} />, to: '/admin/courses', implemented: true },
            { label: 'Buildings', icon: <Building2 size={17} />, to: '/admin/campus/buildings', implemented: true },
            { label: 'Rooms', icon: <DoorOpen size={17} />, to: '/admin/campus/rooms', implemented: true },
          ],
        },
        {
          groupTitle: 'People',
          items: [
            { label: 'Faculty', icon: <GraduationCap size={17} />, to: '/admin/people/faculty', implemented: true },
            { label: 'Students', icon: <School size={17} />, to: '/admin/people/students', implemented: true },
          ],
        },
        {
          groupTitle: 'Timetable Engine',
          items: [
            { label: 'Versions & Review', icon: <CalendarDays size={17} />, to: '/admin/timetable/versions', implemented: true },
            { label: 'Generate Timetable', icon: <Sparkles size={17} />, to: '/admin/timetable/generate', implemented: true },
          ],
        },
        {
          groupTitle: 'System & Records',
          items: [
            { label: 'Resources', icon: <Package size={17} />, to: '/admin/resources', implemented: false },
            { label: 'Change Requests', icon: <FileText size={17} />, to: '/admin/requests', implemented: false },
            { label: 'Notifications', icon: <Bell size={17} />, to: '/admin/notifications', implemented: false },
            { label: 'Audit Logs', icon: <ClipboardList size={17} />, to: '/admin/audit', implemented: false },
          ],
        },
      ];
    case 'FACULTY':
      return [
        {
          groupTitle: 'Overview',
          items: [
            { label: 'Dashboard', icon: <LayoutDashboard size={17} />, to: '/faculty', implemented: true },
          ],
        },
        {
          groupTitle: 'Schedules & Teaching',
          items: [
            { label: 'My Timetable', icon: <CalendarDays size={17} />, to: '/faculty/timetable', implemented: false },
            { label: 'Dept. Timetable', icon: <Building2 size={17} />, to: '/faculty/dept-timetable', implemented: false },
          ],
        },
      ];
    case 'STUDENT':
      return [
        {
          groupTitle: 'Overview',
          items: [
            { label: 'Dashboard', icon: <LayoutDashboard size={17} />, to: '/student', implemented: true },
          ],
        },
        {
          groupTitle: 'Academic Schedule',
          items: [
            { label: 'My Timetable', icon: <CalendarDays size={17} />, to: '/student/timetable', implemented: false },
          ],
        },
      ];
  }
}

interface SidebarProps {
  role: UserRole;
  mobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ role, mobileOpen = false, onCloseMobile }) => {
  const location = useLocation();
  const navGroups = getNavGroups(role);

  const roleLabels: Record<UserRole, string> = {
    ADMIN: 'System Admin',
    FACULTY: 'Faculty Member',
    STUDENT: 'Enrolled Student',
  };

  const roleBadgeStyles: Record<UserRole, string> = {
    ADMIN: 'bg-primary-900/90 text-primary-100 border-primary-800',
    FACULTY: 'bg-sky-900/80 text-sky-100 border-sky-800',
    STUDENT: 'bg-emerald-900/80 text-emerald-100 border-emerald-800',
  };

  const sidebarContent = (
    <div className="flex flex-col h-full bg-slate-900 text-slate-100 border-r border-slate-800">
      {/* Brand Header */}
      <div className="h-16 flex items-center justify-between px-5 border-b border-slate-800/90 shrink-0 bg-slate-950/40">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center shrink-0 shadow-sm border border-primary-500/30">
            <span className="text-white font-bold text-sm tracking-wider">R</span>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-bold text-white tracking-tight leading-none truncate">
                RIO-MJP
              </span>
              <span className="text-[10px] font-semibold uppercase tracking-wider bg-primary-500/20 text-primary-300 px-1.5 py-0.2 rounded border border-primary-500/30">
                ERP
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1 truncate">
              Campus Intelligence
            </p>
          </div>
        </div>

        {/* Mobile close button */}
        {onCloseMobile && (
          <button
            type="button"
            onClick={onCloseMobile}
            className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        )}
      </div>

      {/* Role Context Chip */}
      <div className="px-5 py-3 border-b border-slate-800/60 bg-slate-900/50">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium text-slate-400">Context:</span>
          <span
            className={`text-[10px] font-semibold tracking-wide uppercase px-2 py-0.5 rounded-full border ${roleBadgeStyles[role]}`}
          >
            {roleLabels[role]}
          </span>
        </div>
      </div>

      {/* Navigation Groups */}
      <nav className="flex-1 overflow-y-auto py-3 px-3 space-y-4">
        {navGroups.map((group, gIdx) => (
          <div key={gIdx} className="space-y-1">
            {group.groupTitle && (
              <p className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                {group.groupTitle}
              </p>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const isActive =
                  item.to === '/admin' || item.to === '/faculty' || item.to === '/student'
                    ? location.pathname === item.to
                    : location.pathname.startsWith(item.to);

                if (item.implemented) {
                  return (
                    <Link
                      key={item.to}
                      to={item.to}
                      onClick={onCloseMobile}
                      className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-all group ${
                        isActive
                          ? 'bg-primary-600 text-white font-semibold shadow-xs'
                          : 'text-slate-300 hover:bg-slate-800/80 hover:text-white'
                      }`}
                    >
                      <span
                        className={`shrink-0 transition-colors ${
                          isActive ? 'text-white' : 'text-slate-400 group-hover:text-slate-200'
                        }`}
                      >
                        {item.icon}
                      </span>
                      <span className="truncate">{item.label}</span>
                    </Link>
                  );
                }

                return (
                  <div
                    key={item.to}
                    className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs text-slate-500 cursor-not-allowed select-none transition-colors"
                    title="Module scheduled for next development stage"
                  >
                    <span className="text-slate-600 shrink-0">{item.icon}</span>
                    <span className="truncate">{item.label}</span>
                    <span className="ml-auto text-[9px] font-semibold uppercase tracking-wider bg-slate-800/90 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700/50">
                      Soon
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Institutional Footer */}
      <div className="p-3.5 border-t border-slate-800/90 bg-slate-950/30 shrink-0 text-center">
        <p className="text-[11px] font-medium text-slate-400">
          RIO-MJP Enterprise ERP
        </p>
        <p className="text-[10px] text-slate-400 mt-0.5">
          Academic Information System
        </p>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Persistent Sidebar */}
      <aside className="hidden lg:flex flex-col w-64 min-h-screen shrink-0 sticky top-0 h-screen z-20">
        {sidebarContent}
      </aside>

      {/* Mobile Drawer */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-slate-950/70 backdrop-blur-xs transition-opacity"
            onClick={onCloseMobile}
            aria-hidden="true"
          />
          {/* Drawer container */}
          <div className="relative flex flex-col w-72 max-w-[85vw] h-full shadow-2xl z-10 animate-in slide-in-from-left duration-200">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
};
