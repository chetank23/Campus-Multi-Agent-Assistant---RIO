/**
 * frontend/src/api/substitutions.ts
 * ---------------------------------
 * API client functions and TypeScript interfaces for Faculty Substitution.
 */

import { apiClient } from './client';

export interface ClassOccurrence {
  timetable_entry_id: number;
  date: string;
  day: string;
  start_time?: string | null;
  end_time?: string | null;
  course_id?: number | null;
  course_code?: string | null;
  course_name?: string | null;
  room_number?: string | null;
  building_name?: string | null;
  section_id?: number | null;
  section_name?: string | null;
  batch_id?: number | null;
  batch_name?: string | null;
  department_id?: number | null;
  department_name?: string | null;
  has_active_request: boolean;
  active_substitution_id?: number | null;
  active_substitution_status?: string | null;
  substitute_faculty_id?: number | null;
  substitute_faculty_name?: string | null;
}

export interface SubstitutionRequest {
  id: number;
  timetable_entry_id: number;
  substitution_date: string;
  original_faculty_id: number;
  original_faculty_name: string;
  substitute_faculty_id?: number | null;
  substitute_faculty_name?: string | null;
  course_code?: string | null;
  course_name?: string | null;
  room_number?: string | null;
  building_name?: string | null;
  slot_day?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  section_name?: string | null;
  batch_name?: string | null;
  department_name?: string | null;
  status: 'REQUESTED' | 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'CANCELLED' | string;
  reason?: string | null;
  rejection_reason?: string | null;
  created_by_id: number;
  reviewed_by_id?: number | null;
  reviewed_by_name?: string | null;
  reviewed_at?: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface CandidateEligibilityReason {
  factor: string;
  status: 'PASS' | 'FAIL' | 'UNKNOWN';
  detail: string;
}

export interface SubstituteCandidate {
  faculty_id: number;
  faculty_code?: string | null;
  faculty_name: string;
  department_id?: number | null;
  department_name?: string | null;
  designation?: string | null;
  qualification_tier: 'DIRECT_ASSIGNMENT' | 'DEPARTMENT_MATCH' | 'GENERAL' | string;
  current_weekly_load: number;
  max_weekly_load: number;
  load_percentage: number;
  score: number;
  is_eligible: boolean;
  ineligibility_reasons: string[];
  eligibility_breakdown: CandidateEligibilityReason[];
}

export interface CandidateRecommendationResponse {
  substitution_id: number;
  timetable_entry_id: number;
  substitution_date: string;
  course_code?: string | null;
  course_name?: string | null;
  slot_day?: string | null;
  slot_time?: string | null;
  original_faculty_id: number;
  original_faculty_name: string;
  evaluation_status?: 'ELIGIBLE' | 'NO_ELIGIBLE_CANDIDATE' | 'CANNOT_DETERMINE' | string;
  cannot_determine: boolean;
  cannot_determine_reason?: string | null;
  candidates: SubstituteCandidate[];
}

export interface StudentDateClassView {
  timetable_entry_id: number;
  date: string;
  course_code?: string | null;
  course_name?: string | null;
  room_number?: string | null;
  building_name?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  is_substituted: boolean;
  faculty_name: string;
  original_faculty_name?: string | null;
  slot_type?: string | null;
  status: string;
}

export const substitutionsApi = {
  getMyScheduledClasses: (daysAhead: number = 14) =>
    apiClient.get<ClassOccurrence[]>(`/substitutions/my-classes?days_ahead=${daysAhead}`),

  createSubstitutionRequest: (payload: {
    timetable_entry_id: number;
    substitution_date: string;
    reason: string;
  }) => apiClient.post<SubstitutionRequest>('/substitutions/requests', payload),

  getMySubstitutionRequests: () =>
    apiClient.get<SubstitutionRequest[]>('/substitutions/my-requests'),

  getMySubstitutionAssignments: () =>
    apiClient.get<SubstitutionRequest[]>('/substitutions/my-assignments'),

  getPendingSubstitutionsQueue: () =>
    apiClient.get<SubstitutionRequest[]>('/substitutions/pending'),

  getCandidateRecommendations: (id: number) =>
    apiClient.get<CandidateRecommendationResponse>(`/substitutions/requests/${id}/candidates`),

  reviewSubstitutionRequest: (
    id: number,
    payload: {
      action: 'APPROVE' | 'REJECT';
      substitute_faculty_id?: number | null;
      rejection_reason?: string | null;
      version: number;
    }
  ) => apiClient.post<SubstitutionRequest>(`/substitutions/requests/${id}/review`, payload),

  cancelSubstitutionRequest: (id: number) =>
    apiClient.post<SubstitutionRequest>(`/substitutions/requests/${id}/cancel`),

  getClassesForDate: (date: string, sectionId?: number) => {
    const query = sectionId ? `?date=${date}&section_id=${sectionId}` : `?date=${date}`;
    return apiClient.get<StudentDateClassView[]>(`/substitutions/date-view${query}`);
  },
};

