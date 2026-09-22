/**
 * components/layout/Sidebar.tsx
 * ------------------------------
 * Role-aware left navigation sidebar.
 *
 * Stage 6A: only Dashboard items are functional.
 * Future module links are rendered as placeholders with a "Soon" badge.
 */

import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  GraduationCap,
  Users,
  BookOpen,
  Building2,
  Calendar,
  Package,
  FileText,
  Bell,
  ScrollText,
  User,
  CalendarDays,
} from 'lucide-react';
import type { UserRole } from '@/auth/auth.types';

interface NavItem {
  label: string;
  icon: React.ReactNode;
  to: string;
  implemented: boolean;
}

function getNavItems(role: UserRole): NavItem[] {
  switch (role) {
    case 'ADMIN':
      return [
        { label: 'Dashboard', icon: <LayoutDashboard size={18} />, to: '/admin', implemented: true },
        { label: 'Departments', icon: <Building2 size={18} />, to: '/admin/academic/departments', implemented: true },
        { label: 'Programs', icon: <GraduationCap size={18} />, to: '/admin/academic/programs', implemented: true },
        { label: 'Academic Years', icon: <Calendar size={18} />, to: '/admin/academic/years', implemented: true },
        { label: 'Semesters', icon: <CalendarDays size={18} />, to: '/admin/academic/semesters', implemented: true },
        { label: 'Batches', icon: <Users size={18} />, to: '/admin/academic/batches', implemented: true },
        { label: 'Sections', icon: <BookOpen size={18} />, to: '/admin/academic/sections', implemented: true },
        { label: 'Students', icon: <User size={18} />, to: '/admin/people/students', implemented: true },
        { label: 'Faculty', icon: <Users size={18} />, to: '/admin/people/faculty', implemented: true },
        { label: 'Courses', icon: <BookOpen size={18} />, to: '/admin/courses', implemented: true },
        { label: 'Buildings', icon: <Building2 size={18} />, to: '/admin/campus/buildings', implemented: true },
        { label: 'Rooms', icon: <LayoutDashboard size={18} />, to: '/admin/campus/rooms', implemented: true },
        { label: 'Timetable', icon: <Calendar size={18} />, to: '/admin/timetable', implemented: true },
        { label: 'Resources', icon: <Package size={18} />, to: '/admin/resources', implemented: false },
        { label: 'Requests', icon: <FileText size={18} />, to: '/admin/requests', implemented: false },
        { label: 'Notifications', icon: <Bell size={18} />, to: '/admin/notifications', implemented: false },
        { label: 'Audit Logs', icon: <ScrollText size={18} />, to: '/admin/audit', implemented: false },
      ];
    case 'FACULTY':
      return [
        { label: 'Dashboard', icon: <LayoutDashboard size={18} />, to: '/faculty', implemented: true },
        { label: 'My Timetable', icon: <CalendarDays size={18} />, to: '/faculty/timetable', implemented: false },
        { label: 'Dept. Timetable', icon: <Calendar size={18} />, to: '/faculty/dept-timetable', implemented: false },
      ];
    case 'STUDENT':
      return [
        { label: 'Dashboard', icon: <LayoutDashboard size={18} />, to: '/student', implemented: true },
        { label: 'My Timetable', icon: <CalendarDays size={18} />, to: '/student/timetable', implemented: false },
      ];
  }
}

interface SidebarProps {
  role: UserRole;
}

export function Sidebar({ role }: SidebarProps) {
  const location = useLocation();
  const navItems = getNavItems(role);

  const roleBadgeColor: Record<UserRole, string> = {
    ADMIN: 'bg-violet-100 text-violet-700',
    FACULTY: 'bg-blue-100 text-blue-700',
    STUDENT: 'bg-emerald-100 text-emerald-700',
  };

  return (
    <aside className="hidden md:flex flex-col w-60 min-h-screen bg-white border-r border-gray-200 shrink-0">
      {/* Brand */}
      <div className="h-16 flex items-center gap-2.5 px-5 border-b border-gray-100">
        <div className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center shrink-0">
          <span className="text-white font-bold text-sm">R</span>
        </div>
        <div>
          <p className="text-sm font-semibold text-gray-900 leading-tight">RIO Campus AI</p>
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${roleBadgeColor[role]}`}>
            {role}
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-0.5">
        {navItems.map((item) => {
          const isActive =
            item.to === '/admin' || item.to === '/faculty' || item.to === '/student'
              ? location.pathname === item.to
              : location.pathname.startsWith(item.to);

          return item.implemented ? (
            <Link
              key={item.to}
              to={item.to}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-primary-50 text-primary-700'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              }`}
            >
              <span className={isActive ? 'text-primary-600' : 'text-gray-400'}>
                {item.icon}
              </span>
              {item.label}
            </Link>
          ) : (
            <div
              key={item.to}
              className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-400 cursor-not-allowed select-none"
              title="Coming in a future stage"
            >
              <span>{item.icon}</span>
              {item.label}
              <span className="ml-auto text-[9px] font-semibold uppercase tracking-wide bg-gray-100 text-gray-400 px-1.5 py-0.5 rounded-full">
                Soon
              </span>
            </div>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-gray-100">
        <p className="text-[10px] text-gray-400 text-center">RIO-MJP • Stage 6A</p>
      </div>
    </aside>
  );
}
