import { apiClient } from './client';

export interface DepartmentResponse {
  id: number;
  department_code: string;
  name: string;
}

export interface DepartmentCreate {
  department_code: string;
  name: string;
}

export interface DepartmentUpdate {
  department_code?: string;
  name?: string;
}

export const departmentsApi = {
  getAll: async () => {
    const { data } = await apiClient.get<DepartmentResponse[]>('/departments/');
    return data;
  },

  getById: async (id: number) => {
    const { data } = await apiClient.get<DepartmentResponse>(`/departments/${id}`);
    return data;
  },

  create: async (department: DepartmentCreate) => {
    const { data } = await apiClient.post<DepartmentResponse>('/departments/', department);
    return data;
  },

  update: async (id: number, department: DepartmentUpdate) => {
    const { data } = await apiClient.put<DepartmentResponse>(`/departments/${id}`, department);
    return data;
  },

  delete: async (id: number) => {
    const { data } = await apiClient.delete(`/departments/${id}`);
    return data;
  },
};
