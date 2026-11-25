import React, { useCallback, useMemo, useState } from 'react';
import { Download, Printer } from 'lucide-react';
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import type {
  MoveOptionSlot,
  TimetableEntryDetailResponse,
  TimetableEntryResponse,
  TimetableEntryResult,
  TimetableVersionDetailResponse,
} from '@/api/timetable';
import type { TimeSlotResponse } from '@/api/timeSlots';
import type { CourseAssignmentResponse } from '@/api/courseAssignments';
import type { CourseResponse } from '@/api/courses';
import type { FacultyResponse } from '@/api/faculty';
import type { RoomResponse } from '@/api/rooms';
import { TimetableCell } from './TimetableCell';
import { EditEntryModal } from './EditEntryModal';
import { exportTimetableToPDF } from '@/utils/pdfGenerator';

type AnyTimetableEntry = TimetableEntryResult | TimetableEntryResponse | TimetableEntryDetailResponse;

interface TimetableGridProps {
  entries: AnyTimetableEntry[];
  timeSlots: TimeSlotResponse[];
  assignments: CourseAssignmentResponse[];
  courses: CourseResponse[];
  facultyList: FacultyResponse[];
  rooms: RoomResponse[];
  versionDetail?: TimetableVersionDetailResponse;
  isEditable?: boolean;
  onEntryUpdated?: () => void;
  dndEnabled?: boolean;
  moveOptionsMap?: Record<number, MoveOptionSlot>;
  pendingEntryIds?: Set<number>;
  highlightedEntryIds?: Set<number>;
  onDragStartEntry?: (entryId: number) => void;
  onDropOnSlot?: (entryId: number, targetSlotId: number, slotOption?: MoveOptionSlot) => void;
  onDragCancelEntry?: () => void;
}

const DraggableEntryCard: React.FC<{
  entryId: number;
  disabled: boolean;
  children: React.ReactNode;
}> = ({ entryId, disabled, children }) => {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `entry-${entryId}`,
    data: { entryId },
    disabled,
  });

  const style: React.CSSProperties = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging ? 0.35 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...(disabled ? {} : listeners)}
      {...(disabled ? {} : attributes)}
      data-testid={`draggable-entry-${entryId}`}
    >
      {children}
    </div>
  );
};

const DroppableSlotTd: React.FC<{
  slotId: number | null;
  dayKey: string;
  timeKey: string;
  dndEnabled: boolean;
  isDraggingActive: boolean;
  moveOption?: MoveOptionSlot;
  children: React.ReactNode;
}> = ({ slotId, dayKey, timeKey, dndEnabled, isDraggingActive, moveOption, children }) => {
  const { setNodeRef, isOver } = useDroppable({
    id: slotId ? `slot-${slotId}` : `slot-${dayKey}-${timeKey}`,
    data: { slotId, dayKey, timeKey },
    disabled: !dndEnabled || !slotId,
  });

  let highlightClass = '';
  let titleText: string | undefined;
  const moveStatus = !moveOption
    ? undefined
    : !moveOption.can_move
      ? 'BLOCKED'
      : moveOption.warnings.length > 0
        ? 'WARNING'
        : 'VALID';

  if (dndEnabled && isDraggingActive && moveOption) {
    if (moveStatus === 'VALID') {
      highlightClass = isOver
        ? 'bg-emerald-100 ring-2 ring-emerald-500'
        : 'bg-emerald-50/80 ring-1 ring-inset ring-emerald-300';
      titleText = 'Valid destination — drop to move';
    } else if (moveStatus === 'WARNING') {
      highlightClass = isOver
        ? 'bg-amber-100 ring-2 ring-amber-500'
        : 'bg-amber-50/80 ring-1 ring-inset ring-amber-300';
      titleText = moveOption.warnings.join('; ') || 'Warning';
    } else if (moveStatus === 'BLOCKED') {
      highlightClass = isOver
        ? 'bg-red-100 ring-2 ring-red-500'
        : 'bg-red-50/60 ring-1 ring-inset ring-red-200';
      titleText = moveOption.blocked_reason || 'Blocked destination';
    }
  } else if (dndEnabled && isOver) {
    highlightClass = 'bg-indigo-50 ring-2 ring-indigo-400';
  }

  return (
    <td
      ref={setNodeRef}
      title={titleText}
      data-testid={slotId ? `timetable-slot-${slotId}` : `timetable-slot-${dayKey}-${timeKey}`}
      data-slot-status={moveStatus}
      className={`p-2 border-r last:border-r-0 border-slate-200 min-h-[110px] align-top transition-colors ${highlightClass}`}
    >
      {children}
    </td>
  );
};

const DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];

const DAY_LABELS: Record<string, string> = {
  MON: 'Monday',
  TUE: 'Tuesday',
  WED: 'Wednesday',
  THU: 'Thursday',
  FRI: 'Friday',
  SAT: 'Saturday',
};

const normalizeDay = (d?: string | null): string => {
  if (!d) return 'MON';
  const u = d.toUpperCase().trim();
  if (u.startsWith('MON')) return 'MON';
  if (u.startsWith('TUE')) return 'TUE';
  if (u.startsWith('WED')) return 'WED';
  if (u.startsWith('THU')) return 'THU';
  if (u.startsWith('FRI')) return 'FRI';
  if (u.startsWith('SAT')) return 'SAT';
  return u.slice(0, 3);
};

export const TimetableGrid: React.FC<TimetableGridProps> = ({
  entries,
  timeSlots,
  assignments,
  courses,
  facultyList,
  rooms,
  versionDetail,
  isEditable = false,
  onEntryUpdated,
  dndEnabled = false,
  moveOptionsMap = {},
  pendingEntryIds,
  highlightedEntryIds,
  onDragStartEntry,
  onDropOnSlot,
  onDragCancelEntry,
}) => {
  const [editingEntry, setEditingEntry] = useState<TimetableEntryResponse | null>(null);
  const [activeDragEntryId, setActiveDragEntryId] = useState<number | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    }),
  );

  const slotLookupByDayTime = useMemo(() => {
    const map = new Map<string, TimeSlotResponse>();
    timeSlots.forEach((slot) => {
      const dayKey = normalizeDay(slot.day);
      const start = (slot.start_time || '').slice(0, 5);
      const end = (slot.end_time || '').slice(0, 5);
      map.set(`${dayKey}::${start}-${end}`, slot);
    });
    return map;
  }, [timeSlots]);

  const handleDragStart = (event: DragStartEvent) => {
    const entryId = event.active.data.current?.entryId as number | undefined;
    if (entryId) {
      setActiveDragEntryId(entryId);
      onDragStartEntry?.(entryId);
    }
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const entryId = event.active.data.current?.entryId as number | undefined;
    const targetSlotId = event.over?.data.current?.slotId as number | undefined;
    setActiveDragEntryId(null);
    if (entryId && targetSlotId) {
      onDropOnSlot?.(entryId, targetSlotId, moveOptionsMap[targetSlotId]);
    } else {
      onDragCancelEntry?.();
    }
  };

  const handleDragCancel = () => {
    setActiveDragEntryId(null);
    onDragCancelEntry?.();
  };

  // Sort time slots by start_time
  const sortedSlots = useMemo(() => {
    const uniqueTimes = new Map<string, TimeSlotResponse>();
    timeSlots.forEach((slot) => {
      const start = (slot.start_time || '').slice(0, 5);
      const end = (slot.end_time || '').slice(0, 5);
      const key = `${start}-${end}`;
      if (!uniqueTimes.has(key)) {
        uniqueTimes.set(key, slot);
      }
    });
    return Array.from(uniqueTimes.values()).sort((a, b) => (a.start_time || '').localeCompare(b.start_time || ''));
  }, [timeSlots]);

  // Group entries by day and time signature
  const matrix = useMemo(() => {
    const mat: Record<string, Record<string, AnyTimetableEntry[]>> = {};
    DAYS.forEach((day) => {
      mat[day] = {};
      sortedSlots.forEach((slot) => {
        const start = (slot.start_time || '').slice(0, 5);
        const end = (slot.end_time || '').slice(0, 5);
        const timeKey = `${start}-${end}`;
        mat[day][timeKey] = [];
      });
    });

    entries.forEach((entry) => {
      const slot = timeSlots.find((s) => s.id === entry.slot_id);
      const dayKey = normalizeDay(slot?.day);
      if (slot && mat[dayKey]) {
        const start = (slot.start_time || '').slice(0, 5);
        const end = (slot.end_time || '').slice(0, 5);
        const timeKey = `${start}-${end}`;
        if (mat[dayKey][timeKey]) {
          mat[dayKey][timeKey].push(entry);
        }
      }
    });

    return mat;
  }, [entries, timeSlots, sortedSlots]);

  const getCellData = useCallback((entry: AnyTimetableEntry) => {
    let courseId: number | undefined;
    let facultyId: number | undefined;
    let hourType: string;

    if (!('id' in entry) && 'course_assignment_id' in entry) {
      const assignment = assignments.find((a) => a.id === entry.course_assignment_id);
      courseId = assignment?.course_id;
      facultyId = assignment?.faculty_id;
      hourType = entry.hour_type || 'THEORY';
    } else {
      courseId = entry.course_id || undefined;
      facultyId = entry.faculty_id || undefined;
      const room = rooms.find((r) => r.id === entry.room_id);
      hourType = ('hour_type' in entry && entry.hour_type) ? entry.hour_type : (room?.room_type === 'LAB' ? 'PRACTICAL' : 'THEORY');
    }

    const course = courses.find((c) => c.id === courseId);
    const faculty = facultyList.find((f) => f.id === facultyId);
    const room = rooms.find((r) => r.id === entry.room_id);

    return {
      courseCode: course?.course_code || `Course ${courseId}`,
      courseName: course?.course_name || '',
      facultyName: faculty?.name || (faculty?.user_id ? `Faculty ${faculty.id}` : `Faculty ${facultyId}`),
      facultyDesignation: faculty?.designation || '',
      facultyContact: faculty?.contact_number || '',
      roomName: room?.room_number || (entry.room_id ? `Room ${entry.room_id}` : ''),
      hourType,
    };
  }, [assignments, courses, facultyList, rooms]);

  // Derive unique course-faculty mapping for reference table below grid
  const courseReferenceList = useMemo(() => {
    const map = new Map<string, { code: string; name: string; faculty: string; designation: string; contact: string }>();

    entries.forEach((entry) => {
      const data = getCellData(entry);
      if (data.courseCode) {
        const key = `${data.courseCode}-${data.facultyName}`;
        if (!map.has(key)) {
          map.set(key, {
            code: data.courseCode,
            name: data.courseName,
            faculty: data.facultyName,
            designation: data.facultyDesignation || '—',
            contact: data.facultyContact || '—',
          });
        }
      }
    });

    return Array.from(map.values());
  }, [entries, getCellData]);

  const handleExportPDF = () => {
    if (versionDetail) {
      exportTimetableToPDF({ versionDetail });
    }
  };

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="space-y-6">
      {/* Action Toolbar & Official Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-slate-50 border border-slate-200 p-4 rounded-lg shadow-sm print:hidden">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Academic Timetable Matrix</h2>
          <p className="text-xs text-slate-500">Official Departmental Schedule & Faculty Assignment Reference</p>
        </div>
        <div className="flex items-center gap-2">
          {versionDetail && (
            <button
              onClick={handleExportPDF}
              className="inline-flex items-center px-3 py-2 border border-slate-300 rounded-md shadow-sm text-sm font-medium text-slate-700 bg-white hover:bg-slate-100 transition-colors"
            >
              <Download className="w-4 h-4 mr-2 text-slate-600" />
              Export PDF
            </button>
          )}
          <button
            onClick={handlePrint}
            className="inline-flex items-center px-3 py-2 border border-slate-300 rounded-md shadow-sm text-sm font-medium text-slate-700 bg-white hover:bg-slate-100 transition-colors"
          >
            <Printer className="w-4 h-4 mr-2 text-slate-600" />
            Print
          </button>
        </div>
      </div>

      {/* Printable Academic Header Banner */}
      <div className="bg-white border border-slate-300 rounded-lg p-5 shadow-sm space-y-3">
        <div className="border-b border-slate-200 pb-3 flex justify-between items-start">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 uppercase">RIO-MJP ACADEMIC TIMETABLE</h1>
            <p className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
              {versionDetail?.department_name || 'DEPARTMENT SCHEDULE'} {versionDetail?.program_name ? `• ${versionDetail.program_name}` : ''}
            </p>
          </div>
          <div className="text-right text-xs text-slate-500">
            <p><span className="font-semibold text-slate-700">Academic Year:</span> {versionDetail?.academic_year_name || '2025-2026'}</p>
            <p><span className="font-semibold text-slate-700">Semester:</span> {versionDetail?.semester_number ? `Sem ${versionDetail.semester_number}` : 'N/A'}</p>
          </div>
        </div>

        {/* Subheader Context */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
            <span className="font-bold text-slate-700 block">Class / Section</span>
            <span className="text-slate-900">{versionDetail?.section_name || 'Section A'}</span>
          </div>
          <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
            <span className="font-bold text-slate-700 block">Class Teacher</span>
            <span className="text-slate-900 font-medium">{versionDetail?.class_teacher_name || 'Unassigned'}</span>
            {versionDetail?.class_teacher_designation && (
              <span className="text-slate-500 block text-[11px]">{versionDetail.class_teacher_designation}</span>
            )}
          </div>
          <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
            <span className="font-bold text-slate-700 block">Contact Information</span>
            <span className="text-slate-900">{versionDetail?.class_teacher_contact || '—'}</span>
          </div>
        </div>
      </div>

      {/* Main Timetable Matrix Grid */}
      <DndContext
        sensors={sensors}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onDragCancel={handleDragCancel}
      >
      <div className="overflow-x-auto border border-slate-300 rounded-lg shadow-sm bg-white">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="bg-slate-100 border-b border-slate-300 text-slate-700">
              <th className="w-28 p-3.5 border-r border-slate-300 font-bold text-center uppercase tracking-wider text-xs">Day / Time</th>
              {sortedSlots.map((slot) => {
                const start = (slot.start_time || '').slice(0, 5);
                const end = (slot.end_time || '').slice(0, 5);
                const isTeaBreak = slot.slot_type === 'BREAK' || (start === '10:20' && end === '10:40');
                const isLunchBreak = slot.slot_type === 'LUNCH' || (start === '12:30' && end === '13:30');
                const isBreak = isTeaBreak || isLunchBreak;
                const label = isTeaBreak ? 'Tea Break: 10:20–10:40' : isLunchBreak ? 'Lunch Break: 12:30–13:30' : `${start}–${end}`;

                return (
                  <th
                    key={slot.id}
                    className={`p-3 border-r last:border-r-0 border-slate-300 font-bold text-center text-xs tracking-tight ${
                      isBreak ? 'bg-amber-50/90 text-amber-900 w-28' : 'text-slate-900 min-w-[150px]'
                    }`}
                  >
                    <div className="font-bold font-tabular leading-snug">{label}</div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {DAYS.map((dayKey) => (
              <tr key={dayKey} className="border-b last:border-b-0 border-slate-200 hover:bg-slate-50/50 transition-colors">
                {/* Day Header Column */}
                <td className="w-28 p-3.5 border-r border-slate-300 bg-slate-50/90 font-extrabold text-slate-800 text-center uppercase tracking-wide align-top">
                  {DAY_LABELS[dayKey] || dayKey}
                </td>

                {/* Slot Cells */}
                {sortedSlots.map((slot) => {
                  const start = (slot.start_time || '').slice(0, 5);
                  const end = (slot.end_time || '').slice(0, 5);
                  const timeKey = `${start}-${end}`;
                  const cellEntries = matrix[dayKey]?.[timeKey] || [];
                  const daySlot = slotLookupByDayTime.get(`${dayKey}::${timeKey}`);
                  const daySlotId = daySlot?.id ?? null;
                  const moveOption = daySlotId ? moveOptionsMap[daySlotId] : undefined;

                  // Handle explicit Break/Lunch slots
                  const isTeaBreak = slot.slot_type === 'BREAK' || (start === '10:20' && end === '10:40');
                  const isLunchBreak = slot.slot_type === 'LUNCH' || (start === '12:30' && end === '13:30');

                  if (isLunchBreak) {
                    return (
                      <td key={slot.id} className="p-2 border-r last:border-r-0 border-slate-200 bg-amber-50/60 text-amber-800 text-center font-bold text-[11px] tracking-wider uppercase align-middle">
                        <span className="block px-2 py-1 rounded bg-amber-100/60 font-medium">Lunch Break: 12:30–13:30</span>
                      </td>
                    );
                  }
                  if (isTeaBreak) {
                    return (
                      <td key={slot.id} className="p-2 border-r last:border-r-0 border-slate-200 bg-amber-50/60 text-amber-800 text-center font-bold text-[11px] tracking-wider uppercase align-middle">
                        <span className="block px-2 py-1 rounded bg-amber-100/60 font-medium">Tea Break: 10:20–10:40</span>
                      </td>
                    );
                  }

                  return (
                    <DroppableSlotTd
                      key={slot.id}
                      slotId={daySlotId}
                      dayKey={dayKey}
                      timeKey={timeKey}
                      dndEnabled={dndEnabled}
                      isDraggingActive={activeDragEntryId !== null}
                      moveOption={moveOption}
                    >
                      {cellEntries.length === 0 ? (
                        <div className="h-full min-h-[70px] flex items-center justify-center text-slate-300 text-xs italic">
                          {dndEnabled && activeDragEntryId && moveOption?.can_move ? (
                            <span className="text-emerald-700 font-semibold not-italic text-[11px]">Drop here</span>
                          ) : (
                            '—'
                          )}
                        </div>
                      ) : (
                        <div className="flex flex-col gap-2">
                          {cellEntries.map((entry, idx) => {
                            const data = getCellData(entry);
                            const hasId = 'id' in entry;
                            const entryId = hasId ? (entry as TimetableEntryResponse).id : -1;
                            const key = hasId ? entryId : `${entry.course_assignment_id}-${idx}`;
                            const detailEntry = entry as TimetableEntryDetailResponse;
                            const isPending = hasId && Boolean(pendingEntryIds?.has(entryId));
                            const isHighlighted = hasId && Boolean(highlightedEntryIds?.has(entryId));
                            const isMultiPeriod = Boolean(detailEntry.block_group_id);

                            const card = (
                              <div
                                key={key}
                                onClick={() => {
                                  if (isEditable && hasId && !activeDragEntryId) {
                                    setEditingEntry(entry as TimetableEntryResponse);
                                  }
                                }}
                                className={isEditable && hasId ? 'cursor-pointer hover:ring-2 hover:ring-indigo-500 rounded-lg transition-all' : ''}
                              >
                                <TimetableCell
                                  courseCode={data.courseCode}
                                  courseName={data.courseName}
                                  facultyName={data.facultyName}
                                  roomName={data.roomName}
                                  hourType={data.hourType}
                                  sectionName={detailEntry.section_name}
                                  isEditMode={dndEnabled}
                                  isPendingChange={isPending}
                                  isConflictHighlighted={isHighlighted}
                                  isMultiPeriodBlock={isMultiPeriod}
                                />
                              </div>
                            );

                            if (dndEnabled && hasId) {
                              return (
                                <DraggableEntryCard key={key} entryId={entryId} disabled={!dndEnabled}>
                                  {card}
                                </DraggableEntryCard>
                              );
                            }
                            return card;
                          })}
                        </div>
                      )}
                    </DroppableSlotTd>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <DragOverlay>
        {activeDragEntryId !== null ? (() => {
          const activeEntry = entries.find((e) => 'id' in e && e.id === activeDragEntryId);
          if (!activeEntry) return null;
          const data = getCellData(activeEntry);
          return (
            <div className="w-48 shadow-xl opacity-95 rotate-1">
              <TimetableCell
                courseCode={data.courseCode}
                courseName={data.courseName}
                facultyName={data.facultyName}
                roomName={data.roomName}
                hourType={data.hourType}
                isEditMode
              />
            </div>
          );
        })() : null}
      </DragOverlay>
      </DndContext>

      {/* Course & Faculty Detail Reference Table */}
      <div className="bg-white border border-slate-300 rounded-lg p-5 shadow-sm space-y-3">
        <h3 className="text-sm font-bold text-slate-900 border-b border-slate-200 pb-2">Course & Faculty Reference Directory</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-100 border-b border-slate-300 text-slate-700 font-bold">
                <th className="p-2.5 border-r border-slate-300">Course Code</th>
                <th className="p-2.5 border-r border-slate-300">Course Title</th>
                <th className="p-2.5 border-r border-slate-300">Faculty Name</th>
                <th className="p-2.5 border-r border-slate-300">Designation</th>
                <th className="p-2.5">Contact Number</th>
              </tr>
            </thead>
            <tbody>
              {courseReferenceList.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-4 text-center text-slate-400">No course data available for this schedule.</td>
                </tr>
              ) : (
                courseReferenceList.map((c, i) => (
                  <tr key={i} className="border-b last:border-b-0 border-slate-200 hover:bg-slate-50">
                    <td className="p-2.5 border-r border-slate-200 font-mono font-semibold text-slate-800">{c.code}</td>
                    <td className="p-2.5 border-r border-slate-200 text-slate-700">{c.name}</td>
                    <td className="p-2.5 border-r border-slate-200 font-medium text-slate-900">{c.faculty}</td>
                    <td className="p-2.5 border-r border-slate-200 text-slate-600">{c.designation}</td>
                    <td className="p-2.5 text-slate-600">{c.contact}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Edit Entry Modal */}
      {editingEntry && (
        <EditEntryModal
          entry={editingEntry}
          timeSlots={timeSlots}
          facultyList={facultyList}
          rooms={rooms}
          onClose={() => setEditingEntry(null)}
          onSuccess={() => {
            setEditingEntry(null);
            if (onEntryUpdated) onEntryUpdated();
          }}
        />
      )}
    </div>
  );
};
