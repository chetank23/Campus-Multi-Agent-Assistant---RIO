import { apiClient } from './client';

export interface BuildingResponse {
  id: number;
  building_name: string;
  floors: number;
  name?: string;
  code?: string;
  number_of_floors?: number;
}

export interface BuildingCreate {
  building_name: string;
  floors: number;
}

export interface BuildingUpdate {
  building_name?: string;
  floors?: number;
}

export const buildingsApi = {
  getAll: async () => {
    const { data } = await apiClient.get<BuildingResponse[]>('/buildings/');
    return data;
  },

  getById: async (id: number) => {
    const { data } = await apiClient.get<BuildingResponse>(`/buildings/${id}`);
    return data;
  },

  create: async (building: BuildingCreate) => {
    const { data } = await apiClient.post<BuildingResponse>('/buildings/', building);
    return data;
  },

  update: async (id: number, building: BuildingUpdate) => {
    const { data } = await apiClient.put<BuildingResponse>(`/buildings/${id}`, building);
    return data;
  },

  delete: async (id: number) => {
    const { data } = await apiClient.delete(`/buildings/${id}`);
    return data;
  },
};
