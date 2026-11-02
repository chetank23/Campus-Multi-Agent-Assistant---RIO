import { apiClient } from './client';

export interface AnalyticsOverview {
  people: {
    total_users: number;
    total_students: number;
    total_faculty: number;
    active_users: number;
  };
  academic: {
    total_departments: number;
    total_courses: number;
    total_sections: number;
  };
  infrastructure: {
    total_buildings: number;
    total_rooms: number;
    classrooms: number;
    labs: number;
    total_seat_capacity: number;
  };
  timetables: {
    total_versions: number;
    status_breakdown: Record<string, number>;
  };
  resource_bookings: {
    total_bookings: number;
    status_breakdown: Record<string, number>;
  };
  change_requests: {
    total_change_requests: number;
    status_breakdown: Record<string, number>;
  };
  department_summaries: Array<{
    department_id: number;
    department_code: string;
    department_name: string;
    faculty_count: number;
    student_count: number;
    course_count: number;
    published_schedule_entries: number;
  }>;
}

export interface DepartmentProgress {
  department_id: number;
  department_code: string;
  department_name: string;
  total_sections: number;
  published_sections: number;
  completion_percentage: number;
}

export const analyticsApi = {
  getOverview: async (): Promise<AnalyticsOverview> => {
    const { data } = await apiClient.get<AnalyticsOverview>('/admin/analytics/overview');
    return data;
  },

  getDepartmentProgress: async (): Promise<DepartmentProgress[]> => {
    const { data } = await apiClient.get<DepartmentProgress[]>('/admin/analytics/department-progress');
    return data;
  },
};
