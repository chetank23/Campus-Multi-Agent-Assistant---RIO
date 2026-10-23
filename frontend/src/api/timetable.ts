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

export interface TimetableEntryUpdate {
  room_id?: number | null;
  slot_id?: number | null;
  faculty_id?: number | null;
}

export interface TimetableEntryResponse {
  id: number;
  version_id: number | null;
  department_id: number | null;
  program_id: number | null;
  semester_id: number | null;
  section_id: number | null;
  batch_id: number | null;
  course_id: number | null;
  faculty_id: number | null;
  room_id: number | null;
  slot_id: number | null;
  status: string;
}

export interface TimetableVersionResponse {
  id: number;
  academic_year_id: number | null;
  version_number: string | null;
  status: string | null;
  created_by: number | null;
  approved_by: number | null;
  created_at: string;
  published_at: string | null;
  reason: string | null;
}

export interface TimetableEntryDetailResponse extends TimetableEntryResponse {
  course_code?: string | null;
  course_name?: string | null;
  course_type?: string | null;
  faculty_name?: string | null;
  faculty_designation?: string | null;
  faculty_contact?: string | null;
  room_number?: string | null;
  building_name?: string | null;
  day?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  slot_type?: string | null;
  section_name?: string | null;
}

export interface TimetableVersionDetailResponse extends TimetableVersionResponse {
  department_name?: string | null;
  program_name?: string | null;
  academic_year_name?: string | null;
  semester_number?: number | null;
  section_name?: string | null;
  class_teacher_name?: string | null;
  class_teacher_designation?: string | null;
  class_teacher_contact?: string | null;
  timetable_entries: TimetableEntryDetailResponse[];
}


export interface ValidationViolation {
  severity: string;
  message: string;
  code?: string | null;
  entry_ids?: number[];
  entity_type?: string | null;
  entity_id?: number | null;
  entity_name?: string | null;
  suggestion?: string | null;
}

export interface ValidationResult {
  is_valid: boolean;
  violations: ValidationViolation[];
  blocker_count?: number;
  warning_count?: number;
  info_count?: number;
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

export const getTimetableVersions = async (academicYearId?: number): Promise<TimetableVersionResponse[]> => {
  const params = academicYearId ? { academic_year_id: academicYearId } : {};
  const response = await apiClient.get('/timetable/versions', { params });
  return response.data;
};

export const getTimetableVersion = async (versionId: number): Promise<TimetableVersionDetailResponse> => {
  const response = await apiClient.get(`/timetable/versions/${versionId}`);
  return response.data;
};

export const validateTimetableVersion = async (versionId: number): Promise<ValidationResult> => {
  const response = await apiClient.post(`/timetable/versions/${versionId}/validate`);
  return response.data;
};

export const updateTimetableEntry = async (entryId: number, updates: TimetableEntryUpdate): Promise<TimetableEntryResponse> => {
  const response = await apiClient.patch(`/timetable/entries/${entryId}`, updates);
  return response.data;
};

export const finalizeTimetableVersion = async (versionId: number): Promise<{ message: string; version_id: number; status: string }> => {
  const response = await apiClient.post(`/timetable/versions/${versionId}/finalize`);
  return response.data;
};

export const publishTimetableVersion = async (versionId: number): Promise<{ message: string; version_id: number; status: string }> => {
  const response = await apiClient.post(`/timetable/versions/${versionId}/publish`);
  return response.data;
};

export interface PersonalTimetableEntry {
  id: number;
  version_id?: number | null;
  version_number?: string | null;
  academic_year_name?: string | null;
  semester_number?: number | null;
  department_name?: string | null;
  program_name?: string | null;
  section_name?: string | null;
  batch_name?: string | null;
  course_code?: string | null;
  course_name?: string | null;
  course_type?: string | null;
  faculty_name?: string | null;
  faculty_designation?: string | null;
  room_number?: string | null;
  building_name?: string | null;
  day?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  slot_type?: string | null;
  status: string;
}

export interface FacultyTimetableResponse {
  faculty_id?: number | null;
  faculty_code?: string | null;
  faculty_name?: string | null;
  designation?: string | null;
  department_name?: string | null;
  total_teaching_hours: number;
  entries: PersonalTimetableEntry[];
}

export interface StudentTimetableResponse {
  student_id?: number | null;
  student_code?: string | null;
  student_name?: string | null;
  department_name?: string | null;
  program_name?: string | null;
  semester_number?: number | null;
  section_name?: string | null;
  batch_name?: string | null;
  total_class_hours: number;
  entries: PersonalTimetableEntry[];
}

export const getFacultyMyTimetable = async (academicYearId?: number): Promise<FacultyTimetableResponse> => {
  const params = academicYearId ? { academic_year_id: academicYearId } : {};
  const response = await apiClient.get('/faculty/my-timetable', { params });
  return response.data;
};

export const getStudentMyTimetable = async (academicYearId?: number): Promise<StudentTimetableResponse> => {
  const params = academicYearId ? { academic_year_id: academicYearId } : {};
  const response = await apiClient.get('/student/my-timetable', { params });
  return response.data;
};
