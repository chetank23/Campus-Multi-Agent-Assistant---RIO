import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { formatTime12h } from './timeFormatter';
import type { TimetableVersionDetailResponse } from '@/api/timetable';

export interface PDFData {
  versionDetail: TimetableVersionDetailResponse;
  departmentName?: string;
  programName?: string;
  academicYearName?: string;
  semesterNumber?: number | string;
  sectionName?: string;
  classTeacherName?: string;
  classTeacherDesignation?: string;
  classTeacherContact?: string;
}

export const exportTimetableToPDF = (data: PDFData) => {
  const {
    versionDetail,
    departmentName = versionDetail.department_name || 'Department of Computer Science',
    programName = versionDetail.program_name || 'B.Tech',
    academicYearName = versionDetail.academic_year_name || '2025-2026',
    semesterNumber = versionDetail.semester_number || 'Sem III',
    sectionName = versionDetail.section_name || 'Section A',
    classTeacherName = versionDetail.class_teacher_name || 'Not Assigned',
    classTeacherDesignation = versionDetail.class_teacher_designation || '—',
    classTeacherContact = versionDetail.class_teacher_contact || '—',
  } = data;

  const doc = new jsPDF({
    orientation: 'landscape',
    unit: 'mm',
    format: 'a4',
  });

  // Title Banner
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(16);
  doc.setTextColor(30, 41, 59); // Slate 800
  doc.text('RIO-MJP ACADEMIC TIMETABLE', 14, 15);

  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(71, 85, 105); // Slate 600
  doc.text(`${departmentName} | ${programName} - Semester ${semesterNumber} (${sectionName})`, 14, 21);
  doc.text(`Academic Year: ${academicYearName} | Class Teacher: ${classTeacherName} (${classTeacherDesignation} | Contact: ${classTeacherContact})`, 14, 26);

  // Group entries by Day & Time
  const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const dayAbbrMap: Record<string, string> = {
    MON: 'Monday',
    TUE: 'Tuesday',
    WED: 'Wednesday',
    THU: 'Thursday',
    FRI: 'Friday',
    SAT: 'Saturday',
    Monday: 'Monday',
    Tuesday: 'Tuesday',
    Wednesday: 'Wednesday',
    Thursday: 'Thursday',
    Friday: 'Friday',
    Saturday: 'Saturday',
  };

  // Find all unique slots
  const slotMap = new Map<string, { start: string; end: string; type: string }>();
  versionDetail.timetable_entries.forEach((e) => {
    if (e.start_time && e.end_time) {
      const key = `${e.start_time}-${e.end_time}`;
      if (!slotMap.has(key)) {
        slotMap.set(key, { start: e.start_time, end: e.end_time, type: e.slot_type || 'CLASS' });
      }
    }
  });

  const sortedSlotKeys = Array.from(slotMap.keys()).sort((a, b) => a.localeCompare(b));

  // Build Table Headers
  const headCols = ['Day', ...sortedSlotKeys.map((k) => {
    const s = slotMap.get(k);
    return `${formatTime12h(s?.start)} - ${formatTime12h(s?.end)}`;
  })];

  // Build Matrix Rows
  const bodyRows: string[][] = [];
  const entries = versionDetail.timetable_entries;

  DAYS.forEach((dayName) => {
    const row = [dayName];
    sortedSlotKeys.forEach((slotKey) => {
      const slotObj = slotMap.get(slotKey);
      if (slotObj?.type === 'LUNCH') {
        row.push('LUNCH BREAK');
        return;
      }
      if (slotObj?.type === 'BREAK') {
        row.push('TEA BREAK');
        return;
      }

      const matchingEntries = entries.filter((e) => {
        const dName = e.day ? (dayAbbrMap[e.day] || e.day) : '';
        const key = `${e.start_time}-${e.end_time}`;
        return dName === dayName && key === slotKey;
      });

      if (matchingEntries.length === 0) {
        row.push('—');
      } else {
        const textParts = matchingEntries.map((e) => {
          const code = e.course_code || 'Course';
          const room = e.room_number ? ` (${e.room_number})` : '';
          const fac = e.faculty_name ? `\n${e.faculty_name}` : '';
          return `${code}${room}${fac}`;
        });
        row.push(textParts.join('\n---\n'));
      }
    });
    bodyRows.push(row);
  });

  // Draw Grid Table
  autoTable(doc, {
    startY: 32,
    head: [headCols],
    body: bodyRows,
    theme: 'grid',
    headStyles: {
      fillColor: [241, 245, 249],
      textColor: [30, 41, 59],
      fontStyle: 'bold',
      fontSize: 8,
      halign: 'center',
    },
    styles: {
      fontSize: 7.5,
      cellPadding: 2,
      halign: 'center',
      valign: 'middle',
      textColor: [51, 65, 85],
    },
    alternateRowStyles: {
      fillColor: [250, 250, 250],
    },
  });

  // Add Faculty/Course Reference Table
  const nextY = (doc as any).lastAutoTable ? (doc as any).lastAutoTable.finalY + 8 : 120;

  doc.setFontSize(11);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(30, 41, 59);
  doc.text('Course & Faculty Reference Details', 14, nextY);

  // Collect unique courses with faculty
  const courseMap = new Map<string, { code: string; name: string; faculty: string; designation: string; contact: string }>();

  entries.forEach((e) => {
    if (e.course_code || e.course_name) {
      const key = `${e.course_code}-${e.faculty_name}`;
      if (!courseMap.has(key)) {
        courseMap.set(key, {
          code: e.course_code || '—',
          name: e.course_name || '—',
          faculty: e.faculty_name || '—',
          designation: e.faculty_designation || '—',
          contact: e.faculty_contact || '—',
        });
      }
    }
  });

  const refRows = Array.from(courseMap.values()).map((c) => [
    c.code,
    c.name,
    c.faculty,
    c.designation,
    c.contact,
  ]);

  autoTable(doc, {
    startY: nextY + 3,
    head: [['Course Code', 'Course Title', 'Faculty Name', 'Designation', 'Contact No.']],
    body: refRows.length > 0 ? refRows : [['—', '—', '—', '—', '—']],
    theme: 'plain',
    headStyles: {
      fillColor: [226, 232, 240],
      textColor: [15, 23, 42],
      fontStyle: 'bold',
      fontSize: 8,
    },
    styles: {
      fontSize: 7.5,
      cellPadding: 2,
    },
  });

  // Save PDF
  const filename = `RIO-MJP_Timetable_${sectionName.replace(/\s+/g, '_')}_${semesterNumber}.pdf`;
  doc.save(filename);
};
