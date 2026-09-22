import { apiClient } from './client';

export interface GenerationScope {
  academic_year_id: number;
  semester_id: number;
  department_id: number;
  program_id: number;
  section_ids?: number[];
  building_ids?: number[];
  room_ids?: number[];
  lab_ids?: number[];
  time_slot_ids?: number[];
}

export interface TimetableEntryResult {
  course_assignment_id: number;
  room_id: number;
  slot_id: number;
  hour_type: string;
}

export interface TimetableScore {
  total_score: number;
  hard_violations: number;
  soft_violations: number;
  room_utilization_pct: number;
  faculty_workload_balance: number;
  student_gap_minutes_avg: number;
  faculty_gap_quality: number;
  student_gap_quality: number;
  preferred_slot_quality: number;
  room_change_quality: number;
  late_lab_quality: number;
  workload_balance_quality: number;
}

export interface GenerationSummary {
  status: string;
  message: string;
  loaded_sections: number;
  loaded_courses: number;
  loaded_faculty: number;
  loaded_rooms: number;
  loaded_time_slots: number;
  solve_time_seconds?: number;
  generated_entries?: TimetableEntryResult[];
  diagnostics?: string[];
  score?: TimetableScore;
}

export const generateTimetable = async (scope: GenerationScope): Promise<GenerationSummary> => {
  // We use a custom timeout because timetable generation can take up to 60 seconds (solver time limit).
  const response = await apiClient.post('/timetable/generate', scope, { timeout: 70000 });
  return response.data;
};
