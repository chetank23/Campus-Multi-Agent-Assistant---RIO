import React, { useMemo, useState } from 'react';
import {
  CalendarDays,
  Clock,
  Grid3X3,
  ListFilter,
} from 'lucide-react';
import type { PersonalTimetableEntry } from '@/api/timetable';
import { formatTime12h } from '@/utils/timeFormatter';

export interface PersonalTimetableGridProps {
  entries: PersonalTimetableEntry[];
  role: 'FACULTY' | 'STUDENT';
  emptyMessage?: string;
  workingDays?: 'MON_FRI' | 'MON_SAT';
}

const ALL_DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];

const DAY_LABELS: Record<string, string> = {
  MON: 'Monday',
  TUE: 'Tuesday',
  WED: 'Wednesday',
  THU: 'Thursday',
  FRI: 'Friday',
  SAT: 'Saturday',
  SUN: 'Sunday',
};

// 7 Instructional Periods + 2 Institutional Breaks (Authoritative schedule)
const STANDARD_PERIOD_COLUMNS = [
  { key: 'P1', timeLabel: '08:30–09:25', name: 'Period 1', start: '08:30', end: '09:25', isBreak: false },
  { key: 'P2', timeLabel: '09:25–10:20', name: 'Period 2', start: '09:25', end: '10:20', isBreak: false },
  { key: 'TEA_BREAK', timeLabel: '10:20–10:40', name: 'Tea Break', start: '10:20', end: '10:40', isBreak: true },
  { key: 'P3', timeLabel: '10:40–11:35', name: 'Period 3', start: '10:40', end: '11:35', isBreak: false },
  { key: 'P4', timeLabel: '11:35–12:30', name: 'Period 4', start: '11:35', end: '12:30', isBreak: false },
  { key: 'LUNCH_BREAK', timeLabel: '12:30–13:30', name: 'Lunch Break', start: '12:30', end: '13:30', isBreak: true },
  { key: 'P5', timeLabel: '13:30–14:25', name: 'Period 5', start: '13:30', end: '14:25', isBreak: false },
  { key: 'P6', timeLabel: '14:25–15:20', name: 'Period 6', start: '14:25', end: '15:20', isBreak: false },
  { key: 'P7', timeLabel: '15:20–16:15', name: 'Period 7', start: '15:20', end: '16:15', isBreak: false },
];

