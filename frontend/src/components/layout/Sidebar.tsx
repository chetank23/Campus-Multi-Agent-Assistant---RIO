import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  GraduationCap,
  Users,
  Building2,
  CalendarDays,
  Sparkles,
  Layers,
  History,
  Clock,
  UploadCloud,
  BarChart3,
  ShieldCheck,
  ClipboardList,
  Settings,
  Boxes,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  X,
} from 'lucide-react';
import type { UserRole } from '@/auth/auth.types';

interface SubNavItem {
  label: string;
  to: string;
}

interface NavItem {
  label: string;
  icon: React.ReactNode;
  to: string;
  implemented: boolean;
  subItems?: SubNavItem[];
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
          groupTitle: 'GENERAL',
          items: [
            {
              label: 'Dashboard',
              icon: <LayoutDashboard size={18} />,
              to: '/admin',
              implemented: true,
            },
          ],
        },
        {
          groupTitle: 'ACADEMIC MANAGEMENT',
          items: [
            {
              label: 'Departments & Programs',
              icon: <Layers size={18} />,
              to: '/admin/academic/departments',
              implemented: true,
              subItems: [
                { label: 'Departments', to: '/admin/academic/departments' },
                { label: 'Programs', to: '/admin/academic/programs' },
                { label: 'Academic Years', to: '/admin/academic/years' },
                { label: 'Semesters', to: '/admin/academic/semesters' },
              ],
            },
            {
              label: 'Students & Sections',
              icon: <Users size={18} />,
              to: '/admin/people/students',
              implemented: true,
              subItems: [
                { label: 'Students Roster', to: '/admin/people/students' },
                { label: 'Sections', to: '/admin/academic/sections' },
                { label: 'Batches', to: '/admin/academic/batches' },
              ],
            },
            {
              label: 'Faculty & Courses',
              icon: <GraduationCap size={18} />,
              to: '/admin/people/faculty',
              implemented: true,
              subItems: [
                { label: 'Faculty Directory', to: '/admin/people/faculty' },
                { label: 'Course Catalog', to: '/admin/courses' },
              ],
            },
          ],
        },
        {
          groupTitle: 'TIMETABLE ENGINE',
          items: [
            {
              label: 'Timetable Workspace',
              icon: <CalendarDays size={18} />,
              to: '/admin/timetable/versions',
              implemented: true,
            },
            {
              label: 'Generation & Conflicts',
              icon: <Sparkles size={18} />,
              to: '/admin/timetable/generate',
              implemented: true,
            },
            {
              label: 'Versions & Publishing',
              icon: <History size={18} />,
              to: '/admin/timetable/versions',
              implemented: true,
            },
          ],
        },
        {
          groupTitle: 'CAMPUS INFRASTRUCTURE',
          items: [
            {
              label: 'Buildings, Rooms & Labs',
              icon: <Building2 size={18} />,
              to: '/admin/campus/buildings',
              implemented: true,
              subItems: [
                { label: 'Buildings', to: '/admin/campus/buildings' },
                { label: 'Rooms & Labs', to: '/admin/campus/rooms' },
              ],
            },
            {
              label: 'Resource Management',
              icon: <Boxes size={18} />,
              to: '/admin/resources',
              implemented: true,
            },
            {
              label: 'Time Slots & Calendar',
              icon: <Clock size={18} />,
              to: '/admin/academic/semesters',
              implemented: true,
            },
          ],
        },
        {
          groupTitle: 'DATA & INTEGRATION',
          items: [
            {
              label: 'Import & Validation',
              icon: <UploadCloud size={18} />,
              to: '/admin/campus/rooms',
              implemented: true,
            },
            {
              label: 'Reports & Analytics',
              icon: <BarChart3 size={18} />,
              to: '/admin/resources',
              implemented: false,
            },
          ],
        },
        {
          groupTitle: 'SYSTEM',
          items: [
            {
              label: 'Users & Roles',
              icon: <ShieldCheck size={18} />,
              to: '/admin/audit',
              implemented: false,
            },
            {
              label: 'Audit Logs',
              icon: <ClipboardList size={18} />,
              to: '/admin/audit',
              implemented: false,
            },
            {
              label: 'Settings',
              icon: <Settings size={18} />,
              to: '/admin/resources',
              implemented: false,
            },
          ],
        },
      ];
    case 'FACULTY':
      return [
        {
          groupTitle: 'GENERAL',
          items: [
            { label: 'Dashboard', icon: <LayoutDashboard size={18} />, to: '/faculty', implemented: true },
          ],
        },
        {
          groupTitle: 'SCHEDULES & TEACHING',
          items: [
            { label: 'My Timetable', icon: <CalendarDays size={18} />, to: '/faculty/timetable', implemented: true },
            { label: 'Dept. Timetable', icon: <Building2 size={18} />, to: '/faculty/dept-timetable', implemented: false },
          ],
        },
      ];
    case 'STUDENT':
      return [
        {
          groupTitle: 'GENERAL',
          items: [
            { label: 'Dashboard', icon: <LayoutDashboard size={18} />, to: '/student', implemented: true },
          ],
        },
        {
          groupTitle: 'ACADEMIC SCHEDULE',
          items: [
            { label: 'My Timetable', icon: <CalendarDays size={18} />, to: '/student/timetable', implemented: true },
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
  const [collapsed, setCollapsed] = useState(false);
  const [expandedItems, setExpandedItems] = useState<Record<string, boolean>>({});
  const navGroups = getNavGroups(role);

  const toggleExpand = (label: string) => {
    setExpandedItems((prev) => ({
      ...prev,
      [label]: !prev[label],
    }));
  };

  const isItemActive = (item: NavItem): boolean => {
    if (item.to === '/admin' || item.to === '/faculty' || item.to === '/student') {
      return location.pathname === item.to;
    }
    if (item.subItems) {
      return item.subItems.some((sub) => location.pathname === sub.to || location.pathname.startsWith(sub.to));
    }
    return location.pathname === item.to || location.pathname.startsWith(item.to);
  };

  const sidebarContent = (
    <div className="flex flex-col h-full bg-[#10243A] text-[#F4F7FB] border-r border-[#2B4057] select-none">
      {/* Brand Header */}
      <div className="h-[70px] flex items-center justify-between px-5 border-b border-[#2B4057] shrink-0 bg-[#10243A]">
        <Link to={role === 'ADMIN' ? '/admin' : role === 'FACULTY' ? '/faculty' : '/student'} className="flex items-center gap-3 min-w-0 group">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center shrink-0 text-[#36BDB2] group-hover:scale-105 transition-transform">
            <GraduationCap size={22} className="text-[#36BDB2]" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <span className="text-xl font-extrabold text-white tracking-tight leading-none block">
                RIO
              </span>
              <p className="text-[10px] text-[#B8C7D9] leading-tight mt-0.5 font-normal tracking-wide">
                Campus Assistant<br />& Timetable Engine
              </p>
            </div>
          )}
        </Link>

        {/* Mobile close button */}
        {onCloseMobile && (
          <button
            type="button"
            onClick={onCloseMobile}
            className="lg:hidden p-1.5 rounded-lg text-[#B8C7D9] hover:text-white hover:bg-[#1D3B5C] transition-colors"
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        )}
      </div>

      {/* Navigation Groups */}
      <nav className="flex-1 overflow-y-auto py-3 px-3 space-y-4 scrollbar-thin">
        {navGroups.map((group, gIdx) => (
          <div key={gIdx} className="space-y-1">
            {group.groupTitle && !collapsed && (
              <p className="px-3 text-[10px] font-bold uppercase tracking-wider text-[#8190A5] mb-1.5">
                {group.groupTitle}
              </p>
            )}
            {group.groupTitle && collapsed && (
              <div className="h-px bg-[#2B4057] my-2 mx-1" />
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const active = isItemActive(item);
                const hasSub = item.subItems && item.subItems.length > 0;
                const isExpanded = !!expandedItems[item.label] || active;

                if (item.implemented) {
                  return (
                    <div key={item.label} className="space-y-0.5">
                      <div className="flex items-center">
                        <Link
                          to={item.to}
                          onClick={onCloseMobile}
                          title={collapsed ? item.label : undefined}
                          className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-colors w-full group ${
                            active
                              ? 'bg-[#2B568F] text-white font-semibold shadow-xs'
                              : 'text-[#B8C7D9] hover:bg-[#1D3B5C] hover:text-[#F4F7FB]'
                          }`}
                        >
                          <span
                            className={`shrink-0 transition-colors ${
                              active ? 'text-white' : 'text-[#B8C7D9] group-hover:text-white'
                            }`}
                          >
                            {item.icon}
                          </span>
                          {!collapsed && (
                            <span className="truncate flex-1 text-left">{item.label}</span>
                          )}
                        </Link>
                        {hasSub && !collapsed && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.preventDefault();
                              toggleExpand(item.label);
                            }}
                            className="p-1.5 text-[#B8C7D9] hover:text-white rounded-md hover:bg-[#1D3B5C] transition-colors"
                            aria-label={`Toggle ${item.label} submenu`}
                          >
                            <ChevronDown
                              size={13}
                              className={`transition-transform duration-200 ${
                                isExpanded ? 'rotate-180' : ''
                              }`}
                            />
                          </button>
                        )}
                      </div>

                      {/* Sub-items for fast child navigation */}
                      {hasSub && !collapsed && isExpanded && (
                        <div className="pl-9 pr-2 py-1 space-y-1">
                          {item.subItems!.map((sub) => {
                            const isSubActive = location.pathname === sub.to;
                            return (
                              <Link
                                key={sub.to}
                                to={sub.to}
                                onClick={onCloseMobile}
                                className={`block px-2.5 py-1 rounded text-[11px] transition-colors truncate ${
                                  isSubActive
                                    ? 'bg-[#1D3B5C] text-white font-semibold'
                                    : 'text-[#8190A5] hover:text-white hover:bg-[#142B43]'
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

                return (
                  <div
                    key={item.label}
                    className="flex items-center gap-3 px-3 py-2 rounded-lg text-xs text-[#8190A5]/60 cursor-not-allowed select-none transition-colors"
                    title="Module scheduled for upcoming deployment"
                  >
                    <span className="shrink-0 text-[#8190A5]/60">{item.icon}</span>
                    {!collapsed && (
                      <>
                        <span className="truncate">{item.label}</span>
                        <span className="ml-auto text-[9px] font-semibold uppercase tracking-wider bg-[#142B43] text-[#8190A5] px-1.5 py-0.2 rounded border border-[#2B4057]">
                          Soon
                        </span>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Collapse Sidebar Footer Toggle */}
      <div className="p-3 border-t border-[#2B4057] bg-[#10243A] shrink-0">
        <button
          type="button"
          onClick={() => setCollapsed(!collapsed)}
          className="w-full hidden lg:flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-[#B8C7D9] hover:text-white hover:bg-[#1D3B5C] transition-colors"
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          {!collapsed && <span>Collapse Sidebar</span>}
        </button>
        <div className="lg:hidden text-center py-1">
          <p className="text-[10px] text-[#8190A5]">RIO ERP System</p>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Persistent Sidebar */}
      <aside
        className={`hidden lg:flex flex-col min-h-screen shrink-0 sticky top-0 h-screen z-20 transition-all duration-200 ${
          collapsed ? 'w-[72px]' : 'w-[250px]'
        }`}
      >
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
          <div className="relative flex flex-col w-[260px] max-w-[85vw] h-full shadow-2xl z-10 animate-in slide-in-from-left duration-200">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
};
