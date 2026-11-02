import { apiClient } from './client';

export interface FacultyAvailabilityItem {
  id: number;
  faculty_id: number;
  slot_id: number;
  availability: string;
  preference: number;
}

export interface FacultyAvailabilityCreate {
  faculty_id: number;
  slot_id: number;
  availability: 'AVAILABLE' | 'UNAVAILABLE' | 'PREFERRED';
  preference?: number;
}

export const facultyAvailabilityApi = {
  getAll: async (): Promise<FacultyAvailabilityItem[]> => {
    const { data } = await apiClient.get<FacultyAvailabilityItem[]>('/faculty-availability/');
    return data;
  },

  create: async (payload: FacultyAvailabilityCreate): Promise<FacultyAvailabilityItem> => {
    const { data } = await apiClient.post<FacultyAvailabilityItem>('/faculty-availability/', payload);
    return data;
  },

  update: async (
    id: number,
    payload: { availability?: string; preference?: number }
  ): Promise<FacultyAvailabilityItem> => {
    const { data } = await apiClient.put<FacultyAvailabilityItem>(`/faculty-availability/${id}`, payload);
    return data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/faculty-availability/${id}`);
  },
};

