import { apiClient } from './client';

export type SearchEntityType =
  | 'student'
  | 'faculty'
  | 'department'
  | 'program'
  | 'course'
  | 'room'
  | 'lab';

export interface GlobalSearchResultItem {
  id: number;
  entity_type: SearchEntityType;
  title: string;
  subtitle: string;
  route: string;
}

export interface GlobalSearchResponse {
  query: string;
  total: number;
  results: GlobalSearchResultItem[];
}

export const searchApi = {
  search: async (q: string, limit = 20, signal?: AbortSignal): Promise<GlobalSearchResponse> => {
    const res = await apiClient.get<GlobalSearchResponse>('/search', {
      params: { q, limit },
      signal,
    });
    return res.data;
  },
};
