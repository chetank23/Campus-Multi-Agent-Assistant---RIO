import { apiClient } from './client';

export interface AcademicYearResponse {
  id: number;
  year_name: string;
  start_date: string;
  end_date: string;
  is_active: boolean;
}

export interface AcademicYearCreate {
  year_name: string;
  start_date: string;
  end_date: string;
  is_active: boolean;
}

export interface AcademicYearUpdate {
  year_name?: string;
  start_date?: string;
  end_date?: string;
  is_active?: boolean;
}

export const academicYearsApi = {
  getAll: async () => {
    const { data } = await apiClient.get<AcademicYearResponse[]>('/academic-years/');
    return data;
  },

  getById: async (id: number) => {
    const { data } = await apiClient.get<AcademicYearResponse>(`/academic-years/${id}`);
    return data;
  },

  create: async (year: AcademicYearCreate) => {
    const { data } = await apiClient.post<AcademicYearResponse>('/academic-years/', year);
    return data;
  },

  update: async (id: number, year: AcademicYearUpdate) => {
    const { data } = await apiClient.put<AcademicYearResponse>(`/academic-years/${id}`, year);
    return data;
  },

  delete: async (id: number) => {
    const { data } = await apiClient.delete(`/academic-years/${id}`);
    return data;
  },
};
