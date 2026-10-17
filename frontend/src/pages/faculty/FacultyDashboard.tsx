/**
 * pages/faculty/FacultyDashboard.tsx
 * ------------------------------------
 * Faculty dashboard with real authenticated identity and published schedule integration.
 */

import React from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  CalendarDays,
  Clock,
  BookOpen,
  Users,
  MapPin,
  ArrowRight,
  User,
  Mail,
  Building2,
  GraduationCap,
} from 'lucide-react';
import { apiGetMe } from '@/api/auth';
import { getFacultyMyTimetable } from '@/api/timetable';
import { useAuth } from '@/auth/AuthProvider';
import { PageHeader, StatCard, StatusBadge, LoadingState } from '@/components/common';
import { formatTime12h } from '@/utils/timeFormatter';

export function FacultyDashboard() {
  const { user: ctxUser } = useAuth();

  const { data: me, isLoading: isUserLoading } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: apiGetMe,
    staleTime: 60_000,
  });

  const { data: timetable, isLoading: isTimetableLoading } = useQuery({
    queryKey: ['faculty', 'my-timetable'],
    queryFn: () => getFacultyMyTimetable(),
    staleTime: 60_000,
  });

  const user = me ?? ctxUser;
  const entries = timetable?.entries || [];

  // Determine current day of week (MON, TUE, WED, THU, FRI, SAT)
  const todayKey = React.useMemo(() => {
    const dayIndex = new Date().getDay();
    const days = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
    return days[dayIndex] || 'MON';
  }, []);

  const todayEntries = React.useMemo(() => {
    return entries.filter((e) => {
      const d = (e.day || '').toUpperCase();
      return d.startsWith(todayKey);
    });
  }, [entries, todayKey]);

  const distinctCourses = React.useMemo(() => {
    const set = new Set<string>();
    entries.forEach((e) => {
      if (e.course_code) set.add(e.course_code);
    });
    return set.size;
  }, [entries]);

  const distinctSections = React.useMemo(() => {
    const set = new Set<string>();
    entries.forEach((e) => {
      if (e.section_name) set.add(`${e.section_name}-${e.batch_name || 'all'}`);
    });
    return set.size;
  }, [entries]);

  if (isUserLoading && !user) {
    return <LoadingState message="Connecting to faculty portal…" />;
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <PageHeader
        title={`Welcome, ${user?.name || 'Faculty Member'}`}
        subtitle={
          timetable?.designation && timetable?.department_name
            ? `${timetable.designation} • Department of ${timetable.department_name}`
            : 'Faculty Academic Portal • Teaching Schedule & Allocations'
        }
        actions={
          <Link
            to="/faculty/timetable"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold uppercase tracking-wider transition-colors shadow-xs"
          >
            <CalendarDays size={14} />
            <span>View Full Timetable</span>
            <ArrowRight size={13} />
          </Link>
        }
      />

      {/* KPI Cards Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Weekly Load"
          value={timetable?.total_teaching_hours ?? entries.length}
          sub="Teaching periods / week"
          icon={<Clock size={20} />}
          variant="primary"
        />
        <StatCard
          label="Assigned Courses"
          value={distinctCourses}
          sub="Unique subjects"
          icon={<BookOpen size={20} />}
          variant="default"
        />
        <StatCard
          label="Active Groups"
          value={distinctSections}
          sub="Sections & batches"
          icon={<Users size={20} />}
          variant="warning"
        />
        <StatCard
          label="Today's Classes"
          value={todayEntries.length}
          sub={`Scheduled for today (${todayKey})`}
          icon={<CalendarDays size={20} />}
          variant={todayEntries.length > 0 ? 'primary' : 'default'}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Today's Schedule Card */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CalendarDays size={16} className="text-primary-600" />
              <h3 className="text-sm font-bold text-slate-900">Today's Class Schedule</h3>
            </div>
            <span className="text-xs font-semibold text-slate-500 font-tabular">
              {todayEntries.length} {todayEntries.length === 1 ? 'session' : 'sessions'}
            </span>
          </div>

          <div className="p-5">
            {isTimetableLoading ? (
              <LoadingState message="Checking today's schedule…" />
            ) : todayEntries.length === 0 ? (
              <div className="text-center py-8">
                <div className="w-10 h-10 rounded-xl bg-slate-100 text-slate-400 mx-auto flex items-center justify-center mb-2">
                  <CalendarDays size={20} />
                </div>
                <p className="text-sm font-semibold text-slate-800">No classes scheduled today</p>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                  {entries.length > 0
                    ? `You have ${entries.length} weekly sessions scheduled on other days.`
                    : 'No published timetable entries found for your account.'}
                </p>
                {entries.length > 0 && (
                  <Link
                    to="/faculty/timetable"
                    className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary-600 hover:text-primary-700 mt-3"
                  >
                    <span>Check weekly schedule</span>
                    <ArrowRight size={13} />
                  </Link>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                {todayEntries.map((e) => {
                  const isLab =
                    e.slot_type === 'LAB' ||
                    e.course_type === 'LAB' ||
                    e.course_type === 'PRACTICAL';
                  return (
                    <div
                      key={e.id}
                      className="p-3.5 rounded-xl border border-slate-200/80 hover:border-slate-300 transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-lg bg-primary-50 border border-primary-100 text-primary-700 flex items-center justify-center shrink-0">
                          <Clock size={16} />
                        </div>
                        <div>
                          <div className="text-xs font-bold text-slate-900 font-tabular">
                            {formatTime12h(e.start_time)} – {formatTime12h(e.end_time)}
                          </div>
                          <div className="text-[11px] text-slate-500">
                            {e.course_code}: <span className="font-semibold text-slate-800">{e.course_name}</span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-3 text-xs text-slate-600">
                        {e.room_number && (
                          <div className="flex items-center gap-1">
                            <MapPin size={12} className="text-slate-400" />
                            <span className="font-semibold text-slate-800">{e.room_number}</span>
                          </div>
                        )}
                        {e.section_name && (
                          <div className="flex items-center gap-1">
                            <Users size={12} className="text-slate-400" />
                            <span>Sec {e.section_name}</span>
                            {e.batch_name && <span className="font-semibold">[{e.batch_name}]</span>}
                          </div>
                        )}
                        <StatusBadge
                          variant={isLab ? 'warning' : 'primary'}
                          label={isLab ? 'Lab' : 'Lecture'}
                          size="sm"
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Faculty Account Details Card */}
        <div className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/50 flex items-center gap-2">
            <GraduationCap size={16} className="text-primary-600" />
            <h3 className="text-sm font-bold text-slate-900">Faculty Profile</h3>
          </div>
          <div className="p-5 space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center shrink-0">
                <User size={15} />
              </div>
              <div className="min-w-0">
                <p className="text-xs text-slate-400">Full Name</p>
                <p className="text-sm font-semibold text-slate-900 truncate">{user?.name}</p>
                {timetable?.designation && (
                  <p className="text-xs text-primary-700 font-medium">{timetable.designation}</p>
                )}
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center shrink-0">
                <Mail size={15} />
              </div>
              <div className="min-w-0">
                <p className="text-xs text-slate-400">Campus Email</p>
                <p className="text-sm font-semibold text-slate-900 break-all">{user?.email}</p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center shrink-0">
                <Building2 size={15} />
              </div>
              <div className="min-w-0">
                <p className="text-xs text-slate-400">Department</p>
                <p className="text-sm font-semibold text-slate-900">
                  {timetable?.department_name || (user?.department_id ? `Dept #${user.department_id}` : 'General')}
                </p>
              </div>
            </div>

            {timetable?.faculty_code && (
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center shrink-0">
                  <GraduationCap size={15} />
                </div>
                <div className="min-w-0">
                  <p className="text-xs text-slate-400">Faculty ID</p>
                  <p className="text-sm font-semibold text-slate-900 font-tabular">{timetable.faculty_code}</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
export default FacultyDashboard;
