/**
 * frontend/src/api/settings.ts
 * ----------------------------
 * API client and types for Admin Settings and Safe Operational Data Management.
 */

import { apiClient } from './client';

export interface InstitutionProfile {
  institution_name: string;
  campus_name: string;
  department: string;
  timezone: string;
  academic_year: string;
  current_semester: string;
}

export interface NotificationPreferences {
  email_alerts_enabled: boolean;
  timetable_publish_alerts: boolean;
  substitution_alerts: boolean;
  resource_booking_alerts: boolean;
}

export interface GeneralSettingsResponse {
  institution: InstitutionProfile;
  notifications: NotificationPreferences;
  updated_at?: string | null;
}

export interface GeneralSettingsUpdate {
  institution?: Partial<InstitutionProfile>;
  notifications?: Partial<NotificationPreferences>;
}

export interface BreakPeriod {
  name: string;
  start: string;
  end: string;
}

export interface TimetableSettingsResponse {
  working_days: 'MON_SAT' | 'MON_FRI';
  periods_per_day: number;
  period_duration_minutes: number;
  break_times: BreakPeriod[];
  max_consecutive_faculty_lectures: number;
  enable_soft_lab_preference: boolean;
  updated_at?: string | null;
}

export interface TimetableSettingsUpdate {
  working_days?: 'MON_SAT' | 'MON_FRI';
  max_consecutive_faculty_lectures?: number;
  enable_soft_lab_preference?: boolean;
}

export interface UserAccessSummary {
  total_users: number;
  super_admin_count: number;
  admin_count: number;
  faculty_count: number;
  student_count: number;
  access_token_expiry_minutes: number;
  refresh_token_expiry_days: number;
  mfa_enforced: boolean;
}

export interface SystemIntegrationStatus {
  database_status: string;
  database_host: string;
  database_name: string;
  database_schema: string;
  database_port: number;
  ai_agent_status: string;
  llm_provider: string;
  llm_configured: boolean;
  supabase_configured: boolean;
  server_time: string;
  uptime_status: string;
}

export interface FullSettingsResponse {
  general: GeneralSettingsResponse;
  timetable: TimetableSettingsResponse;
  access: UserAccessSummary;
  system: SystemIntegrationStatus;
}

export interface TableRecordCount {
  table_name: string;
  display_name: string;
  count: number;
  description: string;
}

export interface DataCategorySummary {
  category_id: string;
  category_name: string;
  description: string;
  total_records: number;
  can_clear: boolean;
  warning?: string | null;
  tables: TableRecordCount[];
}

export interface DataManagementSummaryResponse {
  categories: DataCategorySummary[];
  total_generated_records: number;
  master_records_protected: boolean;
  authoritative_dataset: string;
}

export interface AffectedTableDetail {
  table_name: string;
  display_name: string;
  record_count: number;
  foreign_key_dependencies: string[];
}

export interface DataClearPreviewResponse {
  categories_selected: string[];
  clear_all: boolean;
  affected_tables: AffectedTableDetail[];
  total_records_to_delete: number;
  warnings: string[];
  master_records_protected: boolean;
  safe_to_execute: boolean;
}

export interface DataClearExecuteResponse {
  success: boolean;
  categories_cleared: string[];
  total_records_deleted: number;
  deleted_per_table: Record<string, number>;
  audit_log_id: number;
  message: string;
}

export const settingsApi = {
  getFullSettings: async (): Promise<FullSettingsResponse> => {
    const { data } = await apiClient.get<FullSettingsResponse>('/admin/settings');
    return data;
  },

  updateGeneralSettings: async (payload: GeneralSettingsUpdate): Promise<GeneralSettingsResponse> => {
    const { data } = await apiClient.patch<GeneralSettingsResponse>('/admin/settings/general', payload);
    return data;
  },

  updateTimetableSettings: async (payload: TimetableSettingsUpdate): Promise<TimetableSettingsResponse> => {
    const { data } = await apiClient.patch<TimetableSettingsResponse>('/admin/settings/timetable', payload);
    return data;
  },

  getSystemStatus: async (): Promise<SystemIntegrationStatus> => {
    const { data } = await apiClient.get<SystemIntegrationStatus>('/admin/system/status');
    return data;
  },

  getDataManagementSummary: async (): Promise<DataManagementSummaryResponse> => {
    const { data } = await apiClient.get<DataManagementSummaryResponse>('/admin/data-management/summary');
    return data;
  },

  previewDataClear: async (categories: string[], clear_all: boolean = false): Promise<DataClearPreviewResponse> => {
    const { data } = await apiClient.post<DataClearPreviewResponse>('/admin/data-management/preview', {
      categories,
      clear_all,
    });
    return data;
  },

  executeDataClear: async (
    categories: string[],
    clear_all: boolean = false,
    confirmation: boolean = true
  ): Promise<DataClearExecuteResponse> => {
    const { data } = await apiClient.post<DataClearExecuteResponse>('/admin/data-management/clear', {
      categories,
      clear_all,
      confirmation,
    });
    return data;
  },
};
