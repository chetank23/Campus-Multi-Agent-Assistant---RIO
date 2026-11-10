/**
 * pages/faculty/FacultySubstitutionPage.tsx
 * -----------------------------------------
 * Faculty Substitution & Leave Coverage Management:
 * 1. Scheduled Classes occurrence inspection
 * 2. Unavailability reporting modal with date-slot locking
 * 3. Request status tracker (Requested, Approved, Rejected, Cancelled)
 * 4. Substitute assignments view (classes covering for colleagues)
 */

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CalendarDays,
  Calendar,
  UserCheck,
  Clock,
  AlertCircle,
  CheckCircle2,
  Search,
  GraduationCap,
  MapPin,
  Users,
  Info,
} from 'lucide-react';
import { isAxiosError } from 'axios';

import {
  PageHeader,
  StatCard,
  DataTable,
  type Column,
  FormModal,
  StatusBadge,
  type StatusVariant,
} from '@/components/common';

import {
  substitutionsApi,
  type ClassOccurrence,
  type SubstitutionRequest,
} from '@/api/substitutions';

const STATUS_VARIANT_MAP: Record<string, StatusVariant> = {
  REQUESTED: 'warning',
  PROPOSED: 'info',
  APPROVED: 'success',
  REJECTED: 'danger',
  CANCELLED: 'neutral',
};

