import { apiClient } from './client';

export interface SectionResponse {
  id: number;
  department_id: number;
  program_id: number;
  semester_id: number;
  section_name: string;
  student_count: number;
}

export interface SectionCreate {
  department_id: number;
  program_id: number;
  semester_id: number;
  section_name: string;
  student_count: number;
}

export interface SectionUpdate {
  department_id?: number;
  program_id?: number;
  semester_id?: number;
  section_name?: string;
  student_count?: number;
}

export const sectionsApi = {
  getAll: async () => {
    const { data } = await apiClient.get<SectionResponse[]>('/sections/');
    return data;
  },

  getById: async (id: number) => {
    const { data } = await apiClient.get<SectionResponse>(`/sections/${id}`);
    return data;
  },

  create: async (section: SectionCreate) => {
    const { data } = await apiClient.post<SectionResponse>('/sections/', section);
    return data;
  },

  update: async (id: number, section: SectionUpdate) => {
    const { data } = await apiClient.put<SectionResponse>(`/sections/${id}`, section);
    return data;
  },

  delete: async (id: number) => {
    const { data } = await apiClient.delete(`/sections/${id}`);
    return data;
  },
};
