import { apiClient } from './client';

export interface SemesterResponse {
  id: number;
  academic_year_id: number;
  term: string;
  semester_number: number;
  start_date: string;
  end_date: string;
  is_active: boolean;
}

export interface SemesterCreate {
  academic_year_id: number;
  term: string;
  semester_number: number;
  start_date: string;
  end_date: string;
  is_active: boolean;
}

export interface SemesterUpdate {
  academic_year_id?: number;
  term?: string;
  semester_number?: number;
  start_date?: string;
  end_date?: string;
  is_active?: boolean;
}

export const semestersApi = {
  getAll: async () => {
    const { data } = await apiClient.get<SemesterResponse[]>('/semesters/');
    return data;
  },

  getById: async (id: number) => {
    const { data } = await apiClient.get<SemesterResponse>(`/semesters/${id}`);
    return data;
  },

  create: async (semester: SemesterCreate) => {
    const { data } = await apiClient.post<SemesterResponse>('/semesters/', semester);
    return data;
  },

  update: async (id: number, semester: SemesterUpdate) => {
    const { data } = await apiClient.put<SemesterResponse>(`/semesters/${id}`, semester);
    return data;
  },

  delete: async (id: number) => {
    const { data } = await apiClient.delete(`/semesters/${id}`);
    return data;
  },
};