export const PersonalTimetableGrid: React.FC<PersonalTimetableGridProps> = ({
  entries,
  role,
  emptyMessage = 'No schedule entries found.',
  workingDays = 'MON_SAT',
}) => {
  const [activeDay, setActiveDay] = useState<string>('ALL');
  const [viewMode, setViewMode] = useState<'grid' | 'agenda'>('grid');

  // Determine active days based on workingDays prop and actual entries
  const activeDaysList = useMemo(() => {
    if (workingDays === 'MON_FRI') {
      return ['MON', 'TUE', 'WED', 'THU', 'FRI'];
    }
    return ALL_DAYS;
  }, [workingDays]);

  // Group entries by day
  const entriesByDay = useMemo(() => {
    const map: Record<string, PersonalTimetableEntry[]> = {};
    activeDaysList.forEach((d) => {
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
      if (map[key]) {
        map[key].push(entry);
      }
    });

    // Sort entries within each day chronologically
    Object.keys(map).forEach((d) => {
      map[d].sort((a, b) => (a.start_time || '').localeCompare(b.start_time || ''));
    });

    return map;
  }, [entries, activeDaysList]);

  const filteredDays = useMemo(() => {
    if (activeDay === 'ALL') return activeDaysList;
    return [activeDay];
  }, [activeDay, activeDaysList]);

  if (!entries || entries.length === 0) {
    if (role === 'STUDENT') {
      return (
        <div className="bg-[#F1F6FF]/60 rounded-[20px] border border-[#E5ECF5] p-10 sm:p-12 text-center">
          <div className="w-14 h-14 rounded-2xl bg-[#EBF3FE] border border-[#D0E2FC] text-[#4B83D1] mx-auto flex items-center justify-center mb-3.5 shadow-xs">
            <CalendarDays size={26} />
          </div>
          <h3 className="text-sm font-bold text-[#17243B]">{emptyMessage}</h3>
          <p className="text-xs text-[#71819A] mt-1.5 max-w-sm mx-auto leading-relaxed">
            When an administrator publishes the timetable for your section, your complete scheduled classes will appear here.
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
          When an administrator publishes the timetable for your department, your complete teaching assignments will appear here.
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
          {activeDaysList.map((d) => {
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
            <table className="w-full border-collapse min-w-[850px]">
              <thead>
                <tr className="bg-slate-50/80 border-b border-slate-200/90">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider w-28 shrink-0">
                    Day
                  </th>
                  {STANDARD_PERIOD_COLUMNS.map((col) => (
                    <th
                      key={col.key}
                      className={`px-2.5 py-3 text-center border-l border-slate-200/60 ${
                        col.isBreak ? 'bg-amber-50/40 w-24' : 'w-32'
                      }`}
                    >
                      <div className="text-xs font-bold font-tabular text-slate-900 leading-snug">
                        {col.timeLabel}
                      </div>
                      <div className="text-[10px] font-medium text-slate-500 mt-0.5">
                        {col.name}
                      </div>
                    </th>
                  ))}
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

                      {STANDARD_PERIOD_COLUMNS.map((col) => {
                        if (col.isBreak) {
                          return (
                            <td
                              key={col.key}
                              className="px-1 py-2 align-middle text-center border-l border-slate-200/50 bg-amber-50/30 text-amber-900/60 select-none"
                            >
                              <div className="h-full min-h-[80px] flex flex-col items-center justify-center text-[11px] font-semibold tracking-wider uppercase">
                                <span>{col.name}</span>
                              </div>
                            </td>
                          );
                        }

                        const matches = dayEntries.filter(
                          (e) => (e.start_time || '').slice(0, 5) === col.start
                        );

                        if (matches.length === 0) {
                          return (
                            <td
                              key={col.key}
                              className="px-2 py-3 align-top text-center border-l border-slate-200/40 text-slate-300 text-xs"
                            >
                              <div className="h-full min-h-[80px] flex items-center justify-center rounded-lg border border-dashed border-slate-100 bg-slate-50/20 text-[11px]">
                                —
                              </div>
                            </td>
                          );
                        }

                        return (
                          <td
                            key={col.key}
                            className="px-2 py-2.5 align-top border-l border-slate-200/40 min-h-[110px]"
                          >
                            <div className="flex flex-col gap-2">
                              {matches.map((match, mIdx) => {
                                const isLab =
                                  match.slot_type === 'LAB' ||
                                  match.course_type === 'LAB' ||
                                  match.course_type === 'PRACTICAL';

                                return (
                                  <div
                                    key={match.id || `${match.course_code}-${mIdx}`}
                                    className={`rounded-lg p-2.5 border transition-shadow shadow-xs hover:shadow-subtle ${
                                      isLab
                                        ? 'bg-amber-50/90 border-amber-200 text-amber-950'
                                        : 'bg-primary-50/90 border-primary-200 text-primary-950'
                                    }`}
                                  >
                                    <div className="flex items-start justify-between gap-1 mb-1">
                                      <span className="font-extrabold text-xs text-slate-900 tracking-tight">
                                        {match.course_code || 'COURSE'}
                                      </span>
                                      <span
                                        className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${
                                          isLab
                                            ? 'bg-amber-200 text-amber-900'
                                            : 'bg-primary-200 text-primary-900'
                                        }`}
                                      >
                                        {isLab ? 'Lab' : match.course_type || 'Theory'}
                                      </span>
                                    </div>

                                    {/* Subject Title */}
                                    <div className="text-[11px] font-medium leading-snug mb-2 text-slate-800 break-words">
                                      {match.course_name || 'Scheduled Session'}
                                    </div>

                                    <div className="space-y-1 text-[11px] pt-1.5 border-t border-slate-200/70 text-slate-700">
                                      <div className="flex items-center gap-1">
                                        <span className="text-slate-500 font-normal">Room:</span>
                                        <span className="font-bold text-slate-900">
                                          {match.room_number || 'TBD'}
                                        </span>
                                        {match.building_name && (
                                          <span className="text-slate-400 font-normal text-[10px]">
                                            ({match.building_name})
                                          </span>
                                        )}
                                      </div>

                                      {role === 'FACULTY' && match.section_name && (
                                        <div className="flex items-center gap-1">
                                          <span className="text-slate-500 font-normal">Sec:</span>
                                          <span className="font-semibold text-slate-800">
                                            {match.section_name}
                                          </span>
                                          {match.batch_name && (
                                            <span className="text-slate-400 font-semibold text-[10px]">
                                              • {match.batch_name}
                                            </span>
                                          )}
                                        </div>
                                      )}

                                      {match.faculty_name && (
                                        <div className="flex items-start gap-1">
                                          <span className="text-slate-500 font-normal shrink-0">Faculty:</span>
                                          <span className="font-semibold text-slate-900 break-words">
                                            {match.faculty_name}
                                          </span>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
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
                              {e.start_time && e.end_time
                                ? `${formatTime12h(e.start_time)} – ${formatTime12h(e.end_time)}`
                                : 'Time TBD'}
                            </div>
                            <span
                              className={`text-[10px] font-semibold px-1.5 py-0.5 rounded inline-block mt-0.5 ${
                                isLab ? 'bg-amber-100 text-amber-800' : 'bg-primary-100 text-primary-800'
                              }`}
                            >
                              {isLab ? 'Lab / Practical' : e.course_type || 'Theory'}
                            </span>
                          </div>
                        </div>

                        {/* Course details */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-slate-900 font-tabular">
                              {e.course_code || 'COURSE'}
                            </span>
                            <span className="text-xs font-semibold text-slate-800 truncate">
                              {e.course_name || 'Scheduled Session'}
                            </span>
                          </div>
                          <div className="text-xs text-slate-500 mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                            <span>
                              Room: <strong className="text-slate-700">{e.room_number || 'TBD'}</strong>
                              {e.building_name && ` (${e.building_name})`}
                            </span>
                            {role === 'FACULTY' && e.section_name && (
                              <span>
                                Section: <strong className="text-slate-700">{e.section_name}</strong>
                                {e.batch_name && ` • ${e.batch_name}`}
                              </span>
                            )}
                            {e.faculty_name && (
                              <span>
                                Faculty: <strong className="text-slate-700">{e.faculty_name}</strong>
                              </span>
                            )}
                          </div>
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
