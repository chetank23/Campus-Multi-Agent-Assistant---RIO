import React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Clock,
  BookOpen,
  Users,
  RefreshCw,
  GraduationCap,
} from 'lucide-react';
import { getStudentMyTimetable } from '@/api/timetable';
import { LoadingState, ErrorState } from '@/components/common';
import { PersonalTimetableGrid } from '@/components/timetable/PersonalTimetableGrid';

export const StudentTimetablePage: React.FC = () => {
  const {
    data: timetable,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['student', 'my-timetable'],
    queryFn: () => getStudentMyTimetable(),
    staleTime: 60_000,
  });

  const entries = React.useMemo(() => timetable?.entries || [], [timetable?.entries]);

  // Computed summary metrics from real returned schedule data
  const distinctCourses = React.useMemo(() => {
    const set = new Set<string>();
    entries.forEach((e) => {
      if (e.course_code) set.add(e.course_code);
    });
    return set.size;
  }, [entries]);

  const distinctFaculty = React.useMemo(() => {
    const set = new Set<string>();
    entries.forEach((e) => {
      if (e.faculty_name) set.add(e.faculty_name);
    });
    return set.size;
  }, [entries]);

  const academicLabel = React.useMemo(() => {
    const parts = [];
    if (timetable?.program_name) parts.push(timetable.program_name);
    if (timetable?.semester_number) parts.push(`Semester ${timetable.semester_number}`);
    if (timetable?.section_name) parts.push(`Section ${timetable.section_name}`);
    if (timetable?.batch_name) parts.push(`Batch ${timetable.batch_name}`);
    return parts.length > 0 ? parts.join(' • ') : 'Enrolled section academic class schedule';
  }, [timetable]);

  return (
    <div className="space-y-6">
      {/* ── Page Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-[#E5ECF5]">
        <div>
          <h3 className="text-xl sm:text-2xl font-extrabold text-[#17243B] tracking-tight">
            My Class Schedule
          </h3>
          <p className="text-xs text-[#71819A] mt-1 font-medium">
            {academicLabel}
          </p>
        </div>

        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-[#E5ECF5] bg-white text-xs font-semibold text-[#17243B] hover:bg-[#F1F6FF] hover:border-[#D0E2FC] transition-all shadow-xs self-start sm:self-auto disabled:opacity-50"
        >
          <RefreshCw size={13} className={isFetching ? 'animate-spin text-[#4B83D1]' : 'text-[#71819A]'} />
          <span>Refresh</span>
        </button>
      </div>

      {isLoading ? (
        <div className="py-16">
          <LoadingState message="Loading your class timetable from campus database…" />
        </div>
      ) : isError ? (
        <ErrorState
          message={(error as Error)?.message || 'Failed to load class schedule.'}
          onRetry={() => refetch()}
        />
      ) : (
        <>
          {/* ── Compact Pastel Summary Cards ── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 sm:gap-4">
            {/* Soft Blue: Weekly Class Hours */}
            <div className="p-4 rounded-[20px] bg-[#F1F6FF] border border-[#E1ECF8] flex flex-col justify-between transition-all hover:shadow-2xs">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-[#4B83D1] uppercase tracking-wider">
                  Weekly Hours
                </span>
                <div className="w-8 h-8 rounded-full bg-white text-[#4B83D1] flex items-center justify-center shadow-2xs">
                  <Clock size={15} />
                </div>
              </div>
              <div className="mt-3">
                <p className="text-2xl font-extrabold text-[#17243B] font-tabular">
                  {timetable?.total_class_hours ?? entries.length}
                </p>
                <p className="text-xs text-[#71819A] mt-0.5 truncate">Lecture & practical hours</p>
              </div>
            </div>

            {/* Lavender: Active Courses */}
            <div className="p-4 rounded-[20px] bg-[#F0EBFF] border border-[#E5DEFF] flex flex-col justify-between transition-all hover:shadow-2xs">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-[#6C5CE7] uppercase tracking-wider">
                  Active Subjects
                </span>
                <div className="w-8 h-8 rounded-full bg-white text-[#6C5CE7] flex items-center justify-center shadow-2xs">
                  <BookOpen size={15} />
                </div>
              </div>
              <div className="mt-3">
                <p className="text-2xl font-extrabold text-[#17243B] font-tabular">
                  {distinctCourses}
                </p>
                <p className="text-xs text-[#71819A] mt-0.5 truncate">Curriculum course units</p>
              </div>
            </div>

            {/* Mint: Assigned Section & Cohort */}
            <div className="p-4 rounded-[20px] bg-[#DDF7EC] border border-[#C6F2DF] flex flex-col justify-between transition-all hover:shadow-2xs">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-[#1B7A53] uppercase tracking-wider">
                  Section Cohort
                </span>
                <div className="w-8 h-8 rounded-full bg-white text-[#1B7A53] flex items-center justify-center shadow-2xs">
                  <Users size={15} />
                </div>
              </div>
              <div className="mt-3">
                <p className="text-2xl font-extrabold text-[#17243B] truncate">
                  {timetable?.section_name ? `Sec ${timetable.section_name}` : 'Not assigned'}
                </p>
                <p className="text-xs text-[#71819A] mt-0.5 truncate">
                  {timetable?.batch_name ? `Lab Batch ${timetable.batch_name}` : 'Section Cohort'}
                </p>
              </div>
            </div>

            {/* Pale Amber: Instructors */}
            <div className="p-4 rounded-[20px] bg-[#FFF5E6] border border-[#FFE8CC] flex flex-col justify-between transition-all hover:shadow-2xs">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-[#D97706] uppercase tracking-wider">
                  Instructors
                </span>
                <div className="w-8 h-8 rounded-full bg-white text-[#D97706] flex items-center justify-center shadow-2xs">
                  <GraduationCap size={15} />
                </div>
              </div>
              <div className="mt-3">
                <p className="text-2xl font-extrabold text-[#17243B] font-tabular">
                  {distinctFaculty}
                </p>
                <p className="text-xs text-[#71819A] mt-0.5 truncate">Assigned faculty members</p>
              </div>
            </div>
          </div>

          {/* ── Timetable Grid / Agenda ── */}
          <div className="bg-white rounded-[24px] border border-[#E5ECF5] p-4 sm:p-5 shadow-xs">
            <PersonalTimetableGrid
              entries={entries}
              role="STUDENT"
              emptyMessage="No published timetable entries found for your section/batch"
            />
          </div>
        </>
      )}
    </div>
  );
};

export default StudentTimetablePage;
