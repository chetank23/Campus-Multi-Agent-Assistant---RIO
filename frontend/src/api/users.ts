import { apiClient } from './client';

export interface UserAdminItem {
  id: number;
  name: string;
  email: string;
  role: 'ADMIN' | 'FACULTY' | 'STUDENT';
  department_id?: number | null;
  department_name?: string | null;
  is_active: boolean;
  created_at?: string;
}

export interface UserListResponse {
  items: UserAdminItem[];
  total: number;
  skip: number;
  limit: number;
}

export interface UserAdminCreate {
  name: string;
  email: string;
  password: string;
  role: 'ADMIN' | 'FACULTY' | 'STUDENT';
  department_id?: number | null;
}

export interface UserAdminUpdate {
  name?: string;
  role?: 'ADMIN' | 'FACULTY' | 'STUDENT';
  department_id?: number | null;
  is_active?: boolean;
}

export const usersApi = {
  getAll: async (): Promise<UserAdminItem[]> => {
    const { data } = await apiClient.get<UserListResponse>('/users', { params: { limit: 1000 } });
    return data.items;
  },

  list: async (params?: {
    skip?: number;
    limit?: number;
    role?: string;
    department_id?: number;
    search?: string;
    is_active?: boolean;
  }): Promise<UserListResponse> => {
    const { data } = await apiClient.get<UserListResponse>('/users', { params });
    return data;
  },

  getById: async (id: number): Promise<UserAdminItem> => {
    const { data } = await apiClient.get<UserAdminItem>(`/users/${id}`);
    return data;
  },

  create: async (user: UserAdminCreate): Promise<UserAdminItem> => {
    const { data } = await apiClient.post<UserAdminItem>('/users', user);
    return data;
  },

  update: async (id: number, updates: UserAdminUpdate): Promise<UserAdminItem> => {
    const { data } = await apiClient.patch<UserAdminItem>(`/users/${id}`, updates);
    return data;
  },

  resetPassword: async (id: number, newPassword: string): Promise<{ message: string }> => {
    const { data } = await apiClient.post<{ message: string }>(`/users/${id}/reset-password`, {
      new_password: newPassword,
    });
    return data;
  },
};
