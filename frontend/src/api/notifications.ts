/**
 * frontend/src/api/notifications.ts
 * ---------------------------------
 * API client methods for notification fetching, status updates, and broadcasts.
 */

import { apiClient } from './client';

export interface NotificationItem {
  id: number;
  user_id?: number | null;
  title: string;
  message: string;
  type?: string | null;
  link?: string | null;
  entity_type?: string | null;
  entity_id?: number | null;
  is_read: boolean;
  created_at: string;
}

export interface UnreadCountResponse {
  unread_count: number;
}

export interface BroadcastAnnouncementPayload {
  title: string;
  message: string;
  target_role?: 'ALL' | 'FACULTY' | 'STUDENT';
  department_id?: number | null;
  program_id?: number | null;
  section_id?: number | null;
}

export interface FacultyClassUpdatePayload {
  course_id: number;
  section_id: number;
  update_type: 'CANCELLATION' | 'RESCHEDULE' | 'ROOM_CHANGE' | 'ANNOUNCEMENT';
  title: string;
  message: string;
}

export async function getNotifications(
  unreadOnly = false,
  skip = 0,
  limit = 50,
): Promise<NotificationItem[]> {
  const response = await apiClient.get<NotificationItem[]>('/notifications', {
    params: { unread_only: unreadOnly, skip, limit },
  });
  return response.data;
}

export async function getUnreadCount(): Promise<number> {
  const response = await apiClient.get<UnreadCountResponse>('/notifications/unread-count');
  return response.data.unread_count;
}

export async function markNotificationAsRead(
  notificationId: number,
): Promise<{ id: number; is_read: boolean }> {
  const response = await apiClient.patch<{ id: number; is_read: boolean }>(
    `/notifications/${notificationId}/read`,
  );
  return response.data;
}

export async function markAllNotificationsAsRead(): Promise<{ marked_count: number }> {
  const response = await apiClient.post<{ marked_count: number }>('/notifications/mark-all-read');
  return response.data;
}

export async function broadcastAnnouncement(
  payload: BroadcastAnnouncementPayload,
): Promise<{ success: boolean; message: string; recipients_count: number }> {
  const response = await apiClient.post<{ success: boolean; message: string; recipients_count: number }>(
    '/notifications/admin/broadcast',
    payload,
  );
  return response.data;
}

export async function sendFacultyClassUpdate(
  payload: FacultyClassUpdatePayload,
): Promise<{ success: boolean; message: string; students_notified: number }> {
  const response = await apiClient.post<{ success: boolean; message: string; students_notified: number }>(
    '/notifications/faculty/class-update',
    payload,
  );
  return response.data;
}
