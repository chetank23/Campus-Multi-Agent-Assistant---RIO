/**
 * components/layout/AdminSidebar.tsx
 * -----------------------------------
 * ADMIN-exclusive redesigned sidebar replicating the Campus Assistant visual reference:
 * - Brand header with royal-blue graduation-cap logo, vertical divider, Campus Assistant title,
 *   Timetable & Academic Management subtitle, and soft blue decorative wave.
 * - GENERAL section: pale lavender pill header + prominent royal-blue active Dashboard card.
 * - Structured white cards with pale lavender-blue headers, subtle borders, and separators:
 *   - ACADEMIC MANAGEMENT (Departments & Programs, Students & Sections, Faculty & Courses)
 *   - TIMETABLE ENGINE (Timetable Workspace, Generation & Conflicts, Versions & Publishing)
 *   - CAMPUS INFRASTRUCTURE (Buildings, Rooms & Labs, Resource Management, Time Slots & Calendar)
 *   - DATA & INTEGRATION (Import & Validation, Reports & Analytics)
 *   - SYSTEM (Users & Roles, Change Requests, Audit Logs, Settings [Soon])
 * - Bottom footer with horizontal divider and light-blue double-chevron collapse button.
 * - Desktop collapsible state (w-[272px] <-> w-[76px]) and mobile slide-over drawer support.
 */

import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  GraduationCap,
  Home,
  LayoutGrid,
  Layers,
  Users,
  CalendarDays,
  Sparkles,
  Briefcase,
  History,
  Building2,
  Box,
  CalendarClock,
  UploadCloud,
  Network,
  BarChart3,
  ShieldCheck,
  ClipboardList,
  Database,
  Settings,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  X,
} from 'lucide-react';

interface SubNavItem {
  label: string;
  to: string;
}

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  to?: string;
  subItems?: SubNavItem[];
  soon?: boolean;
}

interface NavSection {
  id: string;
  title: string;
  icon: React.ReactNode;
  items: NavItem[];
}

