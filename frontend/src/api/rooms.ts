import { apiClient } from './client';

export interface RoomResponse {
  id: number;
  building_id: number;
  room_number: string;
  room_type: string;
  capacity: number;
  is_active: boolean;
}

export interface RoomCreate {
  building_id: number;
  room_number: string;
  room_type: string;
  capacity: number;
  is_active: boolean;
}

export interface RoomUpdate {
  building_id?: number;
  room_number?: string;
  room_type?: string;
  capacity?: number;
  is_active?: boolean;
}

export const roomsApi = {
  getAll: async () => {
    const { data } = await apiClient.get<RoomResponse[]>('/rooms/');
    return data;
  },

  getById: async (id: number) => {
    const { data } = await apiClient.get<RoomResponse>(`/rooms/${id}`);
    return data;
  },

  create: async (room: RoomCreate) => {
    const { data } = await apiClient.post<RoomResponse>('/rooms/', room);
    return data;
  },

  update: async (id: number, room: RoomUpdate) => {
    const { data } = await apiClient.put<RoomResponse>(`/rooms/${id}`, room);
    return data;
  },

  delete: async (id: number) => {
    const { data } = await apiClient.delete(`/rooms/${id}`);
    return data;
  },
};
