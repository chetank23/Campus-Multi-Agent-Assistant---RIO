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
import { PageHeader, StatCard, LoadingState, ErrorState } from '@/components/common';
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

  const entries = timetable?.entries || [];

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
      <PageHeader
        title="My Class Schedule"
        subtitle={academicLabel}
        actions={
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors shadow-xs disabled:opacity-50"
          >
            <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>
        }
      />

      {isLoading ? (
        <LoadingState message="Loading your class timetable from campus database…" />
      ) : isError ? (
        <ErrorState
          message={(error as Error)?.message || 'Failed to load class schedule.'}
          onRetry={() => refetch()}
        />
      ) : (
        <>
          {/* Quick Stats Banner */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Weekly Class Hours"
              value={timetable?.total_class_hours ?? entries.length}
              sub="Official lecture & lab hours"
              icon={<Clock size={20} />}
              variant="primary"
            />
            <StatCard
              label="Active Courses"
              value={distinctCourses}
              sub="Scheduled curriculum subjects"
              icon={<BookOpen size={20} />}
              variant="default"
            />
            <StatCard
              label="Assigned Section"
              value={timetable?.section_name ? `Sec ${timetable.section_name}` : 'Not assigned'}
              sub={timetable?.batch_name ? `Batch ${timetable.batch_name}` : 'Section-wide'}
              icon={<Users size={20} />}
              variant="warning"
            />
            <StatCard
              label="Instructors"
              value={distinctFaculty}
              sub="Faculty members teaching"
              icon={<GraduationCap size={20} />}
              variant="default"
            />
          </div>

          {/* Timetable Grid */}
          <PersonalTimetableGrid
            entries={entries}
            role="STUDENT"
            emptyMessage="No published timetable entries found for your section/batch"
          />
        </>
      )}
    </div>
  );
};
export default StudentTimetablePage;
