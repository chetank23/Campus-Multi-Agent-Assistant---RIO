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
    // Respect backend maximum pagination limit of 200 by paging through in bounded chunks
    const pageSize = 200;
    const firstPage = await usersApi.list({ skip: 0, limit: pageSize });
    let allItems = [...firstPage.items];
    const total = firstPage.total;
    let currentSkip = pageSize;
    while (allItems.length < total && firstPage.items.length === pageSize) {
      const nextPage = await usersApi.list({ skip: currentSkip, limit: pageSize });
      if (!nextPage.items || !nextPage.items.length) break;
      allItems = allItems.concat(nextPage.items);
      currentSkip += pageSize;
    }
    return allItems;
  },

  list: async (params?: {
    skip?: number;
    limit?: number;
    role?: string;
    department_id?: number;
    search?: string;
    is_active?: boolean;
  }): Promise<UserListResponse> => {
    const boundedParams = {
      ...params,
      limit: Math.min(Math.max(params?.limit ?? 50, 1), 200),
      skip: Math.max(params?.skip ?? 0, 0),
    };
    const { data } = await apiClient.get<UserListResponse>('/users', { params: boundedParams });
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
