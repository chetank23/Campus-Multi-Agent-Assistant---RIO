import { apiClient } from './client';

export type ImportEntityType = 'rooms' | 'courses' | 'faculty' | 'students';

export interface RowError {
  row_index: number;
  field: string;
  message: string;
}

export interface ImportPreviewResponse {
  entity_type: ImportEntityType;
  total_rows: number;
  valid_rows_count: number;
  invalid_rows_count: number;
  errors: RowError[];
  preview_data: Record<string, any>[];
}

export interface ImportCommitResponse {
  success: boolean;
  entity_type: ImportEntityType;
  imported_count: number;
  message: string;
}

export const dataImportApi = {
  preview: async (entityType: ImportEntityType, rows: Record<string, any>[]): Promise<ImportPreviewResponse> => {
    const { data } = await apiClient.post<ImportPreviewResponse>('/admin/import/preview', {
      entity_type: entityType,
      rows,
    });
    return data;
  },

  commit: async (entityType: ImportEntityType, rows: Record<string, any>[]): Promise<ImportCommitResponse> => {
    const { data } = await apiClient.post<ImportCommitResponse>('/admin/import/commit', {
      entity_type: entityType,
      rows,
    });
    return data;
  },
};