const adminSections: NavSection[] = [
  {
    id: 'academic',
    title: 'ACADEMIC MANAGEMENT',
    icon: <Layers size={15} className="text-[#2563EB] shrink-0" />,
    items: [
      {
        id: 'dept-programs',
        label: 'Departments & Programs',
        icon: <Layers size={17} className="shrink-0" />,
        to: '/admin/academic/departments',
        subItems: [
          { label: 'Departments', to: '/admin/academic/departments' },
          { label: 'Programs', to: '/admin/academic/programs' },
          { label: 'Academic Years', to: '/admin/academic/years' },
          { label: 'Semesters', to: '/admin/academic/semesters' },
        ],
      },
      {
        id: 'students-sections',
        label: 'Students & Sections',
        icon: <Users size={17} className="shrink-0" />,
        to: '/admin/people/students',
        subItems: [
          { label: 'Students Roster', to: '/admin/people/students' },
          { label: 'Sections', to: '/admin/academic/sections' },
          { label: 'Batches', to: '/admin/academic/batches' },
        ],
      },
      {
        id: 'faculty-courses',
        label: 'Faculty & Courses',
        icon: <GraduationCap size={17} className="shrink-0" />,
        to: '/admin/people/faculty',
        subItems: [
          { label: 'Faculty Directory', to: '/admin/people/faculty' },
          { label: 'Course Catalog', to: '/admin/courses' },
        ],
      },
    ],
  },
  {
    id: 'timetable',
    title: 'TIMETABLE ENGINE',
    icon: <CalendarDays size={15} className="text-[#2563EB] shrink-0" />,
    items: [
      {
        id: 'workspace',
        label: 'Timetable Workspace',
        icon: <CalendarDays size={17} className="shrink-0" />,
        to: '/admin/timetable/versions',
      },
      {
        id: 'generation',
        label: 'Generation & Conflicts',
        icon: <Sparkles size={17} className="shrink-0" />,
        to: '/admin/timetable/generate',
      },
      {
        id: 'versions',
        label: 'Versions & Publishing',
        icon: <History size={17} className="shrink-0" />,
        to: '/admin/timetable/versions',
      },
    ],
  },
  {
    id: 'campus',
    title: 'CAMPUS INFRASTRUCTURE',
    icon: <Building2 size={15} className="text-[#2563EB] shrink-0" />,
    items: [
      {
        id: 'buildings-rooms',
        label: 'Buildings, Rooms & Labs',
        icon: <Building2 size={17} className="shrink-0" />,
        to: '/admin/campus/buildings',
        subItems: [
          { label: 'Buildings', to: '/admin/campus/buildings' },
          { label: 'Rooms & Labs', to: '/admin/campus/rooms' },
        ],
      },
      {
        id: 'resources',
        label: 'Resource Management',
        icon: <Box size={17} className="shrink-0" />,
        to: '/admin/resources',
      },
      {
        id: 'events-clubs',
        label: 'Events & Clubs',
        icon: <Sparkles size={17} className="shrink-0" />,
        to: '/admin/events',
      },
      {
        id: 'cdc-placements',
        label: 'CDC Placements',
        icon: <Briefcase size={17} className="shrink-0" />,
        to: '/admin/placements',
      },
      {
        id: 'calendar-slots',
        label: 'Time Slots & Calendar',
        icon: <CalendarClock size={17} className="shrink-0" />,
        to: '/admin/campus/calendar-slots',
      },
    ],
  },
  {
    id: 'data',
    title: 'DATA & INTEGRATION',
    icon: <Network size={15} className="text-[#2563EB] shrink-0" />,
    items: [
      {
        id: 'import',
        label: 'Import & Validation',
        icon: <UploadCloud size={17} className="shrink-0" />,
        to: '/admin/data/import',
      },
      {
        id: 'reports',
        label: 'Reports & Analytics',
        icon: <BarChart3 size={17} className="shrink-0" />,
        to: '/admin/reports',
      },
    ],
  },
  {
    id: 'system',
    title: 'SYSTEM',
    icon: <Settings size={15} className="text-[#2563EB] shrink-0" />,
    items: [
      {
        id: 'users',
        label: 'Users & Roles',
        icon: <ShieldCheck size={17} className="shrink-0" />,
        to: '/admin/system/users',
      },
      {
        id: 'requests',
        label: 'Change Requests',
        icon: <ClipboardList size={17} className="shrink-0" />,
        to: '/admin/requests',
      },
      {
        id: 'audit',
        label: 'Audit Logs',
        icon: <Database size={17} className="shrink-0" />,
        to: '/admin/audit',
      },
      {
        id: 'settings',
        label: 'Settings',
        icon: <Settings size={17} className="shrink-0" />,
        soon: true,
      },
    ],
  },
];

