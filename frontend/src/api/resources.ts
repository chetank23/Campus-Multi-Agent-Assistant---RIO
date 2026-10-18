/**
 * api/resources.ts
 * ----------------
 * API client methods and types for Campus Resource Allocation & Bookings.
 */

import { apiClient } from './client';

export type ResourceType = 'LAB' | 'SEMINAR_HALL' | 'PROJECTOR' | 'AUDITORIUM' | 'EQUIPMENT';
export type ResourceStatus = 'ACTIVE' | 'INACTIVE' | 'MAINTENANCE';
export type BookingStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';

export interface ResourceResponse {
  id: number;
  name: string;
  resource_type: ResourceType;
  location?: string | null;
  capacity?: number | null;
  status: ResourceStatus;
}

export interface ResourceCreate {
  name: string;
  resource_type: ResourceType;
  location?: string | null;
  capacity?: number | null;
  status?: ResourceStatus;
}

export interface ResourceUpdate {
  name?: string;
  resource_type?: ResourceType;
  location?: string | null;
  capacity?: number | null;
  status?: ResourceStatus;
}

export interface ResourceBookingResponse {
  id: number;
  resource_id: number;
  requested_by?: number | null;
  date: string;
  start_time: string;
  end_time: string;
  purpose?: string | null;
  status: BookingStatus;
  approved_by?: number | null;

  // Joined metadata
  resource_name?: string | null;
  resource_type?: string | null;
  resource_location?: string | null;
  requester_name?: string | null;
  requester_email?: string | null;
  approver_name?: string | null;
}

export interface ResourceBookingCreate {
  resource_id: number;
  date: string;
  start_time: string;
  end_time: string;
  purpose?: string | null;
}

export interface ConflictDetail {
  conflict_type: 'EXISTING_BOOKING' | 'PUBLISHED_TIMETABLE' | 'RESOURCE_INACTIVE';
  description: string;
  conflicting_id?: number | null;
  start_time?: string | null;
  end_time?: string | null;
}

export interface AlternativeResource {
  id: number;
  name: string;
  resource_type: string;
  location?: string | null;
  capacity?: number | null;
}

export interface AvailabilityResponse {
  resource_id: number;
  date: string;
  start_time: string;
  end_time: string;
  available: boolean;
  conflicts: ConflictDetail[];
  alternatives: AlternativeResource[];
}

export const resourcesApi = {
  // Inventory
  getAll: async (params?: { resource_type?: string; status?: string; search?: string }) => {
    const { data } = await apiClient.get<ResourceResponse[]>('/resources', { params });
    return data;
  },

  getById: async (id: number) => {
    const { data } = await apiClient.get<ResourceResponse>(`/resources/${id}`);
    return data;
  },

  create: async (resource: ResourceCreate) => {
    const { data } = await apiClient.post<ResourceResponse>('/resources', resource);
    return data;
  },

  update: async (id: number, resource: ResourceUpdate) => {
    const { data } = await apiClient.put<ResourceResponse>(`/resources/${id}`, resource);
    return data;
  },

  delete: async (id: number) => {
    const { data } = await apiClient.delete<{ action: string; message: string; resource_id: number }>(
      `/resources/${id}`
    );
    return data;
  },

  // Bookings
  getBookings: async (params?: {
    status?: string;
    resource_id?: number;
    from_date?: string;
    to_date?: string;
    my_only?: boolean;
  }) => {
    const { data } = await apiClient.get<ResourceBookingResponse[]>('/resources/bookings', { params });
    return data;
  },

  getBookingById: async (id: number) => {
    const { data } = await apiClient.get<ResourceBookingResponse>(`/resources/bookings/${id}`);
    return data;
  },

  createBooking: async (booking: ResourceBookingCreate) => {
    const { data } = await apiClient.post<ResourceBookingResponse>('/resources/bookings', booking);
    return data;
  },

  approveBooking: async (id: number) => {
    const { data } = await apiClient.post<ResourceBookingResponse>(`/resources/bookings/${id}/approve`);
    return data;
  },

  rejectBooking: async (id: number, reason?: string) => {
    const { data } = await apiClient.post<ResourceBookingResponse>(`/resources/bookings/${id}/reject`, { reason });
    return data;
  },

  cancelBooking: async (id: number, reason?: string) => {
    const { data } = await apiClient.post<ResourceBookingResponse>(`/resources/bookings/${id}/cancel`, { reason });
    return data;
  },

  // Availability & Conflict Check
  checkAvailability: async (params: {
    resource_id: number;
    date: string;
    start_time: string;
    end_time: string;
  }) => {
    const { data } = await apiClient.get<AvailabilityResponse>('/resources/availability', { params });
    return data;
  },
};
