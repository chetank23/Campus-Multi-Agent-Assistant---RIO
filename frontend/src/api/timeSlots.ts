import { apiClient } from './client';

export interface TimeSlotResponse {
  id: number;
  day: string;
  start_time: string;
  end_time: string;
  slot_type: string;
}

export const getTimeSlots = async (): Promise<TimeSlotResponse[]> => {
  const response = await apiClient.get('/time-slots');
  return response.data;
};
