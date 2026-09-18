import { apiClient } from './client';

export interface CourseResponse {
  id: number;
  course_code: string;
  course_name: string;
  department_id: number;
  course_type: string;
  credits: number;
  lecture_hours: number;
  tutorial_hours: number;
  practical_hours: number;
  requires_lab: boolean;
}

export interface CourseCreate {
  course_code: string;
  course_name: string;
  department_id: number;
  course_type: string;
  credits: number;
  lecture_hours: number;
  tutorial_hours: number;
  practical_hours: number;
  requires_lab?: boolean;
}

export interface CourseUpdate {
  course_code?: string;
  course_name?: string;
  department_id?: number;
  course_type?: string;
  credits?: number;
  lecture_hours?: number;
  tutorial_hours?: number;
  practical_hours?: number;
  requires_lab?: boolean;
}

export const coursesApi = {
  getAll: async () => {
    const { data } = await apiClient.get<CourseResponse[]>('/courses/');
    return data;
  },

  getById: async (id: number) => {
    const { data } = await apiClient.get<CourseResponse>(`/courses/${id}`);
    return data;
  },

  create: async (course: CourseCreate) => {
    const { data } = await apiClient.post<CourseResponse>('/courses/', course);
    return data;
  },

  update: async (id: number, course: CourseUpdate) => {
    const { data } = await apiClient.put<CourseResponse>(`/courses/${id}`, course);
    return data;
  },

  delete: async (id: number) => {
    const { data } = await apiClient.delete(`/courses/${id}`);
    return data;
  },
};
