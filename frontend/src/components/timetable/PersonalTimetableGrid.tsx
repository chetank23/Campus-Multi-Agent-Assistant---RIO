import React, { useMemo, useState } from 'react';
import {
  CalendarDays,
  Clock,
  MapPin,
  User,
  Users,
  Grid3X3,
  ListFilter,
} from 'lucide-react';
import type { PersonalTimetableEntry } from '@/api/timetable';
import { formatTime12h } from '@/utils/timeFormatter';
import { StatusBadge } from '@/components/common/StatusBadge';

interface PersonalTimetableGridProps {
  entries: PersonalTimetableEntry[];
  role: 'FACULTY' | 'STUDENT';
  emptyMessage?: string;
}

const DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];

const DAY_LABELS: Record<string, string> = {
  MON: 'Monday',
  TUE: 'Tuesday',
  WED: 'Wednesday',
  THU: 'Thursday',
  FRI: 'Friday',
  SAT: 'Saturday',
  SUN: 'Sunday',
};

export const PersonalTimetableGrid: React.FC<PersonalTimetableGridProps> = ({
  entries,
  role,
  emptyMessage = 'No schedule entries found.',
}) => {
  const [activeDay, setActiveDay] = useState<string>('ALL');
  const [viewMode, setViewMode] = useState<'grid' | 'agenda'>('grid');

  // Group entries by day
  const entriesByDay = useMemo(() => {
    const map: Record<string, PersonalTimetableEntry[]> = {};
    DAYS.forEach((d) => {
      map[d] = [];
    });

    entries.forEach((entry) => {
      const d = entry.day?.toUpperCase() || 'MON';
      const key = d.startsWith('MON') ? 'MON' :
                  d.startsWith('TUE') ? 'TUE' :
                  d.startsWith('WED') ? 'WED' :
                  d.startsWith('THU') ? 'THU' :
                  d.startsWith('FRI') ? 'FRI' :
                  d.startsWith('SAT') ? 'SAT' : 'MON';
      if (!map[key]) map[key] = [];
      map[key].push(entry);
    });

    // Sort entries within each day by start_time
    Object.keys(map).forEach((d) => {
      map[d].sort((a, b) => (a.start_time || '').localeCompare(b.start_time || ''));
    });

    return map;
  }, [entries]);

  // Distinct time intervals across all days for the grid view
  const timeIntervals = useMemo(() => {
    const set = new Set<string>();
    entries.forEach((e) => {
      if (e.start_time && e.end_time) {
        set.add(`${e.start_time}-${e.end_time}`);
      }
    });
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [entries]);

  const filteredDays = useMemo(() => {
    if (activeDay === 'ALL') return DAYS;
    return [activeDay];
  }, [activeDay]);

  if (!entries || entries.length === 0) {
    if (role === 'STUDENT') {
      return (
        <div className="bg-[#F1F6FF]/60 rounded-[20px] border border-[#E5ECF5] p-10 sm:p-12 text-center">
          <div className="w-14 h-14 rounded-2xl bg-[#EBF3FE] border border-[#D0E2FC] text-[#4B83D1] mx-auto flex items-center justify-center mb-3.5 shadow-xs">
            <CalendarDays size={26} />
          </div>
          <h3 className="text-sm font-bold text-[#17243B]">{emptyMessage}</h3>
          <p className="text-xs text-[#71819A] mt-1.5 max-w-sm mx-auto leading-relaxed">
            When an administrator publishes a verified timetable version for your section, your complete scheduled classes will appear here.
          </p>
        </div>
      );
    }

    return (
      <div className="bg-[#F8FAFD] rounded-2xl border border-[#E3EBF6] p-10 sm:p-12 text-center my-2">
        <div className="w-14 h-14 rounded-2xl bg-[#E4EEFF] text-[#3975D1] mx-auto flex items-center justify-center mb-3 shadow-2xs">
          <CalendarDays size={26} />
        </div>
        <h3 className="text-sm font-bold text-[#101D36]">{emptyMessage}</h3>
        <p className="text-xs text-[#647795] mt-1 max-w-sm mx-auto leading-relaxed">
          When an administrator publishes a verified timetable version for your department, your complete teaching assignments will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* View Switcher and Day Filter */}
      <div className="bg-white rounded-2xl border border-[#E3EBF6] p-3 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Day selection tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          <button
            type="button"
            onClick={() => setActiveDay('ALL')}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-colors ${
              activeDay === 'ALL'
                ? 'bg-[#3975D1] text-white shadow-xs'
                : 'text-[#647795] hover:text-[#101D36] hover:bg-[#F1F6FD]'
            }`}
          >
            Full Week ({entries.length})
          </button>
          {DAYS.map((d) => {
            const count = entriesByDay[d]?.length || 0;
            return (
              <button
                key={d}
                type="button"
                onClick={() => setActiveDay(d)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-colors flex items-center gap-1.5 ${
                  activeDay === d
                    ? 'bg-[#3975D1] text-white shadow-xs'
                    : 'text-[#647795] hover:text-[#101D36] hover:bg-[#F1F6FD]'
                }`}
              >
                <span>{DAY_LABELS[d]}</span>
                {count > 0 && (
                  <span
                    className={`px-1.5 py-0.2 rounded-full text-[10px] ${
                      activeDay === d ? 'bg-[#2F65B8] text-white' : 'bg-[#E3EBF6] text-[#101D36]'
                    }`}
                  >
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* View mode toggle */}
        <div className="flex items-center gap-1 self-end sm:self-auto shrink-0 bg-slate-100 p-1 rounded-lg border border-slate-200/80">
          <button
            type="button"
            onClick={() => setViewMode('grid')}
            title="Grid View"
            aria-label="Grid View"
            className={`p-1.5 rounded-md text-xs font-medium transition-colors ${
              viewMode === 'grid'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            <Grid3X3 size={15} />
          </button>
          <button
            type="button"
            onClick={() => setViewMode('agenda')}
            title="Agenda View"
            aria-label="Agenda View"
            className={`p-1.5 rounded-md text-xs font-medium transition-colors ${
              viewMode === 'agenda'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            <ListFilter size={15} />
          </button>
        </div>
      </div>

      {/* Grid Mode */}
      {viewMode === 'grid' && (
        <div className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse min-w-[700px]">
              <thead>
                <tr className="bg-slate-50/80 border-b border-slate-200/90">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider w-28 shrink-0">
                    Day
                  </th>
                  {timeIntervals.map((interval) => {
                    const [start, end] = interval.split('-');
                    return (
                      <th
                        key={interval}
                        className="px-3 py-3 text-center text-xs font-semibold text-slate-700 tracking-tight font-tabular border-l border-slate-200/60"
                      >
                        <div className="flex items-center justify-center gap-1 text-slate-800">
                          <Clock size={12} className="text-slate-400" />
                          <span>{formatTime12h(start)}</span>
                        </div>
                        <div className="text-[10px] text-slate-400 font-normal">
                          to {formatTime12h(end)}
                        </div>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredDays.map((d) => {
                  const dayEntries = entriesByDay[d] || [];
                  return (
                    <tr key={d} className="hover:bg-slate-50/40 transition-colors">
                      <td className="px-4 py-4 align-top font-bold text-xs text-slate-900 border-r border-slate-200/60 bg-slate-50/30">
                        <div className="uppercase tracking-wider">{DAY_LABELS[d]}</div>
                        <div className="text-[11px] font-normal text-slate-400 mt-0.5">
                          {dayEntries.length} {dayEntries.length === 1 ? 'class' : 'classes'}
                        </div>
                      </td>

                      {timeIntervals.map((interval) => {
                        const [start, end] = interval.split('-');
                        const match = dayEntries.find(
                          (e) => e.start_time === start && e.end_time === end
                        );

                        if (!match) {
                          return (
                            <td
                              key={interval}
                              className="px-2 py-3 align-top text-center border-l border-slate-200/40 text-slate-300 text-xs"
                            >
                              <div className="h-full min-h-[72px] flex items-center justify-center rounded-lg border border-dashed border-slate-100 bg-slate-50/20 text-[11px]">
                                —
                              </div>
                            </td>
                          );
                        }

                        const isLab =
                          match.slot_type === 'LAB' ||
                          match.course_type === 'LAB' ||
                          match.course_type === 'PRACTICAL';

                        return (
                          <td
                            key={interval}
                            className="px-2 py-2.5 align-top border-l border-slate-200/40"
                          >
                            <div
                              className={`rounded-lg p-2.5 border transition-shadow shadow-xs hover:shadow-subtle ${
                                isLab
                                  ? 'bg-amber-50/80 border-amber-200 text-amber-950'
                                  : 'bg-primary-50/80 border-primary-200 text-primary-950'
                              }`}
                            >
                              <div className="flex items-start justify-between gap-1 mb-1">
                                <span className="font-bold text-xs tracking-tight truncate">
                                  {match.course_code || 'COURSE'}
                                </span>
                                <span
                                  className={`text-[9px] font-bold px-1.5 py-0.2 rounded uppercase ${
                                    isLab
                                      ? 'bg-amber-200 text-amber-900'
                                      : 'bg-primary-200 text-primary-900'
                                  }`}
                                >
                                  {match.course_type || 'THEORY'}
                                </span>
                              </div>

                              <p className="text-[11px] font-medium leading-tight line-clamp-2 mb-2 text-slate-800">
                                {match.course_name || 'Scheduled Session'}
                              </p>

                              <div className="space-y-1 text-[10px] pt-1.5 border-t border-slate-200/60 text-slate-600">
                                {match.room_number && (
                                  <div className="flex items-center gap-1 truncate">
                                    <MapPin size={10} className="shrink-0 text-slate-400" />
                                    <span className="font-semibold text-slate-700">
                                      {match.room_number}
                                    </span>
                                    {match.building_name && (
                                      <span className="text-slate-400 truncate">
                                        ({match.building_name})
                                      </span>
                                    )}
                                  </div>
                                )}

                                {role === 'FACULTY' && match.section_name && (
                                  <div className="flex items-center gap-1 truncate">
                                    <Users size={10} className="shrink-0 text-slate-400" />
                                    <span>Section {match.section_name}</span>
                                    {match.batch_name && (
                                      <span className="text-slate-400 font-semibold">
                                        • {match.batch_name}
                                      </span>
                                    )}
                                  </div>
                                )}

                                {role === 'STUDENT' && match.faculty_name && (
                                  <div className="flex items-center gap-1 truncate">
                                    <User size={10} className="shrink-0 text-slate-400" />
                                    <span className="truncate">{match.faculty_name}</span>
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Agenda Mode (Chronological Cards) */}
      {viewMode === 'agenda' && (
        <div className="space-y-6">
          {filteredDays.map((d) => {
            const dayEntries = entriesByDay[d] || [];
            if (dayEntries.length === 0) return null;

            return (
              <div
                key={d}
                className="bg-white rounded-xl border border-slate-200/90 shadow-card overflow-hidden"
              >
                <div className="px-5 py-3.5 bg-slate-50/90 border-b border-slate-200/80 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <CalendarDays size={16} className="text-primary-600" />
                    <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
                      {DAY_LABELS[d]}
                    </h3>
                  </div>
                  <span className="text-xs font-semibold text-slate-500 font-tabular">
                    {dayEntries.length} {dayEntries.length === 1 ? 'class session' : 'class sessions'}
                  </span>
                </div>

                <div className="p-4 divide-y divide-slate-100 space-y-3">
                  {dayEntries.map((e) => {
                    const isLab =
                      e.slot_type === 'LAB' ||
                      e.course_type === 'LAB' ||
                      e.course_type === 'PRACTICAL';

                    return (
                      <div
                        key={e.id}
                        className="pt-3 first:pt-0 flex flex-col md:flex-row md:items-center justify-between gap-3 hover:bg-slate-50/60 p-2.5 rounded-lg transition-colors"
                      >
                        {/* Time & Type */}
                        <div className="flex items-center gap-3 md:w-56 shrink-0">
                          <div className="w-9 h-9 rounded-lg bg-slate-100 border border-slate-200 text-slate-600 flex items-center justify-center shrink-0">
                            <Clock size={16} />
                          </div>
                          <div>
                            <div className="text-xs font-bold text-slate-900 font-tabular">
                              {formatTime12h(e.start_time)} – {formatTime12h(e.end_time)}
                            </div>
                            <div className="text-[11px] text-slate-400 capitalize">
                              {e.slot_type?.toLowerCase() || 'Session'}
                            </div>
                          </div>
                        </div>

                        {/* Course info */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-bold text-xs text-primary-700 bg-primary-50 px-2 py-0.5 rounded border border-primary-200/80">
                              {e.course_code || 'CODE'}
                            </span>
                            <span className="text-sm font-semibold text-slate-900 truncate">
                              {e.course_name || 'Course Name'}
                            </span>
                            <span
                              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                                isLab
                                  ? 'bg-amber-100 text-amber-800'
                                  : 'bg-slate-100 text-slate-700'
                              }`}
                            >
                              {e.course_type || 'THEORY'}
                            </span>
                          </div>
                        </div>

                        {/* Location & Meta */}
                        <div className="flex items-center gap-4 text-xs text-slate-600 shrink-0">
                          {e.room_number && (
                            <div className="flex items-center gap-1.5">
                              <MapPin size={13} className="text-slate-400" />
                              <span className="font-semibold text-slate-800">{e.room_number}</span>
                              {e.building_name && (
                                <span className="text-slate-400 hidden lg:inline">
                                  ({e.building_name})
                                </span>
                              )}
                            </div>
                          )}

                          {role === 'FACULTY' && e.section_name && (
                            <div className="flex items-center gap-1.5">
                              <Users size={13} className="text-slate-400" />
                              <span>Sec {e.section_name}</span>
                              {e.batch_name && (
                                <span className="font-semibold text-slate-800">
                                  [{e.batch_name}]
                                </span>
                              )}
                            </div>
                          )}

                          {role === 'STUDENT' && e.faculty_name && (
                            <div className="flex items-center gap-1.5">
                              <User size={13} className="text-slate-400" />
                              <span className="font-medium text-slate-800">{e.faculty_name}</span>
                            </div>
                          )}

                          <StatusBadge status={e.status} size="sm" />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
