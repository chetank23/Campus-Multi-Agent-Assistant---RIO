import { useQuery } from '@tanstack/react-query';
import {
  Users,
  Building2,
  CalendarDays,
  ClipboardList,
  Boxes,
  RefreshCw,
  BookOpen,
} from 'lucide-react';
import { PageHeader, LoadingState, ErrorState, StatCard } from '@/components/common';
import { analyticsApi } from '@/api/analytics';

export function ReportsPage() {
  const {
    data: overview,
    isLoading: isOverviewLoading,
    isError: isOverviewError,
    refetch: refetchOverview,
    isFetching: isRefetchingOverview,
  } = useQuery({
    queryKey: ['analytics-overview'],
    queryFn: analyticsApi.getOverview,
    staleTime: 60_000,
  });

  const {
    data: progress,
    isLoading: isProgressLoading,
    isError: isProgressError,
    refetch: refetchProgress,
  } = useQuery({
    queryKey: ['department-progress'],
    queryFn: analyticsApi.getDepartmentProgress,
    staleTime: 60_000,
  });

  const isLoading = isOverviewLoading || isProgressLoading;
  const isError = isOverviewError || isProgressError;

  const handleRefreshAll = () => {
    refetchOverview();
    refetchProgress();
  };

  if (isLoading) {
    return (
      <div className="py-12">
        <LoadingState message="Aggregating live institutional reports & metrics…" />
      </div>
    );
  }

  if (isError || !overview) {
    return (
      <div className="py-12">
        <ErrorState
          title="Failed to Load Analytics"
          message="Could not retrieve real-time institutional metrics from the database."
          onRetry={handleRefreshAll}
        />
      </div>
    );
  }

  const { people, academic, infrastructure, timetables, resource_bookings, change_requests, department_summaries } =
    overview;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports & Analytics"
        subtitle="Verified institutional KPIs, department metrics, timetable status, and space utilization."
        actions={
          <button
            onClick={handleRefreshAll}
            className="inline-flex items-center gap-2 px-3.5 py-2 border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg shadow-xs transition-colors"
          >
            <RefreshCw size={16} className={isRefetchingOverview ? 'animate-spin' : ''} />
            {isRefetchingOverview ? 'Refreshing…' : 'Refresh Metrics'}
          </button>
        }
      />

      {/* Top 4 Primary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Campus Population"
          value={people.total_users}
          sub={`${people.total_students} Students · ${people.total_faculty} Faculty`}
          icon={<Users size={22} className="text-primary-600" />}
        />
        <StatCard
          label="Academic Scope"
          value={academic.total_courses}
          sub={`${academic.total_departments} Departments · ${academic.total_sections} Sections`}
          icon={<BookOpen size={22} className="text-blue-600" />}
        />
        <StatCard
          label="Campus Spaces"
          value={infrastructure.total_rooms}
          sub={`${infrastructure.classrooms} Classrooms · ${infrastructure.labs} Labs (${infrastructure.total_seat_capacity} Seats)`}
          icon={<Building2 size={22} className="text-emerald-600" />}
        />
        <StatCard
          label="Timetable Versions"
          value={timetables.total_versions}
          sub={`${timetables.status_breakdown['PUBLISHED'] || 0} Published · ${timetables.status_breakdown['DRAFT'] || 0} Draft`}
          icon={<CalendarDays size={22} className="text-purple-600" />}
        />
      </div>

      {/* Department Timetable Completion Section */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-bold text-slate-900">
              Department Timetable Completion
            </h2>
            <p className="text-xs text-slate-500">
              Published section timetables versus active academic cohorts
            </p>
          </div>
          <span className="px-3 py-1 bg-primary-50 text-primary-700 text-xs font-semibold rounded-full border border-primary-200">
            Live Verified
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
          {progress?.map((d) => (
            <div
              key={d.department_id}
              className="p-4 rounded-xl border border-slate-100 bg-slate-50/70 space-y-2.5"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-slate-900">
                  {d.department_name}
                </span>
                <span className="text-xs font-bold text-slate-500 font-mono">
                  {d.department_code}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs text-slate-600">
                <span>
                  {d.published_sections} of {d.total_sections} sections published
                </span>
                <span className="font-bold text-primary-700">
                  {d.completion_percentage}%
                </span>
              </div>
              <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-primary-600 h-2 rounded-full transition-all duration-500"
                  style={{ width: `${d.completion_percentage}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Middle 2-Column Grid: Department Details & Operational Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Department Academic Summary Table (2 columns wide) */}
        <div className="lg:col-span-2 bg-white p-6 rounded-2xl border border-slate-200 shadow-xs">
          <h2 className="text-base font-bold text-slate-900 mb-1">
            Department Academic Directory & Schedules
          </h2>
          <p className="text-xs text-slate-500 mb-4">
            Aggregated headcount and scheduled lectures per department
          </p>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                <tr>
                  <th className="py-2.5 px-3">Department</th>
                  <th className="py-2.5 px-3">Code</th>
                  <th className="py-2.5 px-3 text-right">Faculty</th>
                  <th className="py-2.5 px-3 text-right">Students</th>
                  <th className="py-2.5 px-3 text-right">Courses</th>
                  <th className="py-2.5 px-3 text-right">Published Slots</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {department_summaries.map((dept) => (
                  <tr key={dept.department_id} className="hover:bg-slate-50/50">
                    <td className="py-3 px-3 font-medium text-slate-900">
                      {dept.department_name}
                    </td>
                    <td className="py-3 px-3 font-mono text-slate-500">
                      {dept.department_code}
                    </td>
                    <td className="py-3 px-3 text-right font-medium text-slate-700">
                      {dept.faculty_count}
                    </td>
                    <td className="py-3 px-3 text-right font-medium text-slate-700">
                      {dept.student_count}
                    </td>
                    <td className="py-3 px-3 text-right font-medium text-slate-700">
                      {dept.course_count}
                    </td>
                    <td className="py-3 px-3 text-right font-bold text-primary-700">
                      {dept.published_schedule_entries}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Operational Status Sidecards (1 column wide) */}
        <div className="space-y-6">
          {/* Resource Bookings Status */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs space-y-3">
            <div className="flex items-center gap-2">
              <Boxes size={18} className="text-primary-600" />
              <h3 className="text-sm font-bold text-slate-900">
                Resource Reservations
              </h3>
            </div>
            <div className="space-y-2 pt-1 text-xs">
              <div className="flex justify-between items-center p-2 rounded-lg bg-emerald-50 text-emerald-800">
                <span className="font-medium">Approved Bookings</span>
                <span className="font-bold">{resource_bookings.status_breakdown['APPROVED'] || 0}</span>
              </div>
              <div className="flex justify-between items-center p-2 rounded-lg bg-amber-50 text-amber-800">
                <span className="font-medium">Pending Approvals</span>
                <span className="font-bold">{resource_bookings.status_breakdown['PENDING'] || 0}</span>
              </div>
              <div className="flex justify-between items-center p-2 rounded-lg bg-red-50 text-red-800">
                <span className="font-medium">Rejected / Cancelled</span>
                <span className="font-bold">
                  {(resource_bookings.status_breakdown['REJECTED'] || 0) +
                    (resource_bookings.status_breakdown['CANCELLED'] || 0)}
                </span>
              </div>
            </div>
          </div>

          {/* Change Requests Status */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs space-y-3">
            <div className="flex items-center gap-2">
              <ClipboardList size={18} className="text-primary-600" />
              <h3 className="text-sm font-bold text-slate-900">
                Workflow Change Requests
              </h3>
            </div>
            <div className="space-y-2 pt-1 text-xs">
              <div className="flex justify-between items-center p-2 rounded-lg bg-slate-50 text-slate-700">
                <span>Total Requests Submitted</span>
                <span className="font-bold">{change_requests.total_change_requests}</span>
              </div>
              <div className="flex justify-between items-center p-2 rounded-lg bg-amber-50 text-amber-800">
                <span>Awaiting Review</span>
                <span className="font-bold">{change_requests.status_breakdown['PENDING'] || 0}</span>
              </div>
              <div className="flex justify-between items-center p-2 rounded-lg bg-emerald-50 text-emerald-800">
                <span>Reviewed & Approved</span>
                <span className="font-bold">{change_requests.status_breakdown['APPROVED'] || 0}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
