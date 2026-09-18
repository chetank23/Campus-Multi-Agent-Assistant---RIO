import { apiClient } from './client';

export interface StudentResponse {
  id: number;
  user_id: number;
  student_id: string;
  department_id: number;
  program_id: number;
  semester_id: number;
  section_id: number;
  batch_id: number;
}

export interface StudentCreate {
  user_id: number;
  student_id: string;
  department_id: number;
  program_id: number;
  semester_id: number;
  section_id: number;
  batch_id: number;
}

export interface StudentUpdate {
  user_id?: number;
  student_id?: string;
  department_id?: number;
  program_id?: number;
  semester_id?: number;
  section_id?: number;
  batch_id?: number;
}

export const studentsApi = {
  getAll: async () => {
    const { data } = await apiClient.get<StudentResponse[]>('/students/');
    return data;
  },

  getById: async (id: number) => {
    const { data } = await apiClient.get<StudentResponse>(`/students/${id}`);
    return data;
  },

  create: async (student: StudentCreate) => {
    const { data } = await apiClient.post<StudentResponse>('/students/', student);
    return data;
  },

  update: async (id: number, student: StudentUpdate) => {
    const { data } = await apiClient.put<StudentResponse>(`/students/${id}`, student);
    return data;
  },

  delete: async (id: number) => {
    const { data } = await apiClient.delete(`/students/${id}`);
    return data;
  },
};
