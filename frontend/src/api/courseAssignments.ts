import { apiClient } from './client';

export interface CourseAssignmentResponse {
  id: number;
  course_id: number;
  faculty_id: number;
  section_id?: number;
  batch_id?: number;
}

export const getCourseAssignments = async (): Promise<CourseAssignmentResponse[]> => {
  const response = await apiClient.get('/course-assignments/');
  return response.data;
};
