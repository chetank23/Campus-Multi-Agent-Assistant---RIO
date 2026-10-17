import React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Clock,
  BookOpen,
  Users,
  MapPin,
  RefreshCw,
} from 'lucide-react';
import { getFacultyMyTimetable } from '@/api/timetable';
import { PageHeader, StatCard, LoadingState, ErrorState } from '@/components/common';
import { PersonalTimetableGrid } from '@/components/timetable/PersonalTimetableGrid';

export const FacultyTimetablePage: React.FC = () => {

  const {
    data: timetable,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['faculty', 'my-timetable'],
    queryFn: () => getFacultyMyTimetable(),
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

  const distinctSections = React.useMemo(() => {
    const set = new Set<string>();
    entries.forEach((e) => {
      if (e.section_name) {
        set.add(`${e.section_name}-${e.batch_name || 'all'}`);
      }
    });
    return set.size;
  }, [entries]);

  const distinctRooms = React.useMemo(() => {
    const set = new Set<string>();
    entries.forEach((e) => {
      if (e.room_number) set.add(e.room_number);
    });
    return set.size;
  }, [entries]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Teaching Timetable"
        subtitle={
          timetable?.designation && timetable?.department_name
            ? `${timetable.designation} • ${timetable.department_name}`
            : 'Published academic teaching schedule and classroom allocations'
        }
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
        <LoadingState message="Loading your teaching timetable from campus database…" />
      ) : isError ? (
        <ErrorState
          message={(error as Error)?.message || 'Failed to load teaching schedule.'}
          onRetry={() => refetch()}
        />
      ) : (
        <>
          {/* Quick Stats Banner */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Weekly Teaching Hours"
              value={timetable?.total_teaching_hours ?? entries.length}
              sub="Official scheduled periods"
              icon={<Clock size={20} />}
              variant="primary"
            />
            <StatCard
              label="Assigned Courses"
              value={distinctCourses}
              sub="Unique course codes"
              icon={<BookOpen size={20} />}
              variant="default"
            />
            <StatCard
              label="Sections & Batches"
              value={distinctSections}
              sub="Teaching groups"
              icon={<Users size={20} />}
              variant="warning"
            />
            <StatCard
              label="Campus Rooms / Labs"
              value={distinctRooms}
              sub="Allocated facilities"
              icon={<MapPin size={20} />}
              variant="default"
            />
          </div>

          {/* Timetable Grid */}
          <PersonalTimetableGrid
            entries={entries}
            role="FACULTY"
            emptyMessage="No published timetable entries found for your teaching assignments"
          />
        </>
      )}
    </div>
  );
};
export default FacultyTimetablePage;
