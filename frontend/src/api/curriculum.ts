/**
 * frontend/src/api/curriculum.ts
 * --------------------------------
 * Centralized API client for:
 * 1. Super Admin Academic Governance (Regulations, Cohorts, Versions, Mappings)
 * 2. AI Syllabus PDF Extraction Studio & Review
 * 3. Super Admin & Admin Correction Request Ticketing & Threads
 * 4. Admin Department Inbox & Acknowledgements
 * 5. Admin Section Offerings, Faculty Teaching Allocation & Readiness Check
 * 6. Student & Faculty Scoped Curriculum Inspection
 */

import { apiClient } from './client';

// ---------------------------------------------------------------------------
// TypeScript Interfaces
// ---------------------------------------------------------------------------

export interface Regulation {
  id: number;
  code: string;
  name: string;
  department_id?: number | null;
  department_name?: string | null;
  effective_year: number;
  is_active: boolean;
  description?: string | null;
  cohorts_count: number;
  curriculum_versions_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdmissionCohort {
  id: number;
  cohort_name: string;
  start_year: number;
  end_year: number;
  program_id: number;
  program_name?: string | null;
  regulation_id: number;
  regulation_code?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CurriculumSubjectMapping {
  id: number;
  curriculum_version_id: number;
  curriculum_semester_id: number;
  semester_number?: number | null;
  course_id?: number | null;
  subject_code: string;
  subject_name: string;
  subject_type: string;
  is_mandatory: boolean;
  elective_group_name?: string | null;
  credits: number;
  lecture_hours: number;
  tutorial_hours: number;
  practical_hours: number;
  contact_hours: number;
  practical_consecutive_periods: number;
  requires_lab: boolean;
  course_description?: string | null;
  prerequisites?: string | null;
  co_requisites?: string | null;
  source_page?: number | null;
  source_text?: string | null;
  verification_status: string;
  created_at: string;
  updated_at: string;
}

export interface CurriculumSemester {
  id: number;
  curriculum_version_id: number;
  semester_number: number;
  total_credits: number;
  total_contact_hours: number;
  notes?: string | null;
  subject_mappings: CurriculumSubjectMapping[];
}

export interface CurriculumVersion {
  id: number;
  version_code: string;
  department_id: number;
  department_name?: string | null;
  program_id: number;
  program_name?: string | null;
  regulation_id: number;
  regulation_code?: string | null;
  cohort_id?: number | null;
  cohort_name?: string | null;
  version_number: number;
  status: 'DRAFT' | 'NEEDS_REVIEW' | 'VALIDATED' | 'APPROVED' | 'PUBLISHED' | 'SUPERSEDED' | 'ARCHIVED';
  description?: string | null;
  total_credits: number;
  total_semesters: number;
  source_document_id?: number | null;
  source_document_title?: string | null;
  created_by_name?: string | null;
  reviewed_by_name?: string | null;
  approved_by_name?: string | null;
  published_by_name?: string | null;
  published_at?: string | null;
  semesters: CurriculumSemester[];
  created_at: string;
  updated_at: string;
}

export interface CurriculumVersionSummary {
  id: number;
  version_code: string;
  department_name: string;
  program_name: string;
  regulation_code: string;
  cohort_name?: string | null;
  version_number: number;
  status: string;
  total_credits: number;
  total_semesters: number;
  published_at?: string | null;
  created_at: string;
}

export interface ExtractedSubjectItem {
  semester: number;
  code: string;
  name: string;
  type: string;
  credits: number;
  lecture: number;
  tutorial: number;
  practical: number;
  contact_hours: number;
  requires_lab: boolean;
  is_mandatory: boolean;
  elective_group?: string | null;
  source_page?: number | null;
  source_text?: string | null;
  confidence_score: number;
}

export interface CurriculumExtractionJob {
  id: number;
  document_id: number;
  document_title?: string | null;
  target_curriculum_version_id?: number | null;
  status: 'QUEUED' | 'PROCESSING' | 'AWAITING_REVIEW' | 'APPROVED' | 'REJECTED' | 'FAILED';
  total_pages: number;
  extracted_semesters_count: number;
  extracted_subjects_count: number;
  extracted_data?: ExtractedSubjectItem[] | null;
  error_message?: string | null;
  created_by_id: number;
  creator_name?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CurriculumRelease {
  id: number;
  curriculum_version_id: number;
  version_code?: string | null;
  program_name?: string | null;
  regulation_code?: string | null;
  department_id: number;
  department_name?: string | null;
  released_at: string;
  released_by_name?: string | null;
  is_acknowledged: boolean;
  acknowledged_by_name?: string | null;
  acknowledged_at?: string | null;
  acknowledgement_notes?: string | null;
}

export interface CurriculumRequestMessage {
  id: number;
  request_id: number;
  sender_id: number;
  sender_name: string;
  sender_role: string;
  message: string;
  attachments_json?: string | null;
  created_at: string;
}

export interface CurriculumRequest {
  id: number;
  request_number: string;
  requesting_admin_id: number;
  requesting_admin_name?: string | null;
  department_id: number;
  department_name?: string | null;
  program_id?: number | null;
  program_name?: string | null;
  curriculum_version_id?: number | null;
  curriculum_version_code?: string | null;
  curriculum_semester_id?: number | null;
  subject_mapping_id?: number | null;
  request_type: string;
  title: string;
  description: string;
  proposed_change_json?: string | null;
  status: 'OPEN' | 'UNDER_REVIEW' | 'NEEDS_INFORMATION' | 'RESOLVED' | 'REJECTED' | 'WITHDRAWN';
  resolution_notes?: string | null;
  resolved_by_name?: string | null;
  resolved_at?: string | null;
  created_at: string;
  updated_at: string;
  messages: CurriculumRequestMessage[];
}

export interface FacultyCourseOffering {
  id: number;
  section_course_offering_id: number;
  faculty_id: number;
  faculty_name?: string | null;
  faculty_code?: string | null;
  assigned_role: string;
  assigned_hours: number;
  is_active: boolean;
  created_at: string;
}

export interface SectionCourseOffering {
  id: number;
  curriculum_version_id: number;
  curriculum_subject_mapping_id: number;
  subject_code?: string | null;
  subject_name?: string | null;
  subject_type?: string | null;
  academic_year_id: number;
  academic_year_name?: string | null;
  semester_id: number;
  semester_number?: number | null;
  section_id: number;
  section_name?: string | null;
  batch_id?: number | null;
  batch_name?: string | null;
  enrolled_student_count: number;
  is_active: boolean;
  faculty_allocations: FacultyCourseOffering[];
  created_at: string;
}

export interface SubjectReadinessItem {
  subject_code: string;
  subject_name: string;
  subject_type: string;
  credits: number;
  contact_hours: number;
  requires_lab: boolean;
  sections_covered: number;
  sections_total: number;
  is_fully_allocated: boolean;
  allocated_faculty_names: string[];
  missing_items: string[];
}

export interface CurriculumReadiness {
  curriculum_version_id: number;
  version_code: string;
  department_id: number;
  department_name: string;
  semester_number: number;
  is_ready_for_scheduling: boolean;
  readiness_percentage: number;
  total_subjects: number;
  allocated_subjects: number;
  unallocated_subjects: number;
  missing_faculty_count: number;
  subjects: SubjectReadinessItem[];
  blocking_reasons: string[];
}

export interface SuperAdminDashboardStats {
  total_regulations: number;
  total_cohorts: number;
  total_curriculum_versions: number;
  draft_versions_count: number;
  needs_review_count: number;
  approved_versions_count: number;
  published_versions_count: number;
  open_requests_count: number;
  documents_count: number;
  extraction_jobs_count: number;
  active_releases_count: number;
  recent_activities: Array<{
    id: number;
    action: string;
    entity_type: string;
    entity_id?: number | null;
    user_name: string;
    timestamp: string;
    details?: any;
  }>;
}

// ---------------------------------------------------------------------------
// 1. Super Admin API Methods
// ---------------------------------------------------------------------------

export async function getSuperAdminDashboardStats(): Promise<SuperAdminDashboardStats> {
  const { data } = await apiClient.get<SuperAdminDashboardStats>('/super-admin/dashboard/stats');
  return data;
}

export async function getRegulations(departmentId?: number): Promise<Regulation[]> {
  const params = departmentId ? { department_id: departmentId } : {};
  const { data } = await apiClient.get<Regulation[]>('/super-admin/regulations', { params });
  return data;
}

export async function createRegulation(payload: Partial<Regulation>): Promise<Regulation> {
  const { data } = await apiClient.post<Regulation>('/super-admin/regulations', payload);
  return data;
}

export async function updateRegulation(id: number, payload: Partial<Regulation>): Promise<Regulation> {
  const { data } = await apiClient.put<Regulation>(`/super-admin/regulations/${id}`, payload);
  return data;
}

export async function getCohorts(programId?: number): Promise<AdmissionCohort[]> {
  const params = programId ? { program_id: programId } : {};
  const { data } = await apiClient.get<AdmissionCohort[]>('/super-admin/cohorts', { params });
  return data;
}

export async function createCohort(payload: Partial<AdmissionCohort>): Promise<AdmissionCohort> {
  const { data } = await apiClient.post<AdmissionCohort>('/super-admin/cohorts', payload);
  return data;
}

export async function getCurriculumVersions(params?: { department_id?: number; status?: string }): Promise<CurriculumVersionSummary[]> {
  const { data } = await apiClient.get<CurriculumVersionSummary[]>('/super-admin/curriculum-versions', { params });
  return data;
}

export async function getCurriculumVersion(id: number): Promise<CurriculumVersion> {
  const { data } = await apiClient.get<CurriculumVersion>(`/super-admin/curriculum-versions/${id}`);
  return data;
}

export async function createCurriculumVersion(payload: {
  department_id: number;
  program_id: number;
  regulation_id: number;
  cohort_id?: number | null;
  description?: string;
  total_semesters?: number;
}): Promise<CurriculumVersion> {
  const { data } = await apiClient.post<CurriculumVersion>('/super-admin/curriculum-versions', payload);
  return data;
}

export async function updateCurriculumVersionStatus(id: number, status: string, reviewNotes?: string): Promise<CurriculumVersion> {
  const { data } = await apiClient.post<CurriculumVersion>(`/super-admin/curriculum-versions/${id}/status`, {
    status,
    review_notes: reviewNotes,
  });
  return data;
}

export async function publishCurriculumVersion(id: number, departmentIds?: number[]): Promise<CurriculumVersion> {
  const payload = departmentIds ? { department_ids: departmentIds } : {};
  const { data } = await apiClient.post<CurriculumVersion>(`/super-admin/curriculum-versions/${id}/publish`, payload);
  return data;
}

export async function reviseCurriculumVersion(id: number): Promise<CurriculumVersion> {
  const { data } = await apiClient.post<CurriculumVersion>(`/super-admin/curriculum-versions/${id}/revise`);
  return data;
}

export async function addSubjectMapping(versionId: number, payload: Partial<CurriculumSubjectMapping>): Promise<CurriculumSubjectMapping> {
  const { data } = await apiClient.post<CurriculumSubjectMapping>(`/super-admin/curriculum-versions/${versionId}/subjects`, payload);
  return data;
}

export async function updateSubjectMapping(mappingId: number, payload: Partial<CurriculumSubjectMapping>): Promise<CurriculumSubjectMapping> {
  const { data } = await apiClient.put<CurriculumSubjectMapping>(`/super-admin/subjects/${mappingId}`, payload);
  return data;
}

export async function deleteSubjectMapping(mappingId: number): Promise<void> {
  await apiClient.delete(`/super-admin/subjects/${mappingId}`);
}

export async function uploadCurriculumPDF(formData: FormData): Promise<{ id: number; title: string; file_name: string }> {
  const { data } = await apiClient.post<{ id: number; title: string; file_name: string }>('/super-admin/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function triggerExtractionJob(documentId: number, targetVersionId?: number): Promise<CurriculumExtractionJob> {
  const params = targetVersionId ? { target_version_id: targetVersionId } : {};
  const { data } = await apiClient.post<CurriculumExtractionJob>(`/super-admin/documents/${documentId}/extract`, null, { params });
  return data;
}

export async function getExtractionJob(jobId: number): Promise<CurriculumExtractionJob> {
  const { data } = await apiClient.get<CurriculumExtractionJob>(`/super-admin/extraction-jobs/${jobId}`);
  return data;
}

export async function reviewExtractionJob(jobId: number, payload: {
  action: 'APPROVE' | 'REJECT';
  feedback?: string;
  target_version_id?: number | null;
  edited_data?: ExtractedSubjectItem[];
}): Promise<CurriculumExtractionJob> {
  const { data } = await apiClient.post<CurriculumExtractionJob>(`/super-admin/extraction-jobs/${jobId}/review`, payload);
  return data;
}

export async function getSuperAdminRequests(status?: string): Promise<CurriculumRequest[]> {
  const params = status ? { status } : {};
  const { data } = await apiClient.get<CurriculumRequest[]>('/super-admin/requests', { params });
  return data;
}

export async function getSuperAdminRequest(id: number): Promise<CurriculumRequest> {
  const { data } = await apiClient.get<CurriculumRequest>(`/super-admin/requests/${id}`);
  return data;
}

export async function updateSuperAdminRequestStatus(id: number, payload: {
  status: string;
  resolution_notes?: string;
  resulting_curriculum_version_id?: number | null;
}): Promise<CurriculumRequest> {
  const { data } = await apiClient.put<CurriculumRequest>(`/super-admin/requests/${id}/status`, payload);
  return data;
}

export async function addSuperAdminRequestMessage(id: number, message: string): Promise<CurriculumRequestMessage> {
  const { data } = await apiClient.post<CurriculumRequestMessage>(`/super-admin/requests/${id}/messages`, { message });
  return data;
}

// ---------------------------------------------------------------------------
// 2. Admin Curriculum Allocation API Methods
// ---------------------------------------------------------------------------

export async function getAdminCurriculumInbox(): Promise<CurriculumRelease[]> {
  const { data } = await apiClient.get<CurriculumRelease[]>('/admin/curriculum/inbox');
  return data;
}

export async function acknowledgeCurriculumRelease(releaseId: number, notes?: string): Promise<CurriculumRelease> {
  const { data } = await apiClient.post<CurriculumRelease>(`/admin/curriculum/inbox/${releaseId}/acknowledge`, {
    acknowledgement_notes: notes,
  });
  return data;
}

export async function getSectionOfferings(params: {
  academic_year_id: number;
  semester_id: number;
  section_id?: number;
}): Promise<SectionCourseOffering[]> {
  const { data } = await apiClient.get<SectionCourseOffering[]>('/admin/curriculum/offerings', { params });
  return data;
}

export async function createSectionOffering(payload: Partial<SectionCourseOffering>): Promise<SectionCourseOffering> {
  const { data } = await apiClient.post<SectionCourseOffering>('/admin/curriculum/offerings', payload);
  return data;
}

export async function allocateFacultyOffering(payload: {
  section_course_offering_id: number;
  faculty_id: number;
  assigned_role?: string;
  assigned_hours?: number;
}): Promise<FacultyCourseOffering> {
  const { data } = await apiClient.post<FacultyCourseOffering>('/admin/curriculum/faculty-allocations', payload);
  return data;
}

export async function getCurriculumReadiness(params: {
  curriculum_version_id: number;
  semester_number: number;
  academic_year_id: number;
  semester_id: number;
}): Promise<CurriculumReadiness> {
  const { data } = await apiClient.get<CurriculumReadiness>('/admin/curriculum/readiness', { params });
  return data;
}

export async function getAdminCurriculumRequests(status?: string): Promise<CurriculumRequest[]> {
  const params = status ? { status } : {};
  const { data } = await apiClient.get<CurriculumRequest[]>('/admin/curriculum/requests', { params });
  return data;
}

export async function createAdminCurriculumRequest(payload: {
  department_id: number;
  request_type: string;
  title: string;
  description: string;
  curriculum_version_id?: number | null;
  curriculum_semester_id?: number | null;
  subject_mapping_id?: number | null;
  proposed_change_json?: string | null;
}): Promise<CurriculumRequest> {
  const { data } = await apiClient.post<CurriculumRequest>('/admin/curriculum/requests', payload);
  return data;
}

export async function addAdminRequestMessage(requestId: number, message: string): Promise<CurriculumRequestMessage> {
  const { data } = await apiClient.post<CurriculumRequestMessage>(`/admin/curriculum/requests/${requestId}/messages`, { message });
  return data;
}

// ---------------------------------------------------------------------------
// 3. Student & Faculty Scoped APIs
// ---------------------------------------------------------------------------

export async function getStudentCurrentCurriculum(): Promise<{
  student_name: string;
  student_id?: string;
  current_semester: number;
  curriculum?: CurriculumVersion | null;
}> {
  const { data } = await apiClient.get('/curriculum/student/current');
  return data;
}

export async function getFacultyAssignedCurriculum(): Promise<{
  faculty_name: string;
  faculty_code?: string;
  department_id?: number;
  assigned_offerings_count: number;
  assigned_items?: Array<{
    offering_id: number;
    subject_code?: string | null;
    subject_name?: string | null;
    assigned_role: string;
    assigned_hours: number;
  }>;
}> {
  const { data } = await apiClient.get('/curriculum/faculty/assigned');
  return data;
}
