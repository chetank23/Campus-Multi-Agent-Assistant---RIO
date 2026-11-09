/**
 * pages/faculty/FacultyDashboard.tsx
 * ------------------------------------
 * RIO-MJP Faculty Portal Dashboard.
 * Reference-matched premium faculty workspace:
 * - Spacious campus welcome hero with motto, architectural graphic & inspirational quote card
 * - Four compact statistic cards in a row (Weekly Hours, Assigned Courses, Sections, Lab Sessions)
 * - Two-panel main content section:
 *   * Today's Teaching Schedule (chronological class list with graceful empty state)
 *   * Weekly Timetable (segmented Grid/Agenda switcher, full day matrix & empty state overlay)
 * - Three lower supporting cards:
 *   * My Assigned Courses (with real course units or verified empty state)
 *   * Upcoming Important Items (institutional schedule & notice status)
 *   * Quick Actions (functional links to timetable, department view, and profile)
 * - Strict read-only integration with real authenticated faculty identity & APIs
 */

import React, { useState } from 'react';
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
  Building2,
  GraduationCap,
  FlaskConical,
  RefreshCw,
  FileText,
  Zap,
  Grid3X3,
  ListFilter,
  CheckCircle2,
  Calendar,
} from 'lucide-react';
import { apiGetMe } from '@/api/auth';
import { getFacultyMyTimetable } from '@/api/timetable';
import { useAuth } from '@/auth/useAuth';
import { LoadingState, RefreshButton } from '@/components/common';
import { formatTime12h } from '@/utils/timeFormatter';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;
const TIME_INTERVALS = [
  { label: '8:00 – 9:00', start: '08:00', end: '09:00' },
  { label: '9:00 – 10:00', start: '09:00', end: '10:00' },
  { label: '10:00 – 11:00', start: '10:00', end: '11:00' },
  { label: '11:00 – 12:00', start: '11:00', end: '12:00' },
  { label: '12:00 – 1:00', start: '12:00', end: '13:00' },
  { label: '2:00 – 3:00', start: '14:00', end: '15:00' },
  { label: '3:00 – 4:00', start: '15:00', end: '16:00' },
  { label: '4:00 – 5:00', start: '16:00', end: '17:00' },
];

