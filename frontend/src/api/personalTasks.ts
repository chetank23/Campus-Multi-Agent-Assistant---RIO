import { apiClient } from './client';

export type TaskPriority = 'LOW' | 'MEDIUM' | 'HIGH';
export type TaskStatus = 'PENDING' | 'COMPLETED';
export type TaskSortBy = 'created_at' | 'due_at' | 'priority';

export interface PersonalTask {
  id: number;
  user_id: number;
  title: string;
  notes?: string | null;
  due_at?: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PersonalTaskCreate {
  title: string;
  notes?: string;
  due_at?: string | null;
  priority: TaskPriority;
}

export interface PersonalTaskUpdate {
  title?: string;
  notes?: string;
  due_at?: string | null;
  clear_due_at?: boolean;
  priority?: TaskPriority;
  status?: TaskStatus;
}

export const personalTasksApi = {
  list: async (params?: {
    status?: TaskStatus;
    priority?: TaskPriority;
    q?: string;
    sort_by?: TaskSortBy;
  }): Promise<PersonalTask[]> => {
    const res = await apiClient.get<PersonalTask[]>('/my-tasks', { params });
    return res.data;
  },
  create: async (payload: PersonalTaskCreate): Promise<PersonalTask> => {
    const res = await apiClient.post<PersonalTask>('/my-tasks', payload);
    return res.data;
  },
  update: async (id: number, payload: PersonalTaskUpdate): Promise<PersonalTask> => {
    const res = await apiClient.put<PersonalTask>(`/my-tasks/${id}`, payload);
    return res.data;
  },
  toggle: async (id: number): Promise<PersonalTask> => {
    const res = await apiClient.patch<PersonalTask>(`/my-tasks/${id}/toggle`);
    return res.data;
  },
  remove: async (id: number): Promise<void> => {
    await apiClient.delete(`/my-tasks/${id}`);
  },
};
