import { apiClient } from './client';

export interface FacultyResponse {
  id: number;
  user_id: number;
  department_id: number;
  designation: string;
  max_hours_per_week: number;
  is_active: boolean;
}

export interface FacultyCreate {
  user_id: number;
  department_id: number;
  designation: string;
  max_hours_per_week: number;
  is_active: boolean;
}

export interface FacultyUpdate {
  user_id?: number;
  department_id?: number;
  designation?: string;
  max_hours_per_week?: number;
  is_active?: boolean;
}

export const facultyApi = {
  getAll: async () => {
    const { data } = await apiClient.get<FacultyResponse[]>('/faculty/');
    return data;
  },

  getById: async (id: number) => {
    const { data } = await apiClient.get<FacultyResponse>(`/faculty/${id}`);
    return data;
  },

  create: async (faculty: FacultyCreate) => {
    const { data } = await apiClient.post<FacultyResponse>('/faculty/', faculty);
    return data;
  },

  update: async (id: number, faculty: FacultyUpdate) => {
    const { data } = await apiClient.put<FacultyResponse>(`/faculty/${id}`, faculty);
    return data;
  },

  delete: async (id: number) => {
    const { data } = await apiClient.delete(`/faculty/${id}`);
    return data;
  },
};
