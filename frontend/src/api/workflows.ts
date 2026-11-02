import { apiClient } from './client';

export type ChangeRequestStatus = 'PENDING' | 'APPROVED' | 'REJECTED';
export interface ChangeRequestItem {
  id: number;
  requested_by: number | null;
  request_type: string | null;
  related_entity_id: number | null;
  reason: string | null;
  status: ChangeRequestStatus;
  reviewed_by: number | null;
  created_at: string;
  review_note?: string | null;
}
export interface ChangeRequestPage {
  items: ChangeRequestItem[];
  total: number;
  skip: number;
  limit: number;
}
export async function getPendingChangeRequests(skip = 0, limit = 50) {
  const { data } = await apiClient.get<ChangeRequestItem[]>('/change-requests/pending', { params: { skip, limit } });
  return data;
}
export async function reviewChangeRequest(id: number, status: 'APPROVED' | 'REJECTED', review_note?: string) {
  const { data } = await apiClient.patch<ChangeRequestItem>(`/change-requests/${id}/review`, { status, review_note });
  return data;
}
export interface AuditLogItem {
  id: number;
  user_id: number | null;
  action: string | null;
  entity_type: string | null;
  entity_id: number | null;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  timestamp: string;
}
export interface AuditLogResponse { items: AuditLogItem[]; total: number; skip: number; limit: number; }
export async function getAuditLogs(params: { user_id?: number; action?: string; entity_type?: string; skip?: number; limit?: number } = {}) {
  const { data } = await apiClient.get<AuditLogResponse>('/admin/audit-logs', { params });
  return data;
}
