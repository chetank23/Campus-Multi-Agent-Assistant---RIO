import React, { useMemo } from 'react';
import type { TimetableEntryResult } from '@/api/timetable';
import type { TimeSlotResponse } from '@/api/timeSlots';
import type { CourseAssignmentResponse } from '@/api/courseAssignments';
import type { CourseResponse } from '@/api/courses';
import type { FacultyResponse } from '@/api/faculty';
import type { RoomResponse } from '@/api/rooms';
import { TimetableCell } from './TimetableCell';

interface TimetableGridProps {
  entries: TimetableEntryResult[];
  timeSlots: TimeSlotResponse[];
  assignments: CourseAssignmentResponse[];
  courses: CourseResponse[];
  facultyList: FacultyResponse[];
  rooms: RoomResponse[];
}

const DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];

export const TimetableGrid: React.FC<TimetableGridProps> = ({
  entries,
  timeSlots,
  assignments,
  courses,
  facultyList,
  rooms,
}) => {
  // Sort time slots by start_time
  const sortedSlots = useMemo(() => {
    // Unique times across all days
    const uniqueTimes = new Map<string, TimeSlotResponse>();
    timeSlots.forEach((slot) => {
      const key = `${slot.start_time}-${slot.end_time}`;
      if (!uniqueTimes.has(key)) {
        uniqueTimes.set(key, slot);
      }
    });
    return Array.from(uniqueTimes.values()).sort((a, b) => a.start_time.localeCompare(b.start_time));
  }, [timeSlots]);

  // Group entries by day and time signature
  const matrix = useMemo(() => {
    const mat: Record<string, Record<string, TimetableEntryResult[]>> = {};
    DAYS.forEach(day => {
      mat[day] = {};
      sortedSlots.forEach(slot => {
        const timeKey = `${slot.start_time}-${slot.end_time}`;
        mat[day][timeKey] = [];
      });
    });

    entries.forEach(entry => {
      const slot = timeSlots.find(s => s.id === entry.slot_id);
      if (slot && mat[slot.day]) {
        const timeKey = `${slot.start_time}-${slot.end_time}`;
        if (mat[slot.day][timeKey]) {
          mat[slot.day][timeKey].push(entry);
        }
      }
    });

    return mat;
  }, [entries, timeSlots, sortedSlots]);

  const getCellData = (entry: TimetableEntryResult) => {
    const assignment = assignments.find(a => a.id === entry.course_assignment_id);
    const course = courses.find(c => c.id === assignment?.course_id);
    const faculty = facultyList.find(f => f.id === assignment?.faculty_id);
    const room = rooms.find(r => r.id === entry.room_id);

    return {
      courseName: course?.course_code || `Course ${assignment?.course_id}`,
      facultyName: faculty ? `Faculty ${faculty.id}` : `Faculty ${assignment?.faculty_id}`,
      roomName: room?.room_number || `Room ${entry.room_id}`,
      hourType: entry.hour_type,
    };
  };

  const formatTime = (timeString: string) => {
    // timeString is like '09:00:00'
    return timeString.substring(0, 5);
  };

  return (
    <div className="mt-8 overflow-x-auto border border-gray-200 rounded-lg shadow-sm">
      <div className="min-w-[800px]">
        {/* Header Row */}
        <div className="flex bg-gray-50 border-b border-gray-200">
          <div className="w-24 flex-shrink-0 border-r border-gray-200 p-3 font-semibold text-gray-500 text-center text-sm flex items-center justify-center">
            Time
          </div>
          {DAYS.map(day => (
            <div key={day} className="flex-1 p-3 font-semibold text-gray-700 text-center border-r last:border-r-0 border-gray-200">
              {day}
            </div>
          ))}
        </div>

        {/* Time Rows */}
        {sortedSlots.map(slot => {
          const timeKey = `${slot.start_time}-${slot.end_time}`;
          return (
            <div key={timeKey} className="flex border-b last:border-b-0 border-gray-200">
              {/* Time Column */}
              <div className="w-24 flex-shrink-0 bg-gray-50 border-r border-gray-200 p-2 text-xs font-medium text-gray-500 flex flex-col items-center justify-center">
                <span>{formatTime(slot.start_time)}</span>
                <span className="text-gray-400">-</span>
                <span>{formatTime(slot.end_time)}</span>
              </div>
              
              {/* Days Columns */}
              {DAYS.map(day => {
                const cellEntries = matrix[day]?.[timeKey] || [];
                return (
                  <div key={`${day}-${timeKey}`} className="flex-1 p-2 border-r last:border-r-0 border-gray-200 min-h-[100px] flex flex-col gap-2">
                    {cellEntries.map((entry, idx) => {
                      const data = getCellData(entry);
                      return (
                        <TimetableCell
                          key={`${entry.course_assignment_id}-${idx}`}
                          courseName={data.courseName}
                          facultyName={data.facultyName}
                          roomName={data.roomName}
                          hourType={data.hourType}
                        />
                      );
                    })}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
};
