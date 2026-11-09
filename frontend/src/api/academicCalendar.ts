import { apiClient } from './client';

export interface AcademicCalendarItem {
  id: number;
  academic_year_id: number;
  date: string;
  event_type: string;
  description?: string | null;
}

export interface AcademicCalendarCreate {
  academic_year_id: number;
  date: string;
  event_type: string;
  description?: string;
}

export interface TimeSlotItem {
  id: number;
  day: string;
  start_time: string;
  end_time: string;
  slot_type: string;
}

export interface TimeSlotCreate {
  day: string;
  start_time: string;
  end_time: string;
  slot_type: string;
}

export const academicCalendarApi = {
  getAll: async (): Promise<AcademicCalendarItem[]> => {
    const { data } = await apiClient.get<AcademicCalendarItem[]>('/academic-calendar');
    return data;
  },

  create: async (item: AcademicCalendarCreate): Promise<AcademicCalendarItem> => {
    const { data } = await apiClient.post<AcademicCalendarItem>('/academic-calendar', item);
    return data;
  },

  update: async (id: number, item: Partial<AcademicCalendarCreate>): Promise<AcademicCalendarItem> => {
    const { data } = await apiClient.put<AcademicCalendarItem>(`/academic-calendar/${id}`, item);
    return data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/academic-calendar/${id}`);
  },
};

export const timeSlotsApi = {
  getAll: async (): Promise<TimeSlotItem[]> => {
    const { data } = await apiClient.get<TimeSlotItem[]>('/time-slots');
    return data;
  },

  create: async (item: TimeSlotCreate): Promise<TimeSlotItem> => {
    const { data } = await apiClient.post<TimeSlotItem>('/time-slots', item);
    return data;
  },

  update: async (id: number, item: Partial<TimeSlotCreate>): Promise<TimeSlotItem> => {
    const { data } = await apiClient.put<TimeSlotItem>(`/time-slots/${id}`, item);
    return data;
  },

  delete: async (id: number): Promise<void> => {
    await apiClient.delete(`/time-slots/${id}`);
  },
};

