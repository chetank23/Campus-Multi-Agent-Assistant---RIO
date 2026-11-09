import React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Clock,
  BookOpen,
  Users,
  MapPin,
} from 'lucide-react';
import { getFacultyMyTimetable } from '@/api/timetable';
import { LoadingState, ErrorState, RefreshButton } from '@/components/common';
import { PersonalTimetableGrid } from '@/components/timetable/PersonalTimetableGrid';

export const FacultyTimetablePage: React.FC = () => {
  const {
    data: timetable,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['faculty', 'my-timetable'],
    queryFn: () => getFacultyMyTimetable(),
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
      {/* ── Page Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-[#E3EBF6]">
        <div>
          <h3 className="text-xl sm:text-2xl font-extrabold text-[#101D36] tracking-tight">
            My Teaching Timetable
          </h3>
          <p className="text-xs text-[#647795] mt-1 font-medium">
            {timetable?.designation && timetable?.department_name
              ? `${timetable.designation} • Department of ${timetable.department_name}`
              : 'Published academic teaching schedule and classroom allocations'}
          </p>
        </div>

        <RefreshButton
          entityName="Teaching Schedule"
          onRefresh={() => refetch()}
          label="Refresh Schedule"
          variant="outline"
        />
      </div>

      {isLoading ? (
        <div className="py-16">
          <LoadingState message="Loading your teaching timetable from campus database…" />
        </div>
      ) : isError ? (
        <ErrorState
          message={(error as Error)?.message || 'Failed to load teaching schedule.'}
          onRetry={() => refetch()}
        />
      ) : (
        <>
          {/* ── Four Summary Cards Matching Reference Palette ── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Card 1: Weekly Teaching Hours */}
            <div className="bg-white rounded-2xl border border-[#E3EBF6] p-4 sm:p-5 shadow-xs flex items-start justify-between">
              <div>
                <p className="text-xs font-bold text-[#647795]">Weekly Teaching Hours</p>
                <p className="text-2xl sm:text-3xl font-extrabold text-[#101D36] font-tabular mt-1.5">
                  {timetable?.total_teaching_hours ?? entries.length}h
                </p>
                <p className="text-[11px] text-[#8FA3BF] mt-1">Official scheduled periods</p>
              </div>
              <div className="w-10 h-10 rounded-xl bg-[#E4EEFF] text-[#3975D1] flex items-center justify-center shrink-0 shadow-2xs">
                <Clock size={20} />
              </div>
            </div>

            {/* Card 2: Assigned Courses */}
            <div className="bg-white rounded-2xl border border-[#E3EBF6] p-4 sm:p-5 shadow-xs flex items-start justify-between">
              <div>
                <p className="text-xs font-bold text-[#647795]">Assigned Courses</p>
                <p className="text-2xl sm:text-3xl font-extrabold text-[#101D36] font-tabular mt-1.5">
                  {distinctCourses}
                </p>
                <p className="text-[11px] text-[#8FA3BF] mt-1">Unique curriculum codes</p>
              </div>
              <div className="w-10 h-10 rounded-xl bg-[#DDF6EC] text-[#14865B] flex items-center justify-center shrink-0 shadow-2xs">
                <BookOpen size={20} />
              </div>
            </div>

            {/* Card 3: Sections & Batches */}
            <div className="bg-white rounded-2xl border border-[#E3EBF6] p-4 sm:p-5 shadow-xs flex items-start justify-between">
              <div>
                <p className="text-xs font-bold text-[#647795]">Sections & Batches</p>
                <p className="text-2xl sm:text-3xl font-extrabold text-[#101D36] font-tabular mt-1.5">
                  {distinctSections}
                </p>
                <p className="text-[11px] text-[#8FA3BF] mt-1">Teaching groups</p>
              </div>
              <div className="w-10 h-10 rounded-xl bg-[#EEE7FF] text-[#8055E8] flex items-center justify-center shrink-0 shadow-2xs">
                <Users size={20} />
              </div>
            </div>

            {/* Card 4: Allocated Rooms & Labs */}
            <div className="bg-white rounded-2xl border border-[#E3EBF6] p-4 sm:p-5 shadow-xs flex items-start justify-between">
              <div>
                <p className="text-xs font-bold text-[#647795]">Campus Rooms / Labs</p>
                <p className="text-2xl sm:text-3xl font-extrabold text-[#101D36] font-tabular mt-1.5">
                  {distinctRooms}
                </p>
                <p className="text-[11px] text-[#8FA3BF] mt-1">Allocated facilities</p>
              </div>
              <div className="w-10 h-10 rounded-xl bg-[#FFF0E1] text-[#C87917] flex items-center justify-center shrink-0 shadow-2xs">
                <MapPin size={20} />
              </div>
            </div>
          </div>

          {/* ── Timetable Grid Container ── */}
          <div className="bg-white rounded-3xl border border-[#E3EBF6] p-5 sm:p-6 shadow-xs">
            <PersonalTimetableGrid
              entries={entries}
              role="FACULTY"
              workingDays={timetable?.working_days || 'MON_SAT'}
              emptyMessage="No published timetable entries found for your teaching assignments"
            />
          </div>
        </>
      )}
    </div>
  );
};

export default FacultyTimetablePage;
