import { apiClient } from './client';
import type { DepartmentResponse } from './departments';

export interface ProgramResponse {
  id: number;
  department_id: number;
  program_name: string;
  degree: string;
  duration: number;
  department?: DepartmentResponse; // Usually expanded or fetched separately
}

export interface ProgramCreate {
  department_id: number;
  program_name: string;
  degree: string;
  duration: number;
}

export interface ProgramUpdate {
  department_id?: number;
  program_name?: string;
  degree?: string;
  duration?: number;
}

export const programsApi = {
  getAll: async () => {
    const { data } = await apiClient.get<ProgramResponse[]>('/programs/');
    return data;
  },

  getById: async (id: number) => {
    const { data } = await apiClient.get<ProgramResponse>(`/programs/${id}`);
    return data;
  },

  create: async (program: ProgramCreate) => {
    const { data } = await apiClient.post<ProgramResponse>('/programs/', program);
    return data;
  },

  update: async (id: number, program: ProgramUpdate) => {
    const { data } = await apiClient.put<ProgramResponse>(`/programs/${id}`, program);
    return data;
  },

  delete: async (id: number) => {
    const { data } = await apiClient.delete(`/programs/${id}`);
    return data;
  },
};
