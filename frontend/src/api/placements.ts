/**
 * frontend/src/api/placements.ts
 * ------------------------------
 * API client functions and TypeScript interfaces for CDC Placement Management.
 */

import { apiClient } from './client';

export interface PlacementScheduleItem {
  id?: number;
  round_type: string;
  round_order: number;
  title: string;
  start_time: string;
  end_time: string;
  venue_name?: string | null;
  room_id?: number | null;
  room_number?: string | null;
  building_name?: string | null;
  is_online: boolean;
  meeting_link?: string | null;
  instructions?: string | null;
}

export interface StudentEligibilityResult {
  status: 'ELIGIBLE' | 'NOT_ELIGIBLE' | 'CANNOT_DETERMINE';
  is_eligible: boolean;
  reasons: string[];
  criteria_breakdown?: Record<string, any>;
}

export interface PlacementDriveItem {
  id: number;
  company_name: string;
  company_description?: string | null;
  company_website?: string | null;
  company_logo_url?: string | null;

  title: string;
  job_role: string;
  job_description?: string | null;
  job_type: 'FULL_TIME' | 'INTERNSHIP' | 'INTERN_PLUS_FULL_TIME' | string;
  work_location?: string | null;
  compensation_details?: string | null;
  tier?: string | null;

  eligible_department_ids?: number[] | null;
  eligible_department_names?: string[];
  eligible_program_ids?: number[] | null;
  eligible_program_names?: string[];
  eligible_batch_ids?: number[] | null;
  graduation_year?: number | null;
  min_cgpa?: number | null;
  grading_scale: number;
  min_percentage?: number | null;
  max_active_backlogs?: number | null;
  max_total_backlogs?: number | null;
  allowed_genders: string;
  additional_criteria?: string | null;

  application_deadline: string;
  is_deadline_passed: boolean;
  application_link?: string | null;
  application_instructions?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  required_documents?: string | null;

  status: 'DRAFT' | 'PUBLISHED' | 'CLOSED' | 'POSTPONED' | 'CANCELLED' | 'ARCHIVED' | string;
  postpone_reason?: string | null;
  cancellation_reason?: string | null;
  published_at?: string | null;
  closed_at?: string | null;

  coordinator_id: number;
  coordinator_name: string;
  coordinator_email: string;
  version: number;
  created_at: string;
  updated_at: string;

  schedules: PlacementScheduleItem[];
  eligibility?: StudentEligibilityResult | null;
}

export interface PlacementDriveCreatePayload {
  company_name: string;
  company_description?: string;
  company_website?: string;
  company_logo_url?: string;
  title: string;
  job_role: string;
  job_description?: string;
  job_type?: 'FULL_TIME' | 'INTERNSHIP' | 'INTERN_PLUS_FULL_TIME';
  work_location?: string;
  compensation_details?: string;
  tier?: string;
  eligible_department_ids?: number[];
  eligible_program_ids?: number[];
  eligible_batch_ids?: number[];
  graduation_year?: number;
  min_cgpa?: number;
  grading_scale?: number;
  min_percentage?: number;
  max_active_backlogs?: number;
  max_total_backlogs?: number;
  allowed_genders?: 'ALL' | 'MALE_ONLY' | 'FEMALE_ONLY';
  additional_criteria?: string;
  application_deadline: string;
  application_link?: string;
  application_instructions?: string;
  contact_email?: string;
  contact_phone?: string;
  required_documents?: string;
  schedules?: PlacementScheduleItem[];
}

export interface PlacementDriveUpdatePayload extends Partial<PlacementDriveCreatePayload> {
  version?: number;
}

export interface PlacementValidationResponse {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  eligible_students_count: number;
  likely_duplicates: string[];
}

export interface CdcDashboardStatsResponse {
  total_drives: number;
  published_drives: number;
  draft_drives: number;
  closed_drives: number;
  postponed_drives: number;
  cancelled_drives: number;
  upcoming_deadlines_count: number;
  recent_drives: PlacementDriveItem[];
}

export interface StudentAcademicRecordItem {
  id: number;
  student_id: number;
  student_name: string;
  student_usn: string;
  department_name?: string | null;
  program_name?: string | null;
  cgpa?: number | null;
  grading_scale: number;
  percentage?: number | null;
  active_backlogs?: number | null;
  total_backlogs?: number | null;
  graduation_year?: number | null;
  tenth_percentage?: number | null;
  twelfth_percentage?: number | null;
  is_verified: boolean;
  verified_by_name?: string | null;
  updated_at: string;
}

export const placementsApi = {
  // Drives Listing & Detail
  listDrives: async (params?: {
    status?: string;
    job_type?: string;
    tier?: string;
    search?: string;
    only_eligible?: boolean;
  }) => {
    const res = await apiClient.get<PlacementDriveItem[]>('/placements/drives', { params });
    return res.data;
  },

  getDriveDetail: async (id: number) => {
    const res = await apiClient.get<PlacementDriveItem>(`/placements/drives/${id}`);
    return res.data;
  },

  // Management Operations
  createDrive: async (payload: PlacementDriveCreatePayload, directPublish: boolean = false) => {
    const res = await apiClient.post<PlacementDriveItem>('/placements/drives', payload, {
      params: { direct_publish: directPublish },
    });
    return res.data;
  },

  updateDrive: async (id: number, payload: PlacementDriveUpdatePayload) => {
    const res = await apiClient.put<PlacementDriveItem>(`/placements/drives/${id}`, payload);
    return res.data;
  },

  validateDrive: async (payload: PlacementDriveCreatePayload, excludeId?: number) => {
    const res = await apiClient.post<PlacementValidationResponse>('/placements/drives/validate', payload, {
      params: { exclude_id: excludeId },
    });
    return res.data;
  },

  publishDrive: async (id: number) => {
    const res = await apiClient.post<PlacementDriveItem>(`/placements/drives/${id}/publish`);
    return res.data;
  },

  postponeDrive: async (id: number, reason: string) => {
    const res = await apiClient.post<PlacementDriveItem>(`/placements/drives/${id}/postpone`, { reason });
    return res.data;
  },

  cancelDrive: async (id: number, reason: string) => {
    const res = await apiClient.post<PlacementDriveItem>(`/placements/drives/${id}/cancel`, { reason });
    return res.data;
  },

  closeDrive: async (id: number) => {
    const res = await apiClient.post<PlacementDriveItem>(`/placements/drives/${id}/close`);
    return res.data;
  },

  // Student Explicit Eligibility
  checkEligibility: async (id: number) => {
    const res = await apiClient.get<StudentEligibilityResult>(`/placements/drives/${id}/eligibility`);
    return res.data;
  },

  // Dashboard Stats
  getDashboardStats: async () => {
    const res = await apiClient.get<CdcDashboardStatsResponse>('/placements/dashboard');
    return res.data;
  },

  // Academic Records Management
  upsertAcademicRecord: async (payload: {
    student_id: number;
    cgpa?: number;
    grading_scale?: number;
    percentage?: number;
    active_backlogs?: number;
    total_backlogs?: number;
    graduation_year?: number;
    tenth_percentage?: number;
    twelfth_percentage?: number;
    is_verified?: boolean;
  }) => {
    const res = await apiClient.post<StudentAcademicRecordItem>('/placements/academic-records', payload);
    return res.data;
  },

  getAcademicRecord: async (studentId: number) => {
    const res = await apiClient.get<StudentAcademicRecordItem>(`/placements/academic-records/${studentId}`);
    return res.data;
  },
};

