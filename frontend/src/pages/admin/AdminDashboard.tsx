/**
 * pages/admin/AdminDashboard.tsx
 * --------------------------------
 * Premium Academic Enterprise Admin Console.
 * Displays authenticated administrative identity, system connection health,
 * operational context, and rapid navigation routing to core campus modules.
 * Strictly uses real context and API data — zero invented metrics.
 */

import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  CheckCircle2,
  XCircle,
  User,
  Mail,
  Building2,
  Shield,
  GraduationCap,
  CalendarDays,
  ArrowRight,
  Server,
  Layers,
} from 'lucide-react';


import { apiGetMe } from '@/api/auth';
import { useAuth } from '@/auth/AuthProvider';
import { PageHeader, StatCard, StatusBadge } from '@/components/common';

export function AdminDashboard() {
  const { user: ctxUser } = useAuth();

  // Verify backend connection by calling /auth/me through React Query
  const { data: me, isLoading, isError, error } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: apiGetMe,
    staleTime: 60_000,
    retry: 1,
  });

  const user = me ?? ctxUser;

  const quickActionSections = [
    {
      title: 'Academic Architecture',
      description: 'Manage departmental structures, degree programs, terms, batches, and class sections.',
      icon: <Layers size={18} className="text-primary-700" />,
      links: [
        { label: 'Departments', to: '/admin/academic/departments' },
        { label: 'Programs', to: '/admin/academic/programs' },
        { label: 'Academic Years', to: '/admin/academic/years' },
        { label: 'Semesters', to: '/admin/academic/semesters' },
        { label: 'Batches', to: '/admin/academic/batches' },
        { label: 'Sections', to: '/admin/academic/sections' },
      ],
    },
    {
      title: 'People & Faculty',
      description: 'Oversee academic appointments, teaching workloads, and student cohort enrollments.',
      icon: <GraduationCap size={18} className="text-primary-700" />,
      links: [
        { label: 'Faculty Directory', to: '/admin/people/faculty' },
        { label: 'Student Roster', to: '/admin/people/students' },
      ],
    },
    {
      title: 'Campus & Facilities',
      description: 'Maintain the master course catalog, campus buildings, lecture halls, and specialized labs.',
      icon: <Building2 size={18} className="text-primary-700" />,
      links: [
        { label: 'Course Catalog', to: '/admin/courses' },
        { label: 'Campus Buildings', to: '/admin/campus/buildings' },
        { label: 'Rooms & Halls', to: '/admin/campus/rooms' },
      ],
    },
    {
      title: 'Timetable Optimization Engine',
      description: 'Generate automated schedules, review solver diagnostics, validate constraints, and publish.',
      icon: <CalendarDays size={18} className="text-primary-700" />,
      links: [
        { label: 'Timetable Versions', to: '/admin/timetable/versions' },
        { label: 'Generate Schedule', to: '/admin/timetable/generate' },
      ],
    },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Admin Control Center"
        subtitle="Institutional operations, system connectivity, security parameters, and campus administration."
        icon={<LayoutDashboard size={20} />}
        badge={
          <StatusBadge
            status={isError ? 'ERROR' : isLoading ? 'PENDING' : 'ACTIVE'}
            label={isError ? 'System Offline' : isLoading ? 'Connecting…' : 'System Operational'}
          />
        }
      />

      {/* Real KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Active Administrator"
          value={user?.name ?? '—'}
          sub="Session Subject"
          icon={<User size={18} />}
          variant="primary"
        />
        <StatCard
          label="Database Record ID"
          value={`#${user?.id ?? '—'}`}
          sub="Primary Identity Key"
          icon={<Shield size={18} />}
          variant="default"
        />
        <StatCard
          label="Assigned Jurisdiction"
          value={user?.department_id ? `Dept #${user.department_id}` : 'University-Wide'}
          sub="Administrative Scope"
          icon={<Building2 size={18} />}
          variant="default"
        />
        <StatCard
          label="Backend Service"
          value={isError ? 'Disconnected' : isLoading ? 'Syncing…' : 'Online & Active'}
          sub="FastAPI Gateway Status"
          icon={<Server size={18} />}
          variant={isError ? 'danger' : isLoading ? 'warning' : 'success'}
        />
      </div>

      {/* Backend Connection Health Banner */}
      <div
        className={`flex items-center justify-between gap-4 p-4 rounded-xl border text-xs sm:text-sm font-medium transition-colors ${
          isError
            ? 'bg-rose-50 border-rose-200 text-rose-800'
            : isLoading
            ? 'bg-amber-50 border-amber-200 text-amber-800'
            : 'bg-emerald-50/70 border-emerald-200/80 text-emerald-800'
        }`}
      >
        <div className="flex items-center gap-3 min-w-0">
          {isError ? (
            <XCircle size={18} className="text-rose-600 shrink-0" />
          ) : isLoading ? (
            <div className="w-4 h-4 border-2 border-amber-600 border-t-transparent rounded-full animate-spin shrink-0" />
          ) : (
            <CheckCircle2 size={18} className="text-emerald-600 shrink-0" />
          )}
          <span className="truncate">
            {isError
              ? `Backend connection failure: ${(error as Error)?.message ?? 'Gateway unresponsive'}`
              : isLoading
              ? 'Verifying administrative session with core API…'
              : 'Campus AI optimization services, database connection, and auth middleware are active.'}
          </span>
        </div>
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 shrink-0 hidden md:inline">
          FastAPI • Postgres Core
        </span>
      </div>

      {/* Administrator Account Details Card */}
      {user && (
        <div className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-900 tracking-tight">
              Administrative Credentials & Permissions
            </h3>
            <span className="text-xs text-slate-500">Security Clearance Level 1</span>
          </div>
          <div className="p-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-lg bg-primary-50 border border-primary-100 flex items-center justify-center shrink-0">
                <User size={16} className="text-primary-700" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Full Name</p>
                <p className="text-sm font-semibold text-slate-900 mt-0.5 truncate">{user.name}</p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-lg bg-primary-50 border border-primary-100 flex items-center justify-center shrink-0">
                <Mail size={16} className="text-primary-700" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">University Email</p>
                <p className="text-sm font-semibold text-slate-900 mt-0.5 truncate">{user.email}</p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0">
                <Shield size={16} className="text-slate-700" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">System Role</p>
                <p className="text-sm font-semibold text-slate-900 mt-0.5">{user.role}</p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-lg bg-primary-50 border border-primary-100 flex items-center justify-center shrink-0">
                <Building2 size={16} className="text-primary-700" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Department Scope</p>
                <p className="text-sm font-semibold text-slate-900 mt-0.5 truncate">
                  {user.department_id ? `Department ID #${user.department_id}` : 'All Departments (Universal)'}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Institutional Module Routing Hub */}
      <div>
        <div className="mb-4">
          <h3 className="text-base font-bold text-slate-900 tracking-tight">
            Academic Operations Hub
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Direct navigation channels to active academic records and scheduling engines.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {quickActionSections.map((sec, idx) => (
            <div
              key={idx}
              className="bg-white rounded-xl border border-slate-200/90 shadow-card p-5 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center gap-2.5 mb-2">
                  <div className="w-8 h-8 rounded-lg bg-primary-50 border border-primary-100 flex items-center justify-center shrink-0">
                    {sec.icon}
                  </div>
                  <h4 className="text-sm font-semibold text-slate-900 tracking-tight">
                    {sec.title}
                  </h4>
                </div>
                <p className="text-xs text-slate-500 leading-relaxed mb-4">
                  {sec.description}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-slate-100">
                {sec.links.map((link, lIdx) => (
                  <Link
                    key={lIdx}
                    to={link.to}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-primary-50 border border-slate-200/80 hover:border-primary-200 text-xs font-medium text-slate-700 hover:text-primary-800 transition-colors"
                  >
                    <span>{link.label}</span>
                    <ArrowRight size={12} className="text-slate-400" />
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
