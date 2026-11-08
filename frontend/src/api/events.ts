/**
 * api/events.ts
 * -------------
 * API client methods and types for Campus Events, Clubs, Activities, and Coordinator Capabilities.
 */

import { apiClient } from './client';

export type EventCategory =
  | 'ACADEMIC'
  | 'CULTURAL'
  | 'SPORTS'
  | 'WORKSHOP'
  | 'SEMINAR'
  | 'HACKATHON'
  | 'CLUB_ACTIVITY'
  | 'GENERAL';

export type EventStatus =
  | 'DRAFT'
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'PUBLISHED'
  | 'ONGOING'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'REJECTED'
  | 'ARCHIVED';

export type TargetAudience =
  | 'ALL'
  | 'STUDENT'
  | 'FACULTY'
  | 'DEPARTMENT_ONLY'
  | 'MEMBERS_ONLY';

export interface CampusEventItem {
  id: number;
  title: string;
  description?: string | null;
  category: EventCategory;
  club_id?: number | null;
  club_name?: string | null;
  start_time: string;
  end_time: string;
  room_id?: number | null;
  room_number?: string | null;
  building_id?: number | null;
  building_name?: string | null;
  venue_name?: string | null;
  target_audience: TargetAudience;
  target_department_id?: number | null;
  requires_approval: boolean;
  status: EventStatus;
  coordinator_id?: number | null;
  coordinator_name?: string | null;
  approved_by_id?: number | null;
  approved_by_name?: string | null;
  approved_at?: string | null;
  rejection_reason?: string | null;
  cancellation_reason?: string | null;
  published_at?: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface EventCreatePayload {
  title: string;
  description?: string;
  category: EventCategory;
  club_id?: number | null;
  start_time: string;
  end_time: string;
  room_id?: number | null;
  building_id?: number | null;
  venue_name?: string;
  target_audience?: TargetAudience;
  target_department_id?: number | null;
  target_batch_id?: number | null;
  requires_approval?: boolean;
}

export interface EventUpdatePayload {
  title?: string;
  description?: string;
  category?: EventCategory;
  start_time?: string;
  end_time?: string;
  room_id?: number | null;
  building_id?: number | null;
  venue_name?: string;
  target_audience?: TargetAudience;
  target_department_id?: number | null;
  target_batch_id?: number | null;
  requires_approval?: boolean;
}

export interface VenueConflictItem {
  type: 'TIMETABLE' | 'RESOURCE_BOOKING' | 'CAMPUS_EVENT';
  id?: number | null;
  reason: string;
  time_window: string;
}

export interface VenueCheckResponse {
  is_available: boolean;
  conflicts: VenueConflictItem[];
}

export interface ClubItem {
  id: number;
  name: string;
  code: string;
  category: string;
  description?: string | null;
  status: 'ACTIVE' | 'INACTIVE' | 'ARCHIVED';
  created_at: string;
  updated_at: string;
}

export interface CoordinatorCapabilityItem {
  id: number;
  user_id: number;
  user_name?: string;
  user_email?: string;
  user_role?: string;
  capability: string;
  scope_type: 'GLOBAL' | 'CLUB' | 'DEPARTMENT';
  scope_id?: number | null;
  scope_name?: string | null;
  assigned_by: number;
  assigned_at: string;
  expires_at?: string | null;
  is_active: boolean;
  revoked_at?: string | null;
  revocation_reason?: string | null;
}

export const eventsApi = {
  // Events
  listEvents: async (params?: {
    category?: string;
    time_filter?: string;
    search?: string;
    club_id?: number;
  }): Promise<CampusEventItem[]> => {
    const res = await apiClient.get<CampusEventItem[]>('/events', { params });
    return res.data;
  },

  getLiveEvents: async (): Promise<CampusEventItem[]> => {
    const res = await apiClient.get<any>('/events/live');
    if (Array.isArray(res.data)) return res.data;
    return res.data?.ongoing_events || [];
  },

  getEvent: async (id: number): Promise<CampusEventItem> => {
    const res = await apiClient.get<CampusEventItem>(`/events/${id}`);
    return res.data;
  },

  createEvent: async (payload: EventCreatePayload): Promise<CampusEventItem> => {
    const res = await apiClient.post<CampusEventItem>('/events', payload);
    return res.data;
  },

  updateEvent: async (id: number, payload: EventUpdatePayload): Promise<CampusEventItem> => {
    const res = await apiClient.put<CampusEventItem>(`/events/${id}`, payload);
    return res.data;
  },

  submitEvent: async (id: number): Promise<CampusEventItem> => {
    const res = await apiClient.post<CampusEventItem>(`/events/${id}/submit`);
    return res.data;
  },

  reviewEvent: async (
    id: number,
    payload: { action: 'APPROVE' | 'REJECT'; reason?: string; notes?: string }
  ): Promise<CampusEventItem> => {
    const res = await apiClient.post<CampusEventItem>(`/events/${id}/review`, payload);
    return res.data;
  },

  cancelEvent: async (id: number, payload?: { reason?: string }): Promise<CampusEventItem> => {
    const res = await apiClient.post<CampusEventItem>(`/events/${id}/cancel`, payload || {});
    return res.data;
  },

  checkVenueAvailability: async (payload: {
    room_id: number;
    start_time: string;
    end_time: string;
    exclude_event_id?: number;
  }): Promise<VenueCheckResponse> => {
    const res = await apiClient.post<VenueCheckResponse>('/events/venue-check', payload);
    return res.data;
  },

  // Clubs
  listClubs: async (status?: string): Promise<ClubItem[]> => {
    const res = await apiClient.get<ClubItem[]>('/clubs', {
      params: status ? { status } : undefined,
    });
    return res.data;
  },

  getClub: async (id: number): Promise<ClubItem> => {
    const res = await apiClient.get<ClubItem>(`/clubs/${id}`);
    return res.data;
  },

  listClubActivities: async (clubId: number): Promise<CampusEventItem[]> => {
    const res = await apiClient.get<CampusEventItem[]>(`/clubs/${clubId}/activities`);
    return res.data;
  },

  listFacultyMyClubs: async (): Promise<ClubItem[]> => {
    const res = await apiClient.get<ClubItem[]>('/faculty/my-clubs');
    return res.data;
  },

  createClub: async (payload: {
    name: string;
    code: string;
    category?: string;
    description?: string;
  }): Promise<ClubItem> => {
    const res = await apiClient.post<ClubItem>('/clubs', payload);
    return res.data;
  },

  updateClub: async (
    id: number,
    payload: {
      name?: string;
      code?: string;
      category?: string;
      description?: string;
      status?: string;
    }
  ): Promise<ClubItem> => {
    const res = await apiClient.put<ClubItem>(`/clubs/${id}`, payload);
    return res.data;
  },

  // Coordinator Capabilities (Admin)
  listCapabilities: async (params?: {
    user_id?: number;
    capability?: string;
    active_only?: boolean;
  }): Promise<CoordinatorCapabilityItem[]> => {
    const res = await apiClient.get<CoordinatorCapabilityItem[]>('/admin/capabilities', {
      params,
    });
    return res.data;
  },

  assignCapability: async (payload: {
    user_id: number;
    capability: string;
    scope_type: 'GLOBAL' | 'CLUB' | 'DEPARTMENT';
    scope_id?: number | null;
    expires_at?: string | null;
  }): Promise<CoordinatorCapabilityItem> => {
    const res = await apiClient.post<CoordinatorCapabilityItem>(
      '/admin/capabilities/assign',
      payload
    );
    return res.data;
  },

  revokeCapability: async (
    id: number,
    reason?: string
  ): Promise<CoordinatorCapabilityItem> => {
    const res = await apiClient.post<CoordinatorCapabilityItem>(
      `/admin/capabilities/${id}/revoke`,
      { reason }
    );
    return res.data;
  },
};