export function FacultySubstitutionPage() {
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<'classes' | 'requests' | 'duties'>('classes');
  const [searchQuery, setSearchQuery] = useState('');

  // Unavailability modal state
  const [selectedClass, setSelectedClass] = useState<ClassOccurrence | null>(null);
  const [reason, setReason] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data: upcomingClasses = [], isLoading: classesLoading } = useQuery({
    queryKey: ['substitutions', 'my-classes'],
    queryFn: async () => {
      const res = await substitutionsApi.getMyScheduledClasses(28);
      return res.data;
    },
  });

  const { data: myRequests = [], isLoading: requestsLoading } = useQuery({
    queryKey: ['substitutions', 'my-requests'],
    queryFn: async () => {
      const res = await substitutionsApi.getMySubstitutionRequests();
      return res.data;
    },
  });

  const { data: myDuties = [], isLoading: dutiesLoading } = useQuery({
    queryKey: ['substitutions', 'my-assignments'],
    queryFn: async () => {
      const res = await substitutionsApi.getMySubstitutionAssignments();
      return res.data;
    },
  });

  // Mutations
  const createRequestMutation = useMutation({
    mutationFn: (payload: { timetable_entry_id: number; substitution_date: string; reason: string }) =>
      substitutionsApi.createSubstitutionRequest(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['substitutions'] });
      setSelectedClass(null);
      setReason('');
      setFormError(null);
    },
    onError: (err) => {
      if (isAxiosError(err) && err.response?.data?.detail) {
        setFormError(err.response.data.detail);
      } else {
        setFormError('Failed to submit substitution request.');
      }
    },
  });

  const cancelRequestMutation = useMutation({
    mutationFn: (id: number) => substitutionsApi.cancelSubstitutionRequest(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['substitutions'] });
    },
  });

  // KPI Calculations
  const stats = useMemo(() => {
    const totalClasses = upcomingClasses.length;
    const pendingReqs = myRequests.filter((r) => r.status === 'REQUESTED' || r.status === 'PROPOSED').length;
    const approvedReqs = myRequests.filter((r) => r.status === 'APPROVED').length;
    const coveringDuties = myDuties.length;
    return { totalClasses, pendingReqs, approvedReqs, coveringDuties };
  }, [upcomingClasses, myRequests, myDuties]);

  // Filtered lists
  const filteredClasses = useMemo(() => {
    if (!searchQuery) return upcomingClasses;
    const q = searchQuery.toLowerCase();
    return upcomingClasses.filter(
      (c) =>
        c.course_code?.toLowerCase().includes(q) ||
        c.course_name?.toLowerCase().includes(q) ||
        c.date?.toLowerCase().includes(q) ||
        c.day?.toLowerCase().includes(q) ||
        c.room_number?.toLowerCase().includes(q)
    );
  }, [upcomingClasses, searchQuery]);

  const filteredRequests = useMemo(() => {
    if (!searchQuery) return myRequests;
    const q = searchQuery.toLowerCase();
    return myRequests.filter(
      (r) =>
        r.course_code?.toLowerCase().includes(q) ||
        r.course_name?.toLowerCase().includes(q) ||
        r.substitution_date?.toLowerCase().includes(q) ||
        r.status?.toLowerCase().includes(q)
    );
  }, [myRequests, searchQuery]);

  const filteredDuties = useMemo(() => {
    if (!searchQuery) return myDuties;
    const q = searchQuery.toLowerCase();
    return myDuties.filter(
      (d) =>
        d.course_code?.toLowerCase().includes(q) ||
        d.course_name?.toLowerCase().includes(q) ||
        d.original_faculty_name?.toLowerCase().includes(q)
    );
  }, [myDuties, searchQuery]);

  // Columns for Upcoming Classes
  const classColumns: Column<ClassOccurrence>[] = [
    {
      header: 'Date & Day',
      render: (c) => (
        <div>
          <div className="font-semibold text-gray-900 dark:text-gray-100">{c.date}</div>
          <div className="text-xs text-gray-500 uppercase">{c.day}</div>
        </div>
      ),
    },
    {
      header: 'Time & Room',
      render: (c) => (
        <div>
          <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
            {c.start_time} - {c.end_time}
          </div>
          <div className="text-xs text-gray-500">
            {c.room_number ? `Room ${c.room_number}` : 'No room assigned'}
          </div>
        </div>
      ),
    },
    {
      header: 'Course & Section',
      render: (c) => (
        <div>
          <div className="font-medium text-primary-600 dark:text-primary-400">
            {c.course_code} - {c.course_name}
          </div>
          <div className="text-xs text-gray-500">
            {c.section_name || 'All Sections'} {c.batch_name ? `(${c.batch_name})` : ''}
          </div>
        </div>
      ),
    },
    {
      header: 'Coverage Status',
      render: (c) => {
        if (!c.has_active_request) {
          return <span className="text-xs text-gray-500 font-medium">Regular Schedule</span>;
        }
        const variant = STATUS_VARIANT_MAP[c.active_substitution_status || ''] || 'neutral';
        return (
          <div className="space-y-1">
            <StatusBadge status={c.active_substitution_status || 'REQUESTED'} variant={variant} />
            {c.substitute_faculty_name && (
              <div className="text-xs text-emerald-600 font-medium">
                Covered by: {c.substitute_faculty_name}
              </div>
            )}
          </div>
        );
      },
    },
    {
      header: 'Action',
      render: (c) => {
        if (c.has_active_request) {
          return (
            <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">
              Request Pending/Active
            </span>
          );
        }
        return (
          <button
            onClick={() => {
              setSelectedClass(c);
              setReason('');
              setFormError(null);
            }}
            className="px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 dark:text-amber-300 dark:bg-amber-950/40 rounded-lg transition-colors border border-amber-200 dark:border-amber-800"
          >
            Report Absence
          </button>
        );
      },
    },
  ];

  // Columns for My Requests
  const requestColumns: Column<SubstitutionRequest>[] = [
    {
      header: 'Date & Time',
      render: (r) => (
        <div>
          <div className="font-semibold text-gray-900 dark:text-gray-100">{r.substitution_date}</div>
          <div className="text-xs text-gray-500">
            {r.start_time} - {r.end_time} ({r.slot_day})
          </div>
        </div>
      ),
    },
    {
      header: 'Course',
      render: (r) => (
        <div>
          <div className="font-medium text-gray-800 dark:text-gray-200">
            {r.course_code} - {r.course_name}
          </div>
          <div className="text-xs text-gray-500">
            Room: {r.room_number || 'N/A'} | Section: {r.section_name || 'N/A'}
          </div>
        </div>
      ),
    },
    {
      header: 'Assigned Substitute',
      render: (r) => (
        <div className="text-sm">
          {r.substitute_faculty_name ? (
            <span className="font-semibold text-emerald-700 dark:text-emerald-400">
              {r.substitute_faculty_name}
            </span>
          ) : (
            <span className="text-gray-400 italic">Awaiting coordinator assignment</span>
          )}
        </div>
      ),
    },
    {
      header: 'Reason / Notes',
      render: (r) => (
        <div className="max-w-xs">
          <div className="text-xs text-gray-700 dark:text-gray-300 truncate" title={r.reason || ''}>
            {r.reason}
          </div>
          {r.rejection_reason && (
            <div className="text-xs text-red-600 dark:text-red-400 mt-1">
              Rejection: {r.rejection_reason}
            </div>
          )}
        </div>
      ),
    },
    {
      header: 'Status',
      render: (r) => (
        <StatusBadge status={r.status} variant={STATUS_VARIANT_MAP[r.status] || 'neutral'} />
      ),
    },
    {
      header: 'Actions',
      render: (r) => {
        if (r.status === 'REJECTED' || r.status === 'CANCELLED') {
          return <span className="text-xs text-gray-400">—</span>;
        }
        return (
          <button
            onClick={() => cancelRequestMutation.mutate(r.id)}
            disabled={cancelRequestMutation.isPending}
            className="text-xs text-red-600 hover:text-red-800 font-medium transition-colors"
          >
            Cancel
          </button>
        );
      },
    },
  ];

  // Columns for Covering Duties
  const dutyColumns: Column<SubstitutionRequest>[] = [
    {
      header: 'Date & Time',
      render: (d) => (
        <div>
          <div className="font-semibold text-gray-900 dark:text-gray-100">{d.substitution_date}</div>
          <div className="text-xs text-gray-500">
            {d.start_time} - {d.end_time} ({d.slot_day})
          </div>
        </div>
      ),
    },
    {
      header: 'Course & Venue',
      render: (d) => (
        <div>
          <div className="font-medium text-primary-600 dark:text-primary-400">
            {d.course_code} - {d.course_name}
          </div>
          <div className="text-xs text-gray-500">
            Room: {d.room_number || 'N/A'} | Section: {d.section_name || 'N/A'}
          </div>
        </div>
      ),
    },
    {
      header: 'Covering For Colleague',
      render: (d) => (
        <div>
          <div className="font-semibold text-gray-900 dark:text-gray-100">
            {d.original_faculty_name}
          </div>
          <div className="text-xs text-gray-500">Regular Course Faculty</div>
        </div>
      ),
    },
    {
      header: 'Status',
      render: () => <StatusBadge status="APPROVED" variant="success" />,
    },
  ];

  const formatDisplayDate = (dateStr: string, dayStr?: string) => {
    try {
      const d = new Date(dateStr + 'T00:00:00');
      if (!isNaN(d.getTime())) {
        const dayName = d.toLocaleDateString('en-US', { weekday: 'short' });
        const day = d.getDate();
        const month = d.toLocaleDateString('en-US', { month: 'short' });
        const year = d.getFullYear();
        return `${dayName}, ${day} ${month} ${year}`;
      }
    } catch {
      // fallback
    }
    return dayStr ? `${dayStr}, ${dateStr}` : dateStr;
  };

  const handleSubmitUnavailability = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedClass) return;
    if (reason.trim().length < 3) {
      setFormError('Please provide a substantive reason (minimum 3 characters).');
      return;
    }
    createRequestMutation.mutate({
      timetable_entry_id: selectedClass.timetable_entry_id,
      substitution_date: selectedClass.date,
      reason: reason.trim(),
    });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Faculty Substitutions & Leave Coverage"
        subtitle="View your scheduled classes, submit temporary date-specific unavailability requests, and track assigned substitute teaching duties."
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Scheduled Classes"
          value={stats.totalClasses}
          sub="Next 28 days"
          icon={<CalendarDays className="h-5 w-5 text-primary-600" />}
        />
        <StatCard
          label="Pending Requests"
          value={stats.pendingReqs}
          sub="Awaiting reviewer approval"
          icon={<Clock className="h-5 w-5 text-amber-600" />}
        />
        <StatCard
          label="Approved Coverage"
          value={stats.approvedReqs}
          sub="Substitute confirmed"
          icon={<CheckCircle2 className="h-5 w-5 text-emerald-600" />}
        />
        <StatCard
          label="Covering Duties"
          value={stats.coveringDuties}
          sub="Covering for colleagues"
          icon={<UserCheck className="h-5 w-5 text-blue-600" />}
        />
      </div>

      {/* Search & Tabs */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4 border-b border-gray-200 dark:border-gray-800 pb-3">
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setActiveTab('classes')}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeTab === 'classes'
                ? 'bg-primary-600 text-white shadow-sm'
                : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
          >
            My Scheduled Classes ({upcomingClasses.length})
          </button>
          <button
            onClick={() => setActiveTab('requests')}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeTab === 'requests'
                ? 'bg-primary-600 text-white shadow-sm'
                : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
          >
            My Absence Requests ({myRequests.length})
          </button>
          <button
            onClick={() => setActiveTab('duties')}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeTab === 'duties'
                ? 'bg-primary-600 text-white shadow-sm'
                : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
          >
            My Covering Duties ({myDuties.length})
          </button>
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search classes or courses..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
      </div>

      {/* Main Table View */}
      {activeTab === 'classes' && (
        <DataTable<ClassOccurrence>
          columns={classColumns}
          data={filteredClasses}
          isLoading={classesLoading}
          isError={false}
          keyExtractor={(c) => c.timetable_entry_id}
          emptyMessage="No scheduled classes found in the next 28 days."
        />
      )}

      {activeTab === 'requests' && (
        <DataTable<SubstitutionRequest>
          columns={requestColumns}
          data={filteredRequests}
          isLoading={requestsLoading}
          isError={false}
          keyExtractor={(r) => r.id}
          emptyMessage="No substitution requests submitted."
        />
      )}

      {activeTab === 'duties' && (
        <DataTable<SubstitutionRequest>
          columns={dutyColumns}
          data={filteredDuties}
          isLoading={dutiesLoading}
          isError={false}
          keyExtractor={(d) => d.id}
          emptyMessage="You have no assigned substitute teaching duties at this time."
        />
      )}

      {/* Report Absence / Substitution Modal */}
      {selectedClass && (
        <FormModal
          isOpen={true}
          title="Report Absence & Request Substitution"
          subtitle="Notify your unavailability and request a substitute for the selected class."
          icon={<Calendar className="h-5 w-5 text-blue-600" />}
          maxWidth="lg"
          onClose={() => setSelectedClass(null)}
        >
          <form onSubmit={handleSubmitUnavailability} className="space-y-4">
            {/* Target Class Occurrence Card */}
            <div className="bg-[#F0F5FF] border border-blue-100 rounded-xl p-4 space-y-3">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0">
                  <GraduationCap className="h-4 w-4" />
                </div>
                <span className="text-xs font-bold text-blue-700 tracking-wide">
                  Target Class Occurrence
                </span>
              </div>

              <div>
                <h3 className="text-base font-bold text-slate-900 tracking-tight">
                  {selectedClass.course_code} – {selectedClass.course_name}
                </h3>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-blue-100/80">
                <div className="flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-blue-500 shrink-0" />
                  <div>
                    <div className="text-[11px] text-slate-500 font-medium">Date</div>
                    <div className="text-xs font-bold text-slate-900">
                      {formatDisplayDate(selectedClass.date, selectedClass.day)}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-blue-500 shrink-0" />
                  <div>
                    <div className="text-[11px] text-slate-500 font-medium">Time</div>
                    <div className="text-xs font-bold text-slate-900">
                      {selectedClass.start_time} – {selectedClass.end_time}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <MapPin className="h-4 w-4 text-blue-500 shrink-0" />
                  <div>
                    <div className="text-[11px] text-slate-500 font-medium">Room</div>
                    <div className="text-xs font-bold text-slate-900">
                      {selectedClass.room_number || 'N/A'}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-blue-500 shrink-0" />
                  <div>
                    <div className="text-[11px] text-slate-500 font-medium">Section</div>
                    <div className="text-xs font-bold text-slate-900">
                      {selectedClass.section_name || 'AIDS-A'}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {formError && (
              <div className="p-3 bg-red-50 text-red-700 text-xs rounded-xl border border-red-200 flex items-start gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <span>{formError}</span>
              </div>
            )}

            {/* Reason for Unavailability */}
            <div>
              <label className="block text-xs font-bold text-slate-900 mb-0.5">
                Reason for Unavailability <span className="text-red-500">*</span>
              </label>
              <p className="text-xs text-slate-500 mb-2">
                Explain why you cannot attend this scheduled class.
              </p>
              <textarea
                rows={3}
                maxLength={300}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="E.g., Medical leave, attending international conference, official academic duty..."
                className="w-full text-sm p-3.5 bg-white border border-slate-200 rounded-xl text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-2xs resize-y min-h-[96px]"
              />
              <div className="text-right text-[11px] text-slate-400 font-medium mt-1">
                {reason.length} / 300
              </div>
            </div>

            {/* Privacy Notice */}
            <div className="bg-[#F0F5FF] border border-blue-100 rounded-xl p-3.5 flex items-start gap-3">
              <div className="w-6 h-6 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 mt-0.5">
                <Info className="h-3.5 w-3.5" />
              </div>
              <div className="text-xs leading-relaxed">
                <strong className="font-bold text-blue-900 block mb-0.5">Privacy Notice</strong>
                <span className="text-slate-600">
                  Your reason is strictly confidential to administrators and reviewers. It is never disclosed to students.
                </span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setSelectedClass(null)}
                className="px-5 py-2.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createRequestMutation.isPending || !reason.trim()}
                className="px-5 py-2.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-xl shadow-xs transition-colors disabled:opacity-50"
              >
                {createRequestMutation.isPending ? 'Submitting...' : 'Submit Request'}
              </button>
            </div>
          </form>
        </FormModal>
      )}
    </div>
  );
}
