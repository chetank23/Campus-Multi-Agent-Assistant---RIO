import { apiClient } from './client';

export interface BatchResponse {
  id: number;
  section_id: number;
  batch_name: string;
  student_count: number;
}

export interface BatchCreate {
  section_id: number;
  batch_name: string;
  student_count: number;
}

export interface BatchUpdate {
  section_id?: number;
  batch_name?: string;
  student_count?: number;
}

export const batchesApi = {
  getAll: async () => {
    const { data } = await apiClient.get<BatchResponse[]>('/batches/');
    return data;
  },

  getById: async (id: number) => {
    const { data } = await apiClient.get<BatchResponse>(`/batches/${id}`);
    return data;
  },

  create: async (batch: BatchCreate) => {
    const { data } = await apiClient.post<BatchResponse>('/batches/', batch);
    return data;
  },

  update: async (id: number, batch: BatchUpdate) => {
    const { data } = await apiClient.put<BatchResponse>(`/batches/${id}`, batch);
    return data;
  },

  delete: async (id: number) => {
    const { data } = await apiClient.delete(`/batches/${id}`);
    return data;
  },
};