interface AdminSidebarProps {
  mobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export const AdminSidebar: React.FC<AdminSidebarProps> = ({
  mobileOpen = false,
  onCloseMobile,
}) => {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [expandedItems, setExpandedItems] = useState<Record<string, boolean>>({});

  const toggleExpand = (id: string) => {
    setExpandedItems((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  const isDashboardActive = location.pathname === '/admin';

  const isSubItemActive = (to: string): boolean => {
    return location.pathname === to || location.pathname.startsWith(to + '/');
  };

  const isItemActive = (item: NavItem): boolean => {
    if (!item.to) return false;
    if (item.id === 'workspace') {
      return location.pathname === '/admin/timetable/versions';
    }
    if (item.id === 'versions') {
      return location.pathname.startsWith('/admin/timetable/versions/');
    }
    if (item.subItems && item.subItems.length > 0) {
      return item.subItems.some((sub) => isSubItemActive(sub.to));
    }
    return location.pathname === item.to || location.pathname.startsWith(item.to + '/');
  };

  const isItemExpanded = (item: NavItem): boolean => {
    if (expandedItems[item.id] !== undefined) {
      return expandedItems[item.id];
    }
    // Auto-expand if current route matches any child
    if (item.subItems) {
      return item.subItems.some((sub) => isSubItemActive(sub.to));
    }
    return false;
  };

  const sidebarContent = (
    <div className="flex flex-col h-full bg-[#F8FAFD] text-[#0F172A] border-r border-[#E2E8F0] select-none shadow-[1px_0_4px_rgba(0,0,0,0.02)]">
      {/* ── Brand Header ────────────────────────────────────────────── */}
      <div className="h-[74px] flex items-center justify-between px-4 border-b border-[#E2E8F0] shrink-0 bg-white relative overflow-hidden select-none">
        {/* Soft blue decorative wave in top-right */}
        {!collapsed && (
          <div className="absolute top-0 right-0 w-36 h-20 pointer-events-none overflow-hidden select-none">
            <svg viewBox="0 0 144 80" fill="none" className="w-full h-full">
              <path
                d="M144 0C130 15 110 35 85 52C60 68 35 72 20 80H144V0Z"
                fill="url(#softBlueWave)"
                opacity="0.4"
              />
              <defs>
                <linearGradient id="softBlueWave" x1="144" y1="0" x2="30" y2="80" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#60A5FA" stopOpacity="0.85" />
                  <stop offset="0.6" stopColor="#93C5FD" stopOpacity="0.45" />
                  <stop offset="1" stopColor="#DBEAFE" stopOpacity="0.15" />
                </linearGradient>
              </defs>
            </svg>
          </div>
        )}

        <Link
          to="/admin"
          onClick={onCloseMobile}
          className={`flex items-center min-w-0 z-10 group ${
            collapsed ? 'mx-auto justify-center' : 'gap-3'
          }`}
          title={collapsed ? 'Campus Assistant - Admin Portal' : undefined}
        >
          {/* Royal-blue rounded-square graduation-cap logo */}
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#2563EB] to-[#1D4ED8] flex items-center justify-center shrink-0 shadow-md shadow-blue-500/20 group-hover:scale-105 transition-transform duration-200">
            <GraduationCap size={22} className="text-white" />
          </div>

          {!collapsed && (
            <div className="flex items-center min-w-0">
              {/* Vertical divider */}
              <div className="h-8 w-px bg-[#E2E8F0] mx-3 shrink-0" />

              <div className="min-w-0">
                <span className="text-[14.5px] font-bold text-[#0F172A] tracking-tight leading-none block truncate">
                  Campus Assistant
                </span>
                <p className="text-[10.5px] text-[#64748B] leading-tight mt-1 font-normal tracking-tight truncate">
                  Timetable & Academic Management
                </p>
              </div>
            </div>
          )}
        </Link>

        {/* Mobile close button */}
        {onCloseMobile && (
          <button
            type="button"
            onClick={onCloseMobile}
            className="lg:hidden z-10 p-1.5 rounded-lg text-[#64748B] hover:text-[#0F172A] hover:bg-[#F1F5F9] transition-colors"
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        )}
      </div>

      {/* ── Scrollable Navigation Area ──────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto p-3 space-y-3 scrollbar-thin">
        {/* ── Section: GENERAL ──────────────────────────────────────── */}
        <div className="space-y-1.5">
          {!collapsed ? (
            <div className="bg-[#EEF3FF] border border-blue-100/60 px-3 py-1.5 rounded-xl flex items-center gap-2">
              <LayoutGrid size={14} className="text-[#2563EB] shrink-0" />
              <span className="text-[11px] font-bold tracking-wider text-[#1E3A8A] uppercase">
                GENERAL
              </span>
            </div>
          ) : (
            <div className="h-px bg-[#E2E8F0] my-2 mx-2" />
          )}

          {/* Active Dashboard item */}
          <Link
            to="/admin"
            onClick={onCloseMobile}
            title={collapsed ? 'Dashboard' : undefined}
            className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-[13.5px] transition-all duration-150 ${
              collapsed ? 'justify-center px-0 w-10 h-10 mx-auto' : 'w-full'
            } ${
              isDashboardActive
                ? 'bg-[#1D61E7] text-white font-semibold shadow-sm hover:bg-[#1955cc]'
                : 'bg-white border border-[#E2E8F0] text-[#1E293B] hover:bg-[#F8FAFC] shadow-xs font-medium'
            }`}
          >
            <Home
              size={18}
              className={`shrink-0 ${isDashboardActive ? 'text-white' : 'text-[#334155]'}`}
            />
            {!collapsed && <span className="truncate">Dashboard</span>}
          </Link>
        </div>

        {/* ── Section Cards ─────────────────────────────────────────── */}
        {adminSections.map((section) => (
          <div key={section.id} className="space-y-1.5">
            {!collapsed ? (
              <div className="rounded-2xl border border-[#E2E8F0] bg-white shadow-xs overflow-hidden">
                {/* Section Header */}
                <div className="bg-[#EEF3FF] px-3.5 py-2 flex items-center gap-2 border-b border-[#E2E8F0]/60">
                  {section.icon}
                  <span className="text-[11px] font-bold tracking-wider text-[#1E3A8A] uppercase">
                    {section.title}
                  </span>
                </div>

                {/* Section Items */}
                <div className="divide-y divide-[#F1F5F9]">
                  {section.items.map((item) => {
                    const active = isItemActive(item);
                    const hasSub = item.subItems && item.subItems.length > 0;
                    const expanded = isItemExpanded(item);

                    // Unavailable / Soon item
                    if (item.soon || !item.to) {
                      return (
                        <div
                          key={item.id}
                          className="flex items-center gap-3 px-3.5 py-2.5 text-[13px] text-[#94A3B8] cursor-not-allowed select-none bg-white/60"
                        >
                          <span className="text-[#94A3B8]">{item.icon}</span>
                          <span className="truncate flex-1 font-medium">{item.label}</span>
                          <span className="ml-auto text-[10px] font-bold uppercase tracking-wider bg-[#E8F0FE] text-[#2563EB] px-2 py-0.5 rounded-full border border-blue-200/60 shadow-xs">
                            Soon
                          </span>
                        </div>
                      );
                    }

                    // Item with sub-items
                    if (hasSub) {
                      return (
                        <div key={item.id} className="bg-white">
                          <div
                            className={`flex items-center justify-between px-3.5 py-2.5 text-[13px] transition-colors group cursor-pointer ${
                              !expanded && active
                                ? 'bg-[#1D61E7] text-white font-semibold'
                                : active
                                ? 'bg-blue-50/70 text-[#1D61E7] font-semibold'
                                : 'text-[#1E293B] hover:bg-[#F8FAFC]'
                            }`}
                            onClick={() => toggleExpand(item.id)}
                          >
                            <Link
                              to={item.to}
                              onClick={(e) => {
                                e.stopPropagation();
                                onCloseMobile?.();
                                if (!expanded) toggleExpand(item.id);
                              }}
                              className="flex items-center gap-3 flex-1 min-w-0"
                            >
                              <span
                                className={
                                  !expanded && active
                                    ? 'text-white'
                                    : active
                                    ? 'text-[#1D61E7]'
                                    : 'text-[#334155] group-hover:text-[#0F172A]'
                                }
                              >
                                {item.icon}
                              </span>
                              <span className="truncate font-medium">{item.label}</span>
                            </Link>

                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleExpand(item.id);
                              }}
                              className={`p-1 rounded-md transition-colors ${
                                !expanded && active
                                  ? 'text-white hover:bg-white/20'
                                  : active
                                  ? 'text-[#1D61E7] hover:bg-blue-100/50'
                                  : 'text-[#64748B] hover:text-[#0F172A] hover:bg-[#E2E8F0]/50'
                              }`}
                              aria-label={`Toggle ${item.label} submenu`}
                            >
                              <ChevronDown
                                size={15}
                                className={`transition-transform duration-200 ${
                                  expanded ? 'rotate-180' : ''
                                }`}
                              />
                            </button>
                          </div>

                          {/* Submenu links */}
                          {expanded && (
                            <div className="bg-[#F8FAFC] border-t border-[#F1F5F9] px-3 py-1.5 space-y-1">
                              {item.subItems!.map((sub) => {
                                const subActive = isSubItemActive(sub.to);
                                return (
                                  <Link
                                    key={sub.to}
                                    to={sub.to}
                                    onClick={onCloseMobile}
                                    className={`block px-3 py-1.5 rounded-lg text-[12px] transition-all truncate ${
                                      subActive
                                        ? 'bg-[#1D61E7] text-white font-semibold shadow-xs'
                                        : 'text-[#475569] hover:text-[#0F172A] hover:bg-[#EEF2F6] font-medium'
                                    }`}
                                  >
                                    {sub.label}
                                  </Link>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    }

                    // Standard direct link item
                    return (
                      <Link
                        key={item.id}
                        to={item.to}
                        onClick={onCloseMobile}
                        className={`flex items-center gap-3 px-3.5 py-2.5 text-[13px] transition-colors group ${
                          active
                            ? 'bg-[#1D61E7] text-white font-semibold shadow-xs'
                            : 'text-[#1E293B] hover:bg-[#F8FAFC]'
                        }`}
                      >
                        <span
                          className={
                            active
                              ? 'text-white'
                              : 'text-[#334155] group-hover:text-[#0F172A]'
                          }
                        >
                          {item.icon}
                        </span>
                        <span className="truncate flex-1 font-medium">{item.label}</span>
                      </Link>
                    );
                  })}
                </div>
              </div>
            ) : (
              /* Collapsed Section */
              <div className="bg-white rounded-xl border border-[#E2E8F0] shadow-xs py-1 space-y-1">
                {section.items.map((item) => {
                  const active = isItemActive(item);

                  if (item.soon || !item.to) {
                    return (
                      <div
                        key={item.id}
                        title={`${item.label} (Coming Soon)`}
                        className="w-10 h-10 rounded-lg flex items-center justify-center mx-auto text-[#CBD5E1] cursor-not-allowed select-none"
                      >
                        {item.icon}
                      </div>
                    );
                  }

                  return (
                    <Link
                      key={item.id}
                      to={item.to}
                      onClick={onCloseMobile}
                      title={item.label}
                      className={`w-10 h-10 rounded-lg flex items-center justify-center mx-auto transition-colors ${
                        active
                          ? 'bg-[#1D61E7] text-white font-semibold shadow-xs'
                          : 'text-[#334155] hover:bg-[#F1F5F9] hover:text-[#0F172A]'
                      }`}
                    >
                      {item.icon}
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </nav>

      {/* ── Bottom Footer with Collapse Sidebar ──────────────────────── */}
      <div className="p-3 border-t border-[#E2E8F0] bg-white shrink-0">
        <button
          type="button"
          onClick={() => setCollapsed(!collapsed)}
          className={`w-full hidden lg:flex items-center gap-3 px-2 py-1.5 rounded-xl text-left hover:bg-[#F1F5F9] transition-colors group cursor-pointer ${
            collapsed ? 'justify-center' : ''
          }`}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <div className="w-7 h-7 rounded-lg bg-[#EBF3FE] text-[#2563EB] flex items-center justify-center shrink-0 group-hover:bg-[#DBEAFE] transition-colors">
            {collapsed ? <ChevronsRight size={15} /> : <ChevronsLeft size={15} />}
          </div>
          {!collapsed && (
            <span className="text-[13px] font-medium text-[#1E293B] group-hover:text-blue-600 transition-colors truncate">
              Collapse Sidebar
            </span>
          )}
        </button>

        {/* Mobile footer text */}
        <div className="lg:hidden text-center py-1">
          <p className="text-[10.5px] font-medium text-[#64748B]">RIO Campus Assistant</p>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Persistent Sidebar */}
      <aside
        className={`hidden lg:flex flex-col min-h-screen shrink-0 sticky top-0 h-screen z-20 transition-all duration-200 ${
          collapsed ? 'w-[76px]' : 'w-[272px]'
        }`}
      >
        {sidebarContent}
      </aside>

      {/* Mobile Slide-Over Drawer */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs transition-opacity"
            onClick={onCloseMobile}
            aria-hidden="true"
          />
          {/* Drawer container */}
          <div className="relative flex flex-col w-[280px] max-w-[85vw] h-full shadow-2xl z-10 animate-in slide-in-from-left duration-200">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
};
