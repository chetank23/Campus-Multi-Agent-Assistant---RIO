/**
 * pages/student/StudentDashboard.tsx
 * -------------------------------------
 * RIO-MJP Student Portal Dashboard.
 * Rebuilt to faithfully follow the pastel powder-blue visual reference override:
 * - 3-panel multi-card layout with soft rounded corners (rounded-[20px] / rounded-[24px])
 * - Left panel: "Classes for the day" with search/filter icons, time badges, instructor avatars, and graceful empty state
 * - Center panels: Academic Overview (4 compact pastel summary cards) & "My Schedule" calendar preview with interactive day switcher
 * - Right panel: Student Academic Profile & Cohort card with banner and official enrollment details
 * - Strict read-only usage of existing APIs with zero fabricated data
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
  Search,
  SlidersHorizontal,
  ChevronRight,
  Sparkles,
  Building2,
  Mail,
  GraduationCap,
} from 'lucide-react';
import { apiGetMe } from '@/api/auth';
import { getStudentMyTimetable } from '@/api/timetable';
import { useAuth } from '@/auth/AuthProvider';
import { LoadingState } from '@/components/common';
import { formatTime12h } from '@/utils/timeFormatter';

const DAYS_SHORT = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'] as const;
const DAY_FULL_NAMES: Record<string, string> = {
  MON: 'Monday',
  TUE: 'Tuesday',
  WED: 'Wednesday',
  THU: 'Thursday',
  FRI: 'Friday',
  SAT: 'Saturday',
  SUN: 'Sunday',
};

export function StudentDashboard() {
  const { user: ctxUser } = useAuth();
  const [classSearch, setClassSearch] = useState('');
  const [showSearchInput, setShowSearchInput] = useState(false);

  // Queries
  const { data: me, isLoading: isUserLoading } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: apiGetMe,
    staleTime: 60_000,
  });

  const { data: timetable, isLoading: isTimetableLoading } = useQuery({
    queryKey: ['student', 'my-timetable'],
    queryFn: () => getStudentMyTimetable(),
    staleTime: 60_000,
  });

  const user = me ?? ctxUser;
  const entries = React.useMemo(() => timetable?.entries || [], [timetable?.entries]);

  // Determine today's day key (MON, TUE, WED, THU, FRI, SAT)
  const todayKey = React.useMemo(() => {
    const dayIndex = new Date().getDay();
    const days = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
    return days[dayIndex] || 'MON';
  }, []);

  const [selectedCalendarDay, setSelectedCalendarDay] = useState<string>(
    todayKey === 'SUN' ? 'MON' : todayKey
  );

  // Today's classes
  const todayEntries = React.useMemo(() => {
    return entries.filter((e) => {
      const d = (e.day || '').toUpperCase();
      return d.startsWith(todayKey);
    });
  }, [entries, todayKey]);

  // Filtered today's entries if user typed in search
  const filteredTodayEntries = React.useMemo(() => {
    if (!classSearch.trim()) return todayEntries;
    const q = classSearch.toLowerCase();
    return todayEntries.filter(
      (e) =>
        (e.course_name && e.course_name.toLowerCase().includes(q)) ||
        (e.course_code && e.course_code.toLowerCase().includes(q)) ||
        (e.faculty_name && e.faculty_name.toLowerCase().includes(q)) ||
        (e.room_number && e.room_number.toLowerCase().includes(q))
    );
  }, [todayEntries, classSearch]);

  // Selected calendar day entries
  const selectedDayEntries = React.useMemo(() => {
    return entries.filter((e) => {
      const d = (e.day || '').toUpperCase();
      return d.startsWith(selectedCalendarDay);
    });
  }, [entries, selectedCalendarDay]);

  // Distinct courses
  const distinctCourses = React.useMemo(() => {
    const set = new Set<string>();
    entries.forEach((e) => {
      if (e.course_code) set.add(e.course_code);
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

  // Format today's date for display (e.g., "17/10/26")
  const formattedTodayDate = React.useMemo(() => {
    const now = new Date();
    const day = now.getDate();
    const month = now.getMonth() + 1;
    const year = String(now.getFullYear()).slice(-2);
    return `${day}/${month}/${year}`;
  }, []);

  // Format current month & year (e.g. "October 2026")
  const currentMonthYear = React.useMemo(() => {
    return new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }, []);

  if (isUserLoading && !user) {
    return (
      <div className="py-16">
        <LoadingState message="Connecting to your student workspace…" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Main Multi-Panel Layout (Inspired by Reference) ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 lg:gap-6">
        {/* ══════════════════════════════════════════════════════════════════
            COLUMN 1: Classes for the day (lg:col-span-5)
            ══════════════════════════════════════════════════════════════════ */}
        <section
          className="lg:col-span-5 bg-white rounded-[24px] border border-[#E5ECF5] p-5 sm:p-6 shadow-xs flex flex-col justify-between"
          aria-labelledby="classes-heading"
        >
          <div>
            {/* Panel Header */}
            <div className="flex items-center justify-between pb-4 border-b border-[#E5ECF5]">
              <div className="flex items-center gap-2">
                <h3 id="classes-heading" className="text-base sm:text-lg font-bold text-[#17243B]">
                  Classes for the day
                </h3>
              </div>

              {/* Action Icons (Search & Filter) */}
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setShowSearchInput((prev) => !prev)}
                  title="Search today's classes"
                  aria-label="Search today's classes"
                  className={`w-8 h-8 rounded-full border border-[#E5ECF5] flex items-center justify-center transition-colors ${
                    showSearchInput
                      ? 'bg-[#4B83D1] text-white border-[#4B83D1]'
                      : 'text-[#71819A] hover:text-[#17243B] hover:bg-[#F1F6FF]'
                  }`}
                >
                  <Search size={14} />
                </button>
                <Link
                  to="/student/timetable"
                  title="Filter and full timetable view"
                  aria-label="Full timetable view"
                  className="w-8 h-8 rounded-full border border-[#E5ECF5] text-[#71819A] hover:text-[#17243B] hover:bg-[#F1F6FF] flex items-center justify-center transition-colors"
                >
                  <SlidersHorizontal size={14} />
                </Link>
              </div>
            </div>

            {/* Quick search input */}
            {showSearchInput && (
              <div className="mt-3 animate-in fade-in duration-150">
                <input
                  type="text"
                  placeholder="Filter by course, faculty, or room…"
                  value={classSearch}
                  onChange={(e) => setClassSearch(e.target.value)}
                  className="w-full px-3.5 py-1.5 rounded-xl border border-[#D6DFEA] text-xs text-[#17243B] bg-[#F8FAFC] placeholder-[#8190A5] focus:outline-none focus:ring-2 focus:ring-[#93B5E8] focus:bg-white transition-all"
                />
              </div>
            )}

            {/* Class Cards List */}
            <div className="mt-4 space-y-3.5">
              {isTimetableLoading ? (
                <div className="py-12">
                  <LoadingState message="Checking your schedule for today…" />
                </div>
              ) : filteredTodayEntries.length === 0 ? (
                /* Elegant Empty State */
                <div className="py-10 px-4 text-center rounded-[20px] bg-[#F1F6FF]/60 border border-[#E5ECF5] mt-2">
                  <div className="w-14 h-14 rounded-2xl bg-[#EBF3FE] border border-[#D0E2FC] text-[#4B83D1] mx-auto flex items-center justify-center mb-3.5 shadow-xs">
                    <CalendarDays size={24} />
                  </div>
                  <h4 className="text-sm font-bold text-[#17243B]">No classes scheduled today</h4>
                  <p className="text-xs text-[#71819A] mt-1.5 max-w-xs mx-auto leading-relaxed">
                    {entries.length > 0
                      ? `You have ${entries.length} scheduled class sessions on other days of the week.`
                      : 'There are currently no published timetable entries for your section or cohort.'}
                  </p>

                  <div className="mt-5">
                    <Link
                      to="/student/timetable"
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[#4B83D1] hover:bg-[#3D71BD] text-white text-xs font-semibold shadow-xs transition-colors"
                    >
                      <span>Check Weekly Timetable</span>
                      <ArrowRight size={13} />
                    </Link>
                  </div>
                </div>
              ) : (
                filteredTodayEntries.map((entry, index) => {
                  const isLab =
                    entry.slot_type === 'LAB' ||
                    entry.course_type === 'LAB' ||
                    entry.course_type === 'PRACTICAL';
                  const isFirst = index === 0;

                  return (
                    <article
                      key={entry.id}
                      className="p-4 rounded-[20px] bg-[#F1F6FF] border border-[#E5ECF5] hover:border-[#D0E2FC] transition-all duration-150 hover:shadow-xs group"
                    >
                      {/* Top Row: Course Title & Date/Time Badge */}
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <h4 className="text-sm font-bold text-[#17243B] group-hover:text-[#4B83D1] transition-colors">
                            {entry.course_name || 'Scheduled Course'}
                          </h4>
                          <span className="text-[11px] font-semibold text-[#71819A] font-tabular">
                            {entry.course_code || 'CODE'}
                          </span>
                        </div>

                        {/* Date/Time badge + "Now" pill */}
                        <div className="flex items-center gap-1.5 shrink-0">
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white border border-[#E5ECF5] text-[11px] font-medium text-[#71819A] font-tabular shadow-2xs">
                            <CalendarDays size={11} className="text-[#4B83D1]" />
                            <span>
                              {entry.start_time
                                ? `${formatTime12h(entry.start_time)}`
                                : formattedTodayDate}
                            </span>
                          </span>

                          {isFirst && (
                            <span className="px-2 py-0.5 rounded-full bg-[#4B83D1] text-white text-[10px] font-bold uppercase tracking-wider shadow-2xs">
                              Next
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Instructor with Avatar */}
                      <div className="flex items-center gap-2 mt-2.5 pt-2 border-t border-[#E5ECF5]/60">
                        <div className="w-6 h-6 rounded-full bg-white border border-[#D0E2FC] text-[#4B83D1] text-[10px] font-bold flex items-center justify-center shrink-0">
                          {entry.faculty_name ? entry.faculty_name.charAt(0) : 'P'}
                        </div>
                        <p className="text-xs font-semibold text-[#17243B] truncate">
                          {entry.faculty_name ? `Professor ${entry.faculty_name}` : 'Faculty Member'}
                        </p>
                      </div>

                      {/* Bottom Info: Location, Slot Type & Time Range */}
                      <div className="flex items-center justify-between text-[11px] text-[#71819A] mt-2.5 pt-2 border-t border-[#E5ECF5]/60">
                        <div className="flex items-center gap-2.5">
                          {entry.room_number && (
                            <span className="inline-flex items-center gap-1 font-semibold text-[#17243B]">
                              <MapPin size={11} className="text-[#4B83D1]" />
                              <span>{entry.room_number}</span>
                            </span>
                          )}
                          <span className="inline-flex items-center gap-1 font-tabular">
                            <Clock size={11} className="text-[#71819A]" />
                            <span>
                              {formatTime12h(entry.start_time)} – {formatTime12h(entry.end_time)}
                            </span>
                          </span>
                        </div>

                        <span
                          className={`px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${
                            isLab
                              ? 'bg-[#FFF5E6] text-[#D97706] border border-[#FFE9CC]'
                              : 'bg-[#DDF7EC] text-[#1B7A53] border border-[#C6F2DF]'
                          }`}
                        >
                          {isLab ? 'Lab' : 'Lecture'}
                        </span>
                      </div>
                    </article>
                  );
                })
              )}
            </div>
          </div>

          {/* Bottom Card Summary */}
          <div className="mt-5 pt-4 border-t border-[#E5ECF5] flex items-center justify-between text-xs text-[#71819A]">
            <span>
              Today: <strong className="text-[#17243B]">{DAY_FULL_NAMES[todayKey] || 'Day'}</strong> ({formattedTodayDate})
            </span>
            <span className="font-semibold text-[#4B83D1]">
              {todayEntries.length} {todayEntries.length === 1 ? 'class' : 'classes'} scheduled
            </span>
          </div>
        </section>

        {/* ══════════════════════════════════════════════════════════════════
            COLUMN 2: Academic Overview & My Calendar (lg:col-span-4)
            ══════════════════════════════════════════════════════════════════ */}
        <div className="lg:col-span-4 space-y-5 lg:space-y-6">
          {/* ── Top Box: Academic Overview (Summary Metrics Cards) ── */}
          <section
            className="bg-white rounded-[24px] border border-[#E5ECF5] p-5 shadow-xs"
            aria-labelledby="overview-heading"
          >
            <div className="flex items-center justify-between pb-3.5 border-b border-[#E5ECF5]">
              <h3 id="overview-heading" className="text-sm font-bold text-[#17243B]">
                Academic Overview
              </h3>
              <span className="text-[11px] font-medium text-[#71819A]">Enrolled Status</span>
            </div>

            {/* 2x2 Grid of Subtle Pastel Summary Cards */}
            <div className="grid grid-cols-2 gap-3 mt-3.5">
              {/* Soft Blue Card: Weekly Class Hours */}
              <div className="p-3.5 rounded-[18px] bg-[#F1F6FF] border border-[#E1ECF8] flex flex-col justify-between transition-all hover:shadow-2xs">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-[#4B83D1] uppercase tracking-wider">
                    Weekly
                  </span>
                  <div className="w-7 h-7 rounded-full bg-white text-[#4B83D1] flex items-center justify-center shadow-2xs">
                    <Clock size={13} />
                  </div>
                </div>
                <div className="mt-2">
                  <p className="text-xl font-extrabold text-[#17243B] font-tabular">
                    {timetable?.total_class_hours ?? entries.length}
                  </p>
                  <p className="text-[10px] text-[#71819A] mt-0.5 truncate">Total Class Hours</p>
                </div>
              </div>

              {/* Lavender Card: Active Courses */}
              <div className="p-3.5 rounded-[18px] bg-[#F0EBFF] border border-[#E5DEFF] flex flex-col justify-between transition-all hover:shadow-2xs">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-[#6C5CE7] uppercase tracking-wider">
                    Subjects
                  </span>
                  <div className="w-7 h-7 rounded-full bg-white text-[#6C5CE7] flex items-center justify-center shadow-2xs">
                    <BookOpen size={13} />
                  </div>
                </div>
                <div className="mt-2">
                  <p className="text-xl font-extrabold text-[#17243B] font-tabular">
                    {distinctCourses}
                  </p>
                  <p className="text-[10px] text-[#71819A] mt-0.5 truncate">Curriculum Units</p>
                </div>
              </div>

              {/* Mint Card: Section & Cohort */}
              <div className="p-3.5 rounded-[18px] bg-[#DDF7EC] border border-[#C6F2DF] flex flex-col justify-between transition-all hover:shadow-2xs">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-[#1B7A53] uppercase tracking-wider">
                    Cohort
                  </span>
                  <div className="w-7 h-7 rounded-full bg-white text-[#1B7A53] flex items-center justify-center shadow-2xs">
                    <Users size={13} />
                  </div>
                </div>
                <div className="mt-2">
                  <p className="text-xl font-extrabold text-[#17243B] truncate">
                    {timetable?.section_name ? `Sec ${timetable.section_name}` : 'Unassigned'}
                  </p>
                  <p className="text-[10px] text-[#71819A] mt-0.5 truncate">
                    {timetable?.batch_name ? `Batch ${timetable.batch_name}` : 'Full Section'}
                  </p>
                </div>
              </div>

              {/* Pale Amber Card: Labs & Practicals */}
              <div className="p-3.5 rounded-[18px] bg-[#FFF5E6] border border-[#FFE8CC] flex flex-col justify-between transition-all hover:shadow-2xs">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-[#D97706] uppercase tracking-wider">
                    Practicals
                  </span>
                  <div className="w-7 h-7 rounded-full bg-white text-[#D97706] flex items-center justify-center shadow-2xs">
                    <GraduationCap size={13} />
                  </div>
                </div>
                <div className="mt-2">
                  <p className="text-xl font-extrabold text-[#17243B] font-tabular">
                    {labSessionsCount}
                  </p>
                  <p className="text-[10px] text-[#71819A] mt-0.5 truncate">Lab Sessions / Wk</p>
                </div>
              </div>
            </div>
          </section>

          {/* ── Bottom Box: My Calendar / Schedule Overview (Modeled on Reference) ── */}
          <section
            className="bg-white rounded-[24px] border border-[#E5ECF5] p-5 shadow-xs"
            aria-labelledby="calendar-heading"
          >
            {/* Header with Arrow Circle Button */}
            <div className="flex items-center justify-between pb-3.5 border-b border-[#E5ECF5]">
              <h3 id="calendar-heading" className="text-sm font-bold text-[#17243B]">
                My Calendar
              </h3>
              <Link
                to="/student/timetable"
                title="Open interactive weekly timetable"
                aria-label="Open interactive weekly timetable"
                className="w-7 h-7 rounded-full bg-[#F1F6FF] text-[#4B83D1] hover:bg-[#4B83D1] hover:text-white flex items-center justify-center transition-colors"
              >
                <ChevronRight size={15} />
              </Link>
            </div>

            {/* Current Month Caption */}
            <div className="text-center py-2.5">
              <span className="text-xs font-bold text-[#4B83D1] uppercase tracking-wider">
                {currentMonthYear}
              </span>
            </div>

            {/* Day Selector Pill Buttons (Mon to Sat) */}
            <div className="grid grid-cols-6 gap-1.5 mt-1">
              {DAYS_SHORT.map((day) => {
                const isSelected = selectedCalendarDay === day;
                const isToday = todayKey === day;
                const count = entries.filter((e) => (e.day || '').toUpperCase().startsWith(day)).length;

                return (
                  <button
                    key={day}
                    type="button"
                    onClick={() => setSelectedCalendarDay(day)}
                    className={`py-2 rounded-xl text-xs font-bold transition-all flex flex-col items-center justify-center gap-0.5 ${
                      isSelected
                        ? 'bg-[#4B83D1] text-white shadow-xs'
                        : isToday
                        ? 'bg-[#EBF3FE] text-[#4B83D1] border border-[#CDE1FB]'
                        : 'bg-[#F8FAFC] text-[#71819A] hover:bg-[#F1F6FF] hover:text-[#17243B]'
                    }`}
                  >
                    <span className="text-[10px] uppercase">{day}</span>
                    <span className={`text-[9px] font-semibold ${isSelected ? 'text-white/90' : 'text-[#71819A]'}`}>
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Selected Day Agenda Snapshot */}
            <div className="mt-3.5 p-3 rounded-2xl bg-[#F8FAFC] border border-[#E5ECF5]">
              <div className="flex items-center justify-between text-xs font-semibold text-[#17243B] pb-2 border-b border-[#E5ECF5]">
                <span>{DAY_FULL_NAMES[selectedCalendarDay] || selectedCalendarDay} Schedule</span>
                <span className="text-[11px] text-[#4B83D1] font-tabular">
                  {selectedDayEntries.length} {selectedDayEntries.length === 1 ? 'class' : 'classes'}
                </span>
              </div>

              {selectedDayEntries.length === 0 ? (
                <p className="text-xs text-[#71819A] text-center py-3">
                  No classes scheduled on this day.
                </p>
              ) : (
                <div className="space-y-2 mt-2 max-h-36 overflow-y-auto pr-1">
                  {selectedDayEntries.map((e) => (
                    <div
                      key={e.id}
                      className="p-2 rounded-xl bg-white border border-[#E5ECF5] text-xs flex items-center justify-between gap-2"
                    >
                      <div className="truncate">
                        <p className="font-semibold text-[#17243B] truncate">{e.course_name}</p>
                        <p className="text-[10px] text-[#71819A] font-tabular">
                          {formatTime12h(e.start_time)} – {formatTime12h(e.end_time)}
                        </p>
                      </div>
                      {e.room_number && (
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#F1F6FF] text-[#4B83D1] shrink-0">
                          {e.room_number}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>

        {/* ══════════════════════════════════════════════════════════════════
            COLUMN 3: Student Academic Profile & Cohort (lg:col-span-3)
            ══════════════════════════════════════════════════════════════════ */}
        <aside
          className="lg:col-span-3 bg-white rounded-[24px] border border-[#E5ECF5] overflow-hidden shadow-xs flex flex-col justify-between"
          aria-labelledby="profile-heading"
        >
          <div>
            {/* Aesthetic Wave / Gradient University Header Banner */}
            <div className="relative h-28 bg-gradient-to-br from-[#4B83D1] via-[#3E76C3] to-[#2E63AC] p-4 flex flex-col justify-end text-white overflow-hidden">
              <div
                className="pointer-events-none absolute -right-6 -bottom-8 w-28 h-28 rounded-full border-8 border-white/10"
                aria-hidden="true"
              />
              <div
                className="pointer-events-none absolute right-10 top-2 w-16 h-16 rounded-full bg-white/10 blur-sm"
                aria-hidden="true"
              />
              <div className="relative z-10 flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-full bg-white/20 backdrop-blur-xs text-[10px] font-bold uppercase tracking-wider text-white">
                  Student File
                </span>
              </div>
            </div>

            {/* Profile Content Body */}
            <div className="p-5 space-y-4">
              <div>
                <h3 id="profile-heading" className="text-base font-bold text-[#17243B] truncate">
                  {user?.name || 'Student Name'}
                </h3>
                <p className="text-xs text-[#4B83D1] font-semibold mt-0.5 font-tabular">
                  {timetable?.student_code || 'ID: Enrolled Student'}
                </p>
              </div>

              {/* Details List */}
              <div className="space-y-3 pt-2 border-t border-[#E5ECF5] text-xs">
                {/* Email */}
                <div className="flex items-start gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-[#F1F6FF] text-[#4B83D1] flex items-center justify-center shrink-0">
                    <Mail size={13} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[10px] text-[#71819A]">Campus Email</p>
                    <p className="font-semibold text-[#17243B] break-all">{user?.email}</p>
                  </div>
                </div>

                {/* Program & Department */}
                <div className="flex items-start gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-[#F1F6FF] text-[#4B83D1] flex items-center justify-center shrink-0">
                    <Building2 size={13} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[10px] text-[#71819A]">Program & Department</p>
                    <p className="font-semibold text-[#17243B]">
                      {timetable?.program_name || timetable?.department_name || (user?.department_id ? `Department #${user.department_id}` : 'General')}
                    </p>
                  </div>
                </div>

                {/* Section & Batch */}
                <div className="flex items-start gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-[#F1F6FF] text-[#4B83D1] flex items-center justify-center shrink-0">
                    <Users size={13} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[10px] text-[#71819A]">Cohort Allocation</p>
                    <p className="font-semibold text-[#17243B]">
                      {timetable?.section_name ? `Section ${timetable.section_name}` : 'Not assigned'}
                      {timetable?.batch_name ? ` • Batch ${timetable.batch_name}` : ''}
                    </p>
                  </div>
                </div>

                {/* Academic Status */}
                <div className="flex items-start gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-[#DDF7EC] text-[#1B7A53] flex items-center justify-center shrink-0">
                    <Sparkles size={13} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[10px] text-[#71819A]">Enrolled Status</p>
                    <p className="font-semibold text-[#1B7A53]">Active Matriculation</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom Action Button */}
          <div className="p-5 pt-0">
            <Link
              to="/student/timetable"
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-full bg-[#4B83D1] hover:bg-[#3D71BD] text-white text-xs font-semibold shadow-xs transition-colors"
            >
              <CalendarDays size={13} />
              <span>Open My Timetable</span>
            </Link>
          </div>
        </aside>
      </div>
    </div>
  );
}

export default StudentDashboard;