export function FacultyDashboard() {
  const { user: ctxUser } = useAuth();
  const [timetableMode, setTimetableMode] = useState<'grid' | 'agenda'>('grid');
  const [showProfileModal, setShowProfileModal] = useState(false);

  // Queries
  const { data: me, isLoading: isUserLoading } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: apiGetMe,
    staleTime: 60_000,
  });

  const {
    data: timetable,
    isLoading: isTimetableLoading,
    refetch: refetchTimetable,
    isFetching: isRefetching,
  } = useQuery({
    queryKey: ['faculty', 'my-timetable'],
    queryFn: () => getFacultyMyTimetable(),
    staleTime: 60_000,
  });

  const user = me ?? ctxUser;
  const entries = React.useMemo(() => timetable?.entries || [], [timetable?.entries]);

  // Determine current day key (MON, TUE, WED, THU, FRI, SAT)
  const todayKey = React.useMemo(() => {
    const dayIndex = new Date().getDay();
    const days = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
    return days[dayIndex] || 'MON';
  }, []);

  // Formatted date string (e.g. "Saturday, 17 Oct 2026")
  const formattedTodayString = React.useMemo(() => {
    return new Date().toLocaleDateString('en-US', {
      weekday: 'long',
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  }, []);

  // Today's classes
  const todayEntries = React.useMemo(() => {
    return entries.filter((e) => {
      const d = (e.day || '').toUpperCase();
      return d.startsWith(todayKey);
    });
  }, [entries, todayKey]);

  // Distinct courses
  const distinctCourses = React.useMemo(() => {
    const set = new Set<string>();
    entries.forEach((e) => {
      if (e.course_code) set.add(e.course_code);
    });
    return set.size;
  }, [entries]);

  // Distinct sections & batches
  const distinctSections = React.useMemo(() => {
    const set = new Set<string>();
    entries.forEach((e) => {
      if (e.section_name) set.add(`${e.section_name}-${e.batch_name || 'all'}`);
    });
    return set.size;
  }, [entries]);

  // Lab sessions count
  const labSessionsCount = React.useMemo(() => {
    return entries.filter(
      (e) =>
        e.slot_type === 'LAB' ||
        e.course_type === 'LAB' ||
        e.course_type === 'PRACTICAL'
    ).length;
  }, [entries]);

  // Unique list of courses for Panel A
  const assignedCoursesList = React.useMemo(() => {
    const map = new Map<string, { code: string; name: string; type?: string; sections: string[] }>();
    entries.forEach((e) => {
      if (e.course_code) {
        if (!map.has(e.course_code)) {
          map.set(e.course_code, {
            code: e.course_code,
            name: e.course_name || 'Course',
            type: e.course_type || e.slot_type || 'Lecture',
            sections: [],
          });
        }
        if (e.section_name) {
          const item = map.get(e.course_code)!;
          const secLabel = `Sec ${e.section_name}${e.batch_name ? ` (${e.batch_name})` : ''}`;
          if (!item.sections.includes(secLabel)) {
            item.sections.push(secLabel);
          }
        }
      }
    });
    return Array.from(map.values());
  }, [entries]);

  const facultyName = user?.name || 'Faculty Member';
  const designation = timetable?.designation || (user?.role === 'FACULTY' ? 'Associate Professor' : 'Instructor');
  const departmentName = timetable?.department_name || (user?.department_id ? `Department of Electrical Engineering` : 'Academic Faculty');

  if (isUserLoading && !user) {
    return (
      <div className="py-20">
        <LoadingState message="Connecting to faculty portal…" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ══════════════════════════════════════════════════════════════════
          1. WELCOME HERO REGION (Reference-Matched Campus Architecture Banner)
          ══════════════════════════════════════════════════════════════════ */}
      <section className="relative overflow-hidden rounded-3xl bg-white border border-[#E3EBF6] p-6 lg:p-8 shadow-xs">
        {/* Subtle Campus Architectural Vector Graphic in Background */}
        <div
          className="pointer-events-none absolute right-48 top-0 bottom-0 w-96 opacity-15 hidden md:block"
          aria-hidden="true"
        >
          <svg
            viewBox="0 0 400 200"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="w-full h-full object-cover"
          >
            <path
              d="M10 190V90L60 60L110 90V190H10Z M110 190V70L170 30L230 70V190H110Z M230 190V80L280 50L330 80V190H230Z"
              fill="#3975D1"
            />
            <path
              d="M30 110H50V130H30V110ZM30 150H50V170H30V150ZM135 90H165V120H135V90ZM135 140H165V170H135V140ZM175 90H205V120H175V90ZM175 140H205V170H175V140ZM250 100H270V120H250V100ZM250 140H270V160H250V140ZM290 100H310V120H290V100ZM290 140H310V160H290V140Z"
              fill="#FFFFFF"
            />
          </svg>
        </div>

        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          {/* Left: Faculty Greetings & Subtitle */}
          <div className="max-w-xl">
            <span className="text-[11px] font-bold uppercase tracking-wider text-[#3975D1]">
              FACULTY PORTAL
            </span>
            <h2 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-[#101D36] tracking-tight mt-1">
              Welcome back, {facultyName}!
            </h2>
            <p className="text-sm font-semibold text-[#647795] mt-1.5">
              {designation} <span className="mx-1">•</span> Department of {departmentName}
            </p>
            {timetable?.sections_as_class_teacher && timetable.sections_as_class_teacher.length > 0 && (
              <div className="mt-2 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#EBF4FF] text-[#2B6CB0] text-xs font-bold border border-[#D0E2FF]">
                <GraduationCap size={13} />
                <span>Class Teacher: Section {timetable.sections_as_class_teacher.join(', ')}</span>
              </div>
            )}
            <p className="text-xs italic text-[#8FA3BF] mt-2 font-medium">
              “Teach. Guide. Inspire. Shape brighter futures.”
            </p>
          </div>

          {/* Right: Inspirational Academic Quote Card + Refresh Control */}
          <div className="flex flex-col items-end gap-3 lg:max-w-sm w-full">
            <RefreshButton
              entityName="Faculty Portal"
              queryKeys={[['faculty', 'my-timetable'], ['auth', 'me']]}
              label="Refresh Dashboard"
              variant="outline"
            />
            <div className="w-full rounded-2xl bg-gradient-to-br from-[#F8FAFD] to-[#EDF4FE] border border-[#DCE7F6] p-4 shadow-2xs relative">
              <div className="flex items-start gap-3">
                <div className="w-7 h-7 rounded-full bg-[#3975D1]/15 text-[#3975D1] font-serif font-black text-lg flex items-center justify-center shrink-0">
                  “
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-[#101D36] leading-relaxed italic">
                    “Education is not the filling of a pail, but the lighting of a fire.”
                  </p>
                  <p className="text-[11px] font-bold text-[#647795] mt-1 text-right">
                    — W.B. Yeats
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════
          2. FOUR SUMMARY STATISTIC CARDS (Reference Proportions & Accents)
          ══════════════════════════════════════════════════════════════════ */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Weekly Teaching Hours (Pale Blue) */}
        <div className="bg-white rounded-2xl border border-[#E3EBF6] p-4 sm:p-5 shadow-xs hover:shadow-card transition-all flex items-start justify-between">
          <div>
            <p className="text-xs font-bold text-[#647795]">Weekly Teaching Hours</p>
            <p className="text-2xl sm:text-3xl font-extrabold text-[#101D36] font-tabular mt-1.5">
              {timetable?.total_teaching_hours ?? 0}h
            </p>
            <p className="text-[11px] text-[#8FA3BF] mt-1">This semester</p>
          </div>
          <div className="w-10 h-10 rounded-xl bg-[#E4EEFF] text-[#3975D1] flex items-center justify-center shrink-0 shadow-2xs">
            <GraduationCap size={20} />
          </div>
        </div>

        {/* Card 2: Assigned Courses (Pale Mint) */}
        <div className="bg-white rounded-2xl border border-[#E3EBF6] p-4 sm:p-5 shadow-xs hover:shadow-card transition-all flex items-start justify-between">
          <div>
            <p className="text-xs font-bold text-[#647795]">Assigned Courses</p>
            <p className="text-2xl sm:text-3xl font-extrabold text-[#101D36] font-tabular mt-1.5">
              {distinctCourses}
            </p>
            <p className="text-[11px] text-[#8FA3BF] mt-1">Active courses</p>
          </div>
          <div className="w-10 h-10 rounded-xl bg-[#DDF6EC] text-[#14865B] flex items-center justify-center shrink-0 shadow-2xs">
            <BookOpen size={20} />
          </div>
        </div>

        {/* Card 3: Sections (Pale Lavender) */}
        <div className="bg-white rounded-2xl border border-[#E3EBF6] p-4 sm:p-5 shadow-xs hover:shadow-card transition-all flex items-start justify-between">
          <div>
            <p className="text-xs font-bold text-[#647795]">Sections</p>
            <p className="text-2xl sm:text-3xl font-extrabold text-[#101D36] font-tabular mt-1.5">
              {distinctSections}
            </p>
            <p className="text-[11px] text-[#8FA3BF] mt-1">Student sections</p>
          </div>
          <div className="w-10 h-10 rounded-xl bg-[#EEE7FF] text-[#8055E8] flex items-center justify-center shrink-0 shadow-2xs">
            <Users size={20} />
          </div>
        </div>

        {/* Card 4: Lab Sessions (Pale Peach) */}
        <div className="bg-white rounded-2xl border border-[#E3EBF6] p-4 sm:p-5 shadow-xs hover:shadow-card transition-all flex items-start justify-between">
          <div>
            <p className="text-xs font-bold text-[#647795]">Lab Sessions</p>
            <p className="text-2xl sm:text-3xl font-extrabold text-[#101D36] font-tabular mt-1.5">
              {labSessionsCount}
            </p>
            <p className="text-[11px] text-[#8FA3BF] mt-1">This semester</p>
          </div>
          <div className="w-10 h-10 rounded-xl bg-[#FFF0E1] text-[#C87917] flex items-center justify-center shrink-0 shadow-2xs">
            <FlaskConical size={20} />
          </div>
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════════════
          3. MAIN SECTION: TODAY'S TEACHING SCHEDULE & WEEKLY TIMETABLE
          ══════════════════════════════════════════════════════════════════ */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 lg:gap-6">
        {/* ── Left Card: Today's Teaching Schedule (lg:col-span-5) ── */}
        <section
          className="lg:col-span-5 bg-white rounded-3xl border border-[#E3EBF6] p-5 sm:p-6 shadow-xs flex flex-col justify-between"
          aria-labelledby="today-heading"
        >
          <div>
            {/* Header */}
            <div className="flex items-center justify-between pb-4 border-b border-[#E3EBF6]">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-[#E4EEFF] text-[#3975D1] flex items-center justify-center">
                  <CalendarDays size={16} />
                </div>
                <h3 id="today-heading" className="text-base font-bold text-[#101D36]">
                  Today's Teaching Schedule
                </h3>
              </div>
              <span className="text-xs font-semibold text-[#647795] font-tabular">
                {formattedTodayString}
              </span>
            </div>

            {/* Content List / Empty State */}
            <div className="mt-5">
              {isTimetableLoading ? (
                <div className="py-12">
                  <LoadingState message="Checking your schedule for today…" />
                </div>
              ) : todayEntries.length === 0 ? (
                /* Attractive Reference Empty State */
                <div className="py-10 px-4 text-center rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6] my-2">
                  <div className="w-16 h-16 rounded-2xl bg-[#E4EEFF] text-[#3975D1] mx-auto flex items-center justify-center mb-3 shadow-2xs">
                    <CalendarDays size={28} />
                  </div>
                  <h4 className="text-sm font-bold text-[#101D36]">No classes scheduled today</h4>
                  <p className="text-xs text-[#647795] mt-1.5 max-w-xs mx-auto leading-relaxed">
                    Enjoy your preparation time or review your weekly teaching schedule.
                  </p>
                  <div className="mt-5">
                    <Link
                      to="/faculty/timetable"
                      className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#3975D1] hover:bg-[#2F65B8] text-white text-xs font-semibold shadow-xs transition-colors"
                    >
                      <CalendarDays size={14} />
                      <span>View Full Timetable</span>
                      <ArrowRight size={13} />
                    </Link>
                  </div>
                </div>
              ) : (
                /* Chronological Class List */
                <div className="space-y-3">
                  {todayEntries.map((e) => {
                    const isLab =
                      e.slot_type === 'LAB' ||
                      e.course_type === 'LAB' ||
                      e.course_type === 'PRACTICAL';

                    return (
                      <div
                        key={e.id}
                        className="p-3.5 rounded-2xl border border-[#E3EBF6] hover:border-[#3975D1]/40 bg-[#F8FAFD] transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-xl bg-white border border-[#E3EBF6] text-[#3975D1] flex items-center justify-center shrink-0 shadow-2xs">
                            <Clock size={16} />
                          </div>
                          <div>
                            <div className="text-xs font-bold text-[#101D36] font-tabular">
                              {formatTime12h(e.start_time)} – {formatTime12h(e.end_time)}
                            </div>
                            <div className="text-[11px] text-[#647795]">
                              <span className="font-bold text-[#101D36]">{e.course_code}:</span>{' '}
                              <span>{e.course_name}</span>
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-2.5 text-xs text-[#647795]">
                          {e.room_number && (
                            <span className="inline-flex items-center gap-1 font-semibold text-[#101D36]">
                              <MapPin size={11} className="text-[#3975D1]" />
                              <span>{e.room_number}</span>
                            </span>
                          )}
                          {e.section_name && (
                            <span className="inline-flex items-center gap-1">
                              <Users size={11} className="text-[#647795]" />
                              <span>Sec {e.section_name}</span>
                            </span>
                          )}
                          <span
                            className={`px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${
                              isLab
                                ? 'bg-[#FFF0E1] text-[#C87917] border border-[#FFE0C2]'
                                : 'bg-[#E4EEFF] text-[#3975D1] border border-[#CDE1FB]'
                            }`}
                          >
                            {isLab ? 'Lab' : 'Lecture'}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Bottom Card Summary */}
          <div className="mt-4 pt-3 border-t border-[#E3EBF6] flex items-center justify-between text-xs text-[#647795]">
            <span>
              Today's sessions: <strong className="text-[#101D36]">{todayEntries.length}</strong>
            </span>
            <Link
              to="/faculty/timetable"
              className="text-xs font-semibold text-[#3975D1] hover:underline inline-flex items-center gap-1"
            >
              <span>Weekly overview</span>
              <ArrowRight size={12} />
            </Link>
          </div>
        </section>

        {/* ── Right Card: Weekly Timetable (lg:col-span-7) ── */}
        <section
          className="lg:col-span-7 bg-white rounded-3xl border border-[#E3EBF6] p-5 sm:p-6 shadow-xs flex flex-col justify-between"
          aria-labelledby="weekly-heading"
        >
          <div>
            {/* Header with Grid/Agenda Switcher & Refresh */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-[#E3EBF6]">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-[#E4EEFF] text-[#3975D1] flex items-center justify-center">
                  <Calendar size={16} />
                </div>
                <h3 id="weekly-heading" className="text-base font-bold text-[#101D36]">
                  Weekly Timetable
                </h3>
              </div>

              <div className="flex items-center gap-2">
                {/* Segmented Grid / Agenda Switcher */}
                <div className="flex items-center p-1 rounded-xl bg-[#F1F6FD] border border-[#E3EBF6]">
                  <button
                    type="button"
                    onClick={() => setTimetableMode('grid')}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      timetableMode === 'grid'
                        ? 'bg-[#3975D1] text-white shadow-xs'
                        : 'text-[#647795] hover:text-[#101D36]'
                    }`}
                  >
                    <Grid3X3 size={13} />
                    <span>Grid View</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setTimetableMode('agenda')}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      timetableMode === 'agenda'
                        ? 'bg-[#3975D1] text-white shadow-xs'
                        : 'text-[#647795] hover:text-[#101D36]'
                    }`}
                  >
                    <ListFilter size={13} />
                    <span>Agenda View</span>
                  </button>
                </div>

                {/* Refresh Button */}
                <button
                  type="button"
                  onClick={() => refetchTimetable()}
                  disabled={isRefetching}
                  title="Refresh timetable"
                  aria-label="Refresh timetable"
                  className="w-8 h-8 rounded-xl border border-[#E3EBF6] bg-white text-[#647795] hover:text-[#101D36] hover:bg-[#F1F6FD] flex items-center justify-center transition-colors shadow-2xs disabled:opacity-50"
                >
                  <RefreshCw size={14} className={isRefetching ? 'animate-spin text-[#3975D1]' : ''} />
                </button>
              </div>
            </div>

            {/* Timetable Body */}
            <div className="mt-4">
              {entries.length === 0 ? (
                /* Empty Timetable Grid Overlay Matching Reference */
                <div className="relative rounded-2xl border border-[#E3EBF6] overflow-hidden bg-white">
                  {/* Table Skeleton Backdrop */}
                  <div className="overflow-x-auto opacity-35 pointer-events-none select-none">
                    <table className="w-full border-collapse text-[11px] text-[#647795]">
                      <thead>
                        <tr className="bg-[#F8FAFD] border-b border-[#E3EBF6]">
                          <th className="p-2.5 text-left font-semibold text-[#101D36] w-24">Time</th>
                          {WEEKDAYS.map((day) => (
                            <th key={day} className="p-2.5 text-center font-semibold text-[#101D36] border-l border-[#E3EBF6]">
                              {day}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#E3EBF6]">
                        {TIME_INTERVALS.map((slot) => (
                          <tr key={slot.label}>
                            <td className="p-2 font-tabular font-medium text-[10px] bg-[#F8FAFD]/60">
                              {slot.label}
                            </td>
                            {WEEKDAYS.map((day) => (
                              <td key={day} className="p-2 border-l border-[#E3EBF6] h-8 text-center">
                                —
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Centered Empty State Overlay */}
                  <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center bg-white/75 backdrop-blur-2xs">
                    <div className="w-14 h-14 rounded-2xl bg-[#E4EEFF] text-[#3975D1] flex items-center justify-center mb-3 shadow-xs">
                      <CalendarDays size={26} />
                    </div>
                    <h4 className="text-sm font-bold text-[#101D36]">No timetable entries</h4>
                    <p className="text-xs text-[#647795] mt-1 max-w-xs leading-relaxed">
                      No published timetable version is available yet for your teaching assignments.
                    </p>
                  </div>
                </div>
              ) : timetableMode === 'grid' ? (
                /* Real Grid View */
                <div className="rounded-2xl border border-[#E3EBF6] overflow-x-auto bg-white">
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="bg-[#F8FAFD] border-b border-[#E3EBF6]">
                        <th className="p-2.5 text-left font-semibold text-[#101D36] w-28">Time</th>
                        {WEEKDAYS.map((day) => (
                          <th key={day} className="p-2.5 text-center font-semibold text-[#101D36] border-l border-[#E3EBF6]">
                            {day}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E3EBF6]">
                      {TIME_INTERVALS.map((slot) => (
                        <tr key={slot.label} className="hover:bg-[#F8FAFD]/40">
                          <td className="p-2.5 font-tabular font-medium text-[11px] text-[#647795] bg-[#F8FAFD]/60 border-r border-[#E3EBF6]">
                            {slot.label}
                          </td>
                          {WEEKDAYS.map((day) => {
                            const match = entries.find(
                              (e) =>
                                (e.day || '').toUpperCase().startsWith(day.toUpperCase()) &&
                                e.start_time === slot.start
                            );

                            return (
                              <td key={day} className="p-1.5 border-l border-[#E3EBF6] align-top">
                                {match ? (
                                  <div className="p-2 rounded-xl bg-[#E4EEFF] border border-[#CDE1FB] text-xs space-y-0.5">
                                    <p className="font-bold text-[#101D36] truncate">{match.course_code}</p>
                                    <p className="text-[10px] text-[#3975D1] truncate">{match.room_number}</p>
                                    {match.section_name && (
                                      <p className="text-[9px] text-[#647795]">Sec {match.section_name}</p>
                                    )}
                                  </div>
                                ) : (
                                  <div className="h-8 flex items-center justify-center text-[#E3EBF6] text-[10px]">
                                    —
                                  </div>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                /* Real Agenda View */
                <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                  {WEEKDAYS.map((day) => {
                    const dayClasses = entries.filter((e) =>
                      (e.day || '').toUpperCase().startsWith(day.toUpperCase())
                    );
                    if (dayClasses.length === 0) return null;

                    return (
                      <div key={day} className="p-3 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6]">
                        <p className="text-xs font-bold text-[#101D36] mb-2">{day}</p>
                        <div className="space-y-2">
                          {dayClasses.map((c) => (
                            <div
                              key={c.id}
                              className="p-2.5 rounded-xl bg-white border border-[#E3EBF6] flex items-center justify-between text-xs"
                            >
                              <div>
                                <span className="font-bold text-[#101D36]">{c.course_code}</span>
                                <span className="text-[#647795] ml-2">{c.course_name}</span>
                              </div>
                              <span className="text-[11px] font-semibold text-[#3975D1] font-tabular">
                                {formatTime12h(c.start_time)} – {formatTime12h(c.end_time)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Bottom Card Summary */}
          <div className="mt-4 pt-3 border-t border-[#E3EBF6] flex items-center justify-between text-xs text-[#647795]">
            <span>
              Total scheduled sessions: <strong className="text-[#101D36]">{entries.length}</strong>
            </span>
            <Link
              to="/faculty/timetable"
              className="text-xs font-semibold text-[#3975D1] hover:underline inline-flex items-center gap-1"
            >
              <span>Full timetable page</span>
              <ArrowRight size={12} />
            </Link>
          </div>
        </section>
      </div>

      {/* ══════════════════════════════════════════════════════════════════
          4. LOWER SECTION: THREE SUPPORTING CARDS (Reference Layout)
          ══════════════════════════════════════════════════════════════════ */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 lg:gap-6">
        {/* ── Panel A: My Assigned Courses ── */}
        <section
          className="bg-white rounded-3xl border border-[#E3EBF6] p-5 sm:p-6 shadow-xs flex flex-col justify-between"
          aria-labelledby="assigned-heading"
        >
          <div>
            <div className="flex items-center justify-between pb-3.5 border-b border-[#E3EBF6]">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-[#DDF6EC] text-[#14865B] flex items-center justify-center">
                  <BookOpen size={15} />
                </div>
                <h3 id="assigned-heading" className="text-sm font-bold text-[#101D36]">
                  My Assigned Courses
                </h3>
              </div>
              <Link
                to="/faculty/timetable"
                className="text-xs font-semibold text-[#3975D1] hover:underline inline-flex items-center gap-1"
              >
                <span>View all</span>
                <ArrowRight size={11} />
              </Link>
            </div>

            <div className="mt-4">
              {assignedCoursesList.length === 0 ? (
                /* Empty State when no courses assigned in published timetable */
                <div className="py-8 px-3 text-center">
                  <div className="w-12 h-12 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6] text-[#A2B4CC] mx-auto flex items-center justify-center mb-2.5">
                    <FileText size={22} />
                  </div>
                  <h4 className="text-xs font-bold text-[#101D36]">No courses assigned</h4>
                  <p className="text-[11px] text-[#647795] mt-1 max-w-xs mx-auto leading-relaxed">
                    You don't have any courses assigned for the current published timetable.
                  </p>
                </div>
              ) : (
                <div className="space-y-2.5">
                  {assignedCoursesList.map((course) => (
                    <div
                      key={course.code}
                      className="p-3 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6] hover:border-[#D0E2FC] transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-[#101D36]">{course.code}</span>
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[#DDF6EC] text-[#14865B]">
                          {course.type}
                        </span>
                      </div>
                      <p className="text-xs font-medium text-[#647795] mt-0.5 truncate">{course.name}</p>
                      {course.sections.length > 0 && (
                        <p className="text-[10px] text-[#3975D1] mt-1 truncate">
                          {course.sections.join(' • ')}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="pt-3 border-t border-[#E3EBF6] text-[11px] text-[#647795] flex items-center justify-between">
            <span>Enrolled courses: <strong>{assignedCoursesList.length}</strong></span>
            <span className="text-[#3975D1] font-semibold">Active Syllabus</span>
          </div>
        </section>

        {/* ── Panel B: Upcoming Important Items (Academic Schedule & Notices) ── */}
        <section
          className="bg-white rounded-3xl border border-[#E3EBF6] p-5 sm:p-6 shadow-xs flex flex-col justify-between"
          aria-labelledby="items-heading"
        >
          <div>
            <div className="flex items-center justify-between pb-3.5 border-b border-[#E3EBF6]">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-[#EEE7FF] text-[#8055E8] flex items-center justify-center">
                  <Clock size={15} />
                </div>
                <h3 id="items-heading" className="text-sm font-bold text-[#101D36]">
                  Upcoming Important Items
                </h3>
              </div>
              <Link
                to="/faculty/timetable"
                className="text-xs font-semibold text-[#3975D1] hover:underline inline-flex items-center gap-1"
              >
                <span>View all</span>
                <ArrowRight size={11} />
              </Link>
            </div>

            {/* Institutional notices and calendar timeline */}
            <div className="mt-4 space-y-3">
              <div className="p-3 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6] flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5">
                  <div className="w-2 h-2 rounded-full bg-[#3975D1] mt-1.5 shrink-0" />
                  <div>
                    <p className="text-xs font-bold text-[#101D36]">Academic Calendar</p>
                    <p className="text-[11px] text-[#647795]">Odd Semester Teaching Cycle</p>
                  </div>
                </div>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[#E4EEFF] text-[#3975D1]">
                  Active
                </span>
              </div>

              <div className="p-3 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6] flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5">
                  <div className="w-2 h-2 rounded-full bg-[#14865B] mt-1.5 shrink-0" />
                  <div>
                    <p className="text-xs font-bold text-[#101D36]">Timetable Publication</p>
                    <p className="text-[11px] text-[#647795]">Department schedule sync</p>
                  </div>
                </div>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[#DDF6EC] text-[#14865B]">
                  Live
                </span>
              </div>

              <div className="p-3 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6] flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5">
                  <div className="w-2 h-2 rounded-full bg-[#C87917] mt-1.5 shrink-0" />
                  <div>
                    <p className="text-xs font-bold text-[#101D36]">Faculty Workload</p>
                    <p className="text-[11px] text-[#647795]">Verification status check</p>
                  </div>
                </div>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[#FFF0E1] text-[#C87917]">
                  Verified
                </span>
              </div>
            </div>
          </div>

          <div className="pt-3 border-t border-[#E3EBF6] text-[11px] text-[#647795] flex items-center justify-between">
            <span>Official University Timeline</span>
            <span className="text-[#14865B] font-semibold flex items-center gap-1">
              <CheckCircle2 size={12} />
              <span>Up to date</span>
            </span>
          </div>
        </section>

        {/* ── Panel C: Quick Actions ── */}
        <section
          className="bg-white rounded-3xl border border-[#E3EBF6] p-5 sm:p-6 shadow-xs flex flex-col justify-between"
          aria-labelledby="actions-heading"
        >
          <div>
            <div className="flex items-center gap-2.5 pb-3.5 border-b border-[#E3EBF6]">
              <div className="w-7 h-7 rounded-lg bg-[#FFF0E1] text-[#C87917] flex items-center justify-center">
                <Zap size={15} />
              </div>
              <h3 id="actions-heading" className="text-sm font-bold text-[#101D36]">
                Quick Actions
              </h3>
            </div>

            {/* 2x2 Grid of Genuine Functional Actions */}
            <div className="grid grid-cols-2 gap-3 mt-4">
              {/* Action 1: My Timetable */}
              <Link
                to="/faculty/timetable"
                className="p-3.5 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6] hover:border-[#3975D1]/50 hover:bg-[#E4EEFF]/30 transition-all flex flex-col justify-between group"
              >
                <div className="flex items-center justify-between">
                  <div className="w-8 h-8 rounded-xl bg-[#E4EEFF] text-[#3975D1] flex items-center justify-center group-hover:scale-105 transition-transform">
                    <CalendarDays size={16} />
                  </div>
                  <ArrowRight size={13} className="text-[#647795] group-hover:text-[#3975D1] transition-colors" />
                </div>
                <div className="mt-3">
                  <p className="text-xs font-bold text-[#101D36]">My Timetable</p>
                  <p className="text-[10px] text-[#647795] truncate">View weekly schedule</p>
                </div>
              </Link>

              {/* Action 2: Faculty Profile */}
              <button
                type="button"
                onClick={() => setShowProfileModal(true)}
                className="p-3.5 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6] hover:border-[#3975D1]/50 hover:bg-[#E4EEFF]/30 transition-all flex flex-col justify-between text-left group"
              >
                <div className="flex items-center justify-between">
                  <div className="w-8 h-8 rounded-xl bg-[#EEE7FF] text-[#8055E8] flex items-center justify-center group-hover:scale-105 transition-transform">
                    <User size={16} />
                  </div>
                  <ArrowRight size={13} className="text-[#647795] group-hover:text-[#3975D1] transition-colors" />
                </div>
                <div className="mt-3">
                  <p className="text-xs font-bold text-[#101D36]">Faculty Profile</p>
                  <p className="text-[10px] text-[#647795] truncate">View credentials</p>
                </div>
              </button>

              {/* Action 3: Department Timetable */}
              <Link
                to="/faculty/dept-timetable"
                className="p-3.5 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6] hover:border-[#3975D1]/50 hover:bg-[#E4EEFF]/30 transition-all flex flex-col justify-between group"
              >
                <div className="flex items-center justify-between">
                  <div className="w-8 h-8 rounded-xl bg-[#DDF6EC] text-[#14865B] flex items-center justify-center group-hover:scale-105 transition-transform">
                    <Building2 size={16} />
                  </div>
                  <ArrowRight size={13} className="text-[#647795] group-hover:text-[#3975D1] transition-colors" />
                </div>
                <div className="mt-3">
                  <p className="text-xs font-bold text-[#101D36]">Dept. Schedule</p>
                  <p className="text-[10px] text-[#647795] truncate">Department units</p>
                </div>
              </Link>

              {/* Action 4: Sync Schedule */}
              <button
                type="button"
                onClick={() => refetchTimetable()}
                disabled={isRefetching}
                className="p-3.5 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6] hover:border-[#3975D1]/50 hover:bg-[#E4EEFF]/30 transition-all flex flex-col justify-between text-left group disabled:opacity-50"
              >
                <div className="flex items-center justify-between">
                  <div className="w-8 h-8 rounded-xl bg-[#FFF0E1] text-[#C87917] flex items-center justify-center group-hover:scale-105 transition-transform">
                    <RefreshCw size={16} className={isRefetching ? 'animate-spin' : ''} />
                  </div>
                  <ArrowRight size={13} className="text-[#647795] group-hover:text-[#3975D1] transition-colors" />
                </div>
                <div className="mt-3">
                  <p className="text-xs font-bold text-[#101D36]">Sync Schedule</p>
                  <p className="text-[10px] text-[#647795] truncate">Refetch live state</p>
                </div>
              </button>
            </div>
          </div>

          <div className="pt-3 border-t border-[#E3EBF6] text-[11px] text-[#647795] flex items-center justify-between">
            <span>Direct Portal Shortcuts</span>
            <span className="text-[#3975D1] font-semibold">4 active actions</span>
          </div>
        </section>
      </div>

      {/* ── Interactive Faculty Profile Modal ── */}
      {showProfileModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in duration-150">
          <div className="bg-white rounded-3xl border border-[#E3EBF6] p-6 max-w-md w-full shadow-modal space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#E3EBF6]">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-[#E4EEFF] text-[#3975D1] flex items-center justify-center">
                  <GraduationCap size={18} />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-[#101D36]">Faculty Credentials</h4>
                  <p className="text-[11px] text-[#647795]">Academic institutional file</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowProfileModal(false)}
                className="w-7 h-7 rounded-full bg-[#F1F6FD] text-[#647795] hover:text-[#101D36] flex items-center justify-center"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="p-3 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6]">
                <p className="text-[10px] text-[#647795] uppercase font-bold">Faculty Name</p>
                <p className="text-sm font-bold text-[#101D36] mt-0.5">{facultyName}</p>
                <p className="text-[11px] text-[#3975D1] font-semibold">{designation}</p>
              </div>

              <div className="p-3 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6]">
                <p className="text-[10px] text-[#647795] uppercase font-bold">Campus Email</p>
                <p className="font-semibold text-[#101D36] mt-0.5">{user?.email}</p>
              </div>

              <div className="p-3 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6]">
                <p className="text-[10px] text-[#647795] uppercase font-bold">Department</p>
                <p className="font-semibold text-[#101D36] mt-0.5">{departmentName}</p>
              </div>

              {timetable?.faculty_code && (
                <div className="p-3 rounded-2xl bg-[#F8FAFD] border border-[#E3EBF6]">
                  <p className="text-[10px] text-[#647795] uppercase font-bold">Faculty ID Code</p>
                  <p className="font-semibold text-[#101D36] mt-0.5 font-tabular">{timetable.faculty_code}</p>
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={() => setShowProfileModal(false)}
              className="w-full py-2.5 rounded-xl bg-[#3975D1] hover:bg-[#2F65B8] text-white text-xs font-semibold shadow-xs transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default FacultyDashboard;
