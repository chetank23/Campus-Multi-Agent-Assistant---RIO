import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Building2,
  CalendarDays,
  Clock,
  Users,
  MapPin,
  RefreshCw,
  Filter,
} from 'lucide-react';
import {
  getFacultyDepartmentTimetable,
} from '@/api/timetable';
import { sectionsApi } from '@/api/sections';
import { semestersApi } from '@/api/semesters';
import { LoadingState, ErrorState } from '@/components/common';
import { formatTime12h } from '@/utils/timeFormatter';

const DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'] as const;

export function FacultyDeptTimetablePage() {
  const [selectedDay, setSelectedDay] = useState<string>('ALL');
  const [selectedSectionId, setSelectedSectionId] = useState<number | 'ALL'>('ALL');
  const [selectedSemesterId, setSelectedSemesterId] = useState<number | 'ALL'>('ALL');

  // Queries
  const { data: deptData, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['faculty-dept-timetable'],
    queryFn: () => getFacultyDepartmentTimetable(),
    staleTime: 60_000,
  });

  const { data: sections } = useQuery({
    queryKey: ['sections'],
    queryFn: sectionsApi.getAll,
    staleTime: 120_000,
  });

  const { data: semesters } = useQuery({
    queryKey: ['semesters'],
    queryFn: semestersApi.getAll,
    staleTime: 120_000,
  });

  const entries = useMemo(() => deptData?.entries || [], [deptData?.entries]);

  const filteredEntries = useMemo(() => {
    return entries.filter((e) => {
      // Day filter
      if (selectedDay !== 'ALL') {
        const d = (e.day || '').toUpperCase();
        if (!d.startsWith(selectedDay)) return false;
      }
      // Section filter
      if (selectedSectionId !== 'ALL') {
        const sec = sections?.find((s) => s.id === selectedSectionId);
        if (sec && e.section_name !== sec.section_name) return false;
      }
      // Semester filter
      if (selectedSemesterId !== 'ALL') {
        if (e.semester_number !== selectedSemesterId) return false;
      }
      return true;
    });
  }, [entries, selectedDay, selectedSectionId, selectedSemesterId, sections]);

  if (isLoading) {
    return (
      <div className="py-12">
        <LoadingState message="Loading department schedule and timetable entries…" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="py-12">
        <ErrorState
          title="Could Not Load Department Timetable"
          message="Failed to fetch published department schedules. Please verify network or credentials."
          onRetry={refetch}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto pb-10">
      {/* Top Banner Header */}
      <div className="bg-[#142542] text-white p-6 rounded-2xl shadow-sm border border-[#1D3152] flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Building2 size={20} className="text-[#38BDF8]" />
            <h1 className="text-xl font-black tracking-tight">
              {deptData?.department_name || 'Department'} Timetable
            </h1>
          </div>
          <p className="text-xs text-[#8FA3BF] mt-1">
            Department Code: <span className="font-mono text-white font-bold">{deptData?.department_code}</span> · {entries.length} Published Teaching Sessions
          </p>
        </div>

        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 px-4 py-2 bg-[#1D3152] hover:bg-[#2B426B] text-white text-xs font-semibold rounded-xl border border-[#2B426B] transition-colors"
        >
          <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Filter Toolbar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs flex flex-wrap items-center justify-between gap-4">
        {/* Day Pills */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => setSelectedDay('ALL')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
              selectedDay === 'ALL'
                ? 'bg-primary-600 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            All Days
          </button>
          {DAYS.map((d) => (
            <button
              key={d}
              onClick={() => setSelectedDay(d)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                selectedDay === d
                  ? 'bg-primary-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {d}
            </button>
          ))}
        </div>

        {/* Section and Semester dropdowns */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <Filter size={14} className="text-slate-400" />
            <select
              value={selectedSectionId}
              onChange={(e) =>
                setSelectedSectionId(
                  e.target.value === 'ALL' ? 'ALL' : Number(e.target.value)
                )
              }
              className="px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/20"
            >
              <option value="ALL">All Sections</option>
              {sections?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.section_name}
                </option>
              ))}
            </select>
          </div>

          <select
            value={selectedSemesterId}
            onChange={(e) =>
              setSelectedSemesterId(
                e.target.value === 'ALL' ? 'ALL' : Number(e.target.value)
              )
            }
            className="px-2.5 py-1.5 border border-slate-200 rounded-lg text-xs bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/20"
          >
            <option value="ALL">All Semesters</option>
            {semesters?.map((sem) => (
              <option key={sem.id} value={sem.semester_number}>
                Semester {sem.semester_number}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Timetable Entries Cards */}
      {filteredEntries.length === 0 ? (
        <div className="p-12 bg-white rounded-2xl border border-slate-200 text-center space-y-2">
          <div className="w-12 h-12 rounded-xl bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
            <CalendarDays size={24} />
          </div>
          <h3 className="text-sm font-bold text-slate-900">No Timetable Sessions Match Filters</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Try adjusting your active day, section, or semester filters.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredEntries.map((item) => (
            <div
              key={item.id}
              className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs hover:border-primary-300 transition-all flex flex-col justify-between space-y-3"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold font-mono px-2 py-0.5 rounded bg-primary-50 text-primary-700 border border-primary-200">
                    {item.course_code || 'N/A'}
                  </span>
                  <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                    {item.day}
                  </span>
                </div>

                <div>
                  <h4 className="text-sm font-bold text-slate-900 line-clamp-1">
                    {item.course_name}
                  </h4>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Section: <span className="font-semibold text-slate-800">{item.section_name || 'All'}</span>
                    {item.semester_number ? ` · Semester ${item.semester_number}` : ''}
                  </p>
                </div>
              </div>

              <div className="pt-2 border-t border-slate-100 space-y-1.5 text-xs text-slate-600">
                <div className="flex items-center gap-2">
                  <Clock size={14} className="text-slate-400 shrink-0" />
                  <span className="font-medium font-mono text-[11px]">
                    {formatTime12h(item.start_time || '')} – {formatTime12h(item.end_time || '')}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <MapPin size={14} className="text-slate-400 shrink-0" />
                  <span>
                    Room {item.room_number || 'TBD'} ({item.building_name || 'Main'})
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <Users size={14} className="text-slate-400 shrink-0" />
                  <span className="truncate">
                    Instructor: <span className="font-semibold text-slate-800">{item.faculty_name || 'Staff'}</span>
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
