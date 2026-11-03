/**
 * pages/admin/AdminSubstitutionPage.tsx
 * -------------------------------------
 * Admin & Substitution Coordinator Review Workspace:
 * 1. Pending substitution requests queue
 * 2. Deterministic candidate recommendation inspector (qualification, clash, availability, workload)
 * 3. Optimistic locking approval & rejection actions
 * 4. Reviewed history and audit visibility
 */

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  UserCheck,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Search,
  ChevronRight,
  Sparkles,
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
  type SubstitutionRequest,
} from '@/api/substitutions';

const STATUS_VARIANT_MAP: Record<string, StatusVariant> = {
  REQUESTED: 'warning',
  PROPOSED: 'info',
  APPROVED: 'success',
  REJECTED: 'danger',
  CANCELLED: 'neutral',
};

export function AdminSubstitutionPage() {
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<'pending' | 'all'>('pending');
  const [searchQuery, setSearchQuery] = useState('');

  // Inspector modal state
  const [inspectingRequest, setInspectingRequest] = useState<SubstitutionRequest | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<number | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);

  // Reject modal state
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');

  // Queries
  const { data: pendingRequests = [], isLoading: pendingLoading } = useQuery({
    queryKey: ['substitutions', 'pending'],
    queryFn: async () => {
      const res = await substitutionsApi.getPendingSubstitutionsQueue();
      return res.data;
    },
  });

  const { data: allRequests = [], isLoading: allLoading } = useQuery({
    queryKey: ['substitutions', 'all'],
    queryFn: async () => {
      const res = await substitutionsApi.getMySubstitutionRequests(); // returns all for admin
      return res.data;
    },
  });

  // Query candidate recommendations when a request is inspected
  const {
    data: candidateRecs,
    isLoading: candidatesLoading,
  } = useQuery({
    queryKey: ['substitutions', 'candidates', inspectingRequest?.id],
    queryFn: async () => {
      if (!inspectingRequest) return null;
      const res = await substitutionsApi.getCandidateRecommendations(inspectingRequest.id);
      return res.data;
    },
    enabled: !!inspectingRequest,
  });

  // Mutations
  const reviewMutation = useMutation({
    mutationFn: (payload: {
      id: number;
      action: 'APPROVE' | 'REJECT';
      substitute_faculty_id?: number | null;
      rejection_reason?: string | null;
      version: number;
    }) =>
      substitutionsApi.reviewSubstitutionRequest(payload.id, {
        action: payload.action,
        substitute_faculty_id: payload.substitute_faculty_id,
        rejection_reason: payload.rejection_reason,
        version: payload.version,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['substitutions'] });
      setInspectingRequest(null);
      setSelectedCandidateId(null);
      setRejectModalOpen(false);
      setRejectionReason('');
      setReviewError(null);
    },
    onError: (err) => {
      if (isAxiosError(err) && err.response?.data?.detail) {
        setReviewError(err.response.data.detail);
      } else {
        setReviewError('Review action failed. Please refresh.');
      }
    },
  });

  // Statistics
  const stats = useMemo(() => {
    const pendingCount = pendingRequests.length;
    const totalCount = allRequests.length;
    const approvedCount = allRequests.filter((r) => r.status === 'APPROVED').length;
    const rejectedCount = allRequests.filter((r) => r.status === 'REJECTED').length;
    return { pendingCount, totalCount, approvedCount, rejectedCount };
  }, [pendingRequests, allRequests]);

  const filteredPending = useMemo(() => {
    if (!searchQuery) return pendingRequests;
    const q = searchQuery.toLowerCase();
    return pendingRequests.filter(
      (r) =>
        r.course_code?.toLowerCase().includes(q) ||
        r.course_name?.toLowerCase().includes(q) ||
        r.original_faculty_name?.toLowerCase().includes(q) ||
        r.substitution_date?.toLowerCase().includes(q)
    );
  }, [pendingRequests, searchQuery]);

  const filteredAll = useMemo(() => {
    if (!searchQuery) return allRequests;
    const q = searchQuery.toLowerCase();
    return allRequests.filter(
      (r) =>
        r.course_code?.toLowerCase().includes(q) ||
        r.course_name?.toLowerCase().includes(q) ||
        r.original_faculty_name?.toLowerCase().includes(q) ||
        r.status?.toLowerCase().includes(q)
    );
  }, [allRequests, searchQuery]);

  const handleApprove = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inspectingRequest || !selectedCandidateId) {
      setReviewError('Please select a qualified substitute faculty candidate.');
      return;
    }
    reviewMutation.mutate({
      id: inspectingRequest.id,
      action: 'APPROVE',
      substitute_faculty_id: selectedCandidateId,
      version: inspectingRequest.version,
    });
  };

  const handleReject = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inspectingRequest) return;
    if (rejectionReason.trim().length < 3) {
      setReviewError('A substantive rejection reason is required (minimum 3 characters).');
      return;
    }
    reviewMutation.mutate({
      id: inspectingRequest.id,
      action: 'REJECT',
      rejection_reason: rejectionReason.trim(),
      version: inspectingRequest.version,
    });
  };

  const columns: Column<SubstitutionRequest>[] = [
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
      header: 'Course & Venue',
      render: (r) => (
        <div>
          <div className="font-medium text-primary-600 dark:text-primary-400">
            {r.course_code} - {r.course_name}
          </div>
          <div className="text-xs text-gray-500">
            Room: {r.room_number || 'N/A'} | Section: {r.section_name || 'N/A'}
          </div>
        </div>
      ),
    },
    {
      header: 'Requesting Faculty',
      render: (r) => (
        <div>
          <div className="font-semibold text-gray-900 dark:text-gray-100">{r.original_faculty_name}</div>
          <div className="text-xs text-gray-500 max-w-xs truncate" title={r.reason || ''}>
            Reason: {r.reason}
          </div>
        </div>
      ),
    },
    {
      header: 'Assigned Substitute',
      render: (r) => (
        <div>
          {r.substitute_faculty_name ? (
            <span className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
              {r.substitute_faculty_name}
            </span>
          ) : (
            <span className="text-xs text-gray-400 italic">None</span>
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
      header: 'Action',
      render: (r) => {
        if (r.status === 'REQUESTED' || r.status === 'PROPOSED') {
          return (
            <button
              onClick={() => {
                setInspectingRequest(r);
                setSelectedCandidateId(null);
                setReviewError(null);
              }}
              className="px-3 py-1.5 text-xs font-semibold text-white bg-primary-600 hover:bg-primary-700 rounded-lg shadow-sm transition-colors flex items-center gap-1"
            >
              Review & Assign <ChevronRight size={14} />
            </button>
          );
        }
        return <span className="text-xs text-gray-400">Archived</span>;
      },
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Faculty Substitution Coordinator"
        subtitle="Review faculty unavailability requests, inspect transparent deterministic substitute recommendations, and approve single-date temporary coverage."
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Pending Requests"
          value={stats.pendingCount}
          sub="Awaiting coordinator action"
          icon={<Clock className="h-5 w-5 text-amber-600" />}
        />
        <StatCard
          label="Total Requests"
          value={stats.totalCount}
          sub="All-time submissions"
          icon={<UserCheck className="h-5 w-5 text-primary-600" />}
        />
        <StatCard
          label="Approved Substitutions"
          value={stats.approvedCount}
          sub="Successfully covered"
          icon={<CheckCircle2 className="h-5 w-5 text-emerald-600" />}
        />
        <StatCard
          label="Rejected Requests"
          value={stats.rejectedCount}
          sub="Declined requests"
          icon={<XCircle className="h-5 w-5 text-red-600" />}
        />
      </div>

      {/* Tabs & Search */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4 border-b border-gray-200 dark:border-gray-800 pb-3">
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setActiveTab('pending')}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeTab === 'pending'
                ? 'bg-primary-600 text-white shadow-sm'
                : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
          >
            Pending Queue ({pendingRequests.length})
          </button>
          <button
            onClick={() => setActiveTab('all')}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeTab === 'all'
                ? 'bg-primary-600 text-white shadow-sm'
                : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
          >
            All Requests ({allRequests.length})
          </button>
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search faculty or course..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
      </div>

      {/* Main Table */}
      {activeTab === 'pending' ? (
        <DataTable<SubstitutionRequest>
          columns={columns}
          data={filteredPending}
          isLoading={pendingLoading}
          isError={false}
          keyExtractor={(r) => r.id}
          emptyMessage="No pending substitution requests requiring review."
        />
      ) : (
        <DataTable<SubstitutionRequest>
          columns={columns}
          data={filteredAll}
          isLoading={allLoading}
          isError={false}
          keyExtractor={(r) => r.id}
          emptyMessage="No substitution requests found."
        />
      )}

      {/* Candidate Inspector & Review Modal */}
      {inspectingRequest && (
        <FormModal
          isOpen={true}
          title="Review Substitution & Assign Faculty"
          onClose={() => setInspectingRequest(null)}
        >
          <form onSubmit={handleApprove} className="space-y-4 max-h-[75vh] overflow-y-auto pr-1">
            {/* Target Occurrence Summary */}
            <div className="bg-gray-50 dark:bg-gray-900 p-3.5 rounded-xl border border-gray-200 dark:border-gray-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-primary-700 dark:text-primary-300 uppercase">
                  Class Occurrence
                </span>
                <span className="text-xs font-medium text-gray-500">
                  Version {inspectingRequest.version}
                </span>
              </div>
              <div className="text-base font-semibold text-gray-900 dark:text-gray-100">
                {inspectingRequest.course_code} - {inspectingRequest.course_name}
              </div>
              <div className="text-xs text-gray-600 dark:text-gray-400 grid grid-cols-2 gap-2">
                <div>
                  Date: <span className="font-semibold">{inspectingRequest.substitution_date}</span> (
                  {inspectingRequest.slot_day})
                </div>
                <div>
                  Time:{' '}
                  <span className="font-semibold">
                    {inspectingRequest.start_time} - {inspectingRequest.end_time}
                  </span>
                </div>
                <div>
                  Off-Duty Faculty:{' '}
                  <span className="font-semibold text-gray-900 dark:text-gray-200">
                    {inspectingRequest.original_faculty_name}
                  </span>
                </div>
                <div>
                  Room: <span className="font-semibold">{inspectingRequest.room_number || 'N/A'}</span>
                </div>
              </div>
              <div className="text-xs bg-amber-50 dark:bg-amber-950/40 p-2 rounded border border-amber-200 dark:border-amber-800 text-amber-900 dark:text-amber-200">
                <span className="font-semibold">Faculty Reason:</span> {inspectingRequest.reason}
              </div>
            </div>

            {reviewError && (
              <div className="p-3 bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300 text-xs rounded-lg border border-red-200 dark:border-red-800 flex items-start gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <span>{reviewError}</span>
              </div>
            )}

            {/* Candidate Recommendations List */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase flex items-center gap-1.5">
                  <Sparkles size={14} className="text-primary-600" />
                  Deterministic Ranked Candidates
                </label>
                <div className="flex items-center gap-2">
                  {candidateRecs?.evaluation_status && (
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${
                        candidateRecs.evaluation_status === 'ELIGIBLE'
                          ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
                          : candidateRecs.evaluation_status === 'NO_ELIGIBLE_CANDIDATE'
                          ? 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300'
                          : 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300'
                      }`}
                    >
                      {candidateRecs.evaluation_status.replace(/_/g, ' ')}
                    </span>
                  )}
                  <span className="text-xs text-gray-500">
                    {candidateRecs?.candidates.filter((c) => c.is_eligible).length || 0} Eligible
                  </span>
                </div>
              </div>

              {candidateRecs?.evaluation_status === 'CANNOT_DETERMINE' && (
                <div className="mb-3 p-2.5 bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 text-xs rounded-lg border border-amber-200 dark:border-amber-800">
                  <span className="font-semibold">Cannot Determine Substitute:</span>{' '}
                  {candidateRecs.cannot_determine_reason || 'Missing or ambiguous qualification data.'}
                </div>
              )}

              {candidateRecs?.evaluation_status === 'NO_ELIGIBLE_CANDIDATE' && (
                <div className="mb-3 p-2.5 bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 text-xs rounded-lg border border-amber-200 dark:border-amber-800">
                  <span className="font-semibold">No Eligible Substitute:</span> All evaluated faculty members have active timetable clashes, lack verified course qualifications, or exceed maximum teaching loads.
                </div>
              )}

              {candidatesLoading ? (
                <div className="py-8 text-center text-xs text-gray-500">
                  Evaluating clashes, teaching qualifications, and workload limits...
                </div>
              ) : (
                <div className="space-y-2">
                  {candidateRecs?.candidates.map((cand) => {
                    const isSelected = selectedCandidateId === cand.faculty_id;
                    return (
                      <div
                        key={cand.faculty_id}
                        onClick={() => {
                          if (cand.is_eligible) {
                            setSelectedCandidateId(cand.faculty_id);
                            setReviewError(null);
                          }
                        }}
                        className={`p-3 rounded-xl border transition-all ${
                          !cand.is_eligible
                            ? 'opacity-60 bg-gray-50 dark:bg-gray-900/50 border-gray-200 dark:border-gray-800 cursor-not-allowed'
                            : isSelected
                            ? 'border-primary-600 bg-primary-50/50 dark:bg-primary-950/30 shadow-sm cursor-pointer'
                            : 'border-gray-200 dark:border-gray-800 hover:border-gray-300 dark:hover:border-gray-700 cursor-pointer'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <input
                              type="radio"
                              name="selectedCandidate"
                              checked={isSelected}
                              disabled={!cand.is_eligible}
                              onChange={() => setSelectedCandidateId(cand.faculty_id)}
                              className="text-primary-600 focus:ring-primary-500"
                            />
                            <div>
                              <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                                {cand.faculty_name}
                              </div>
                              <div className="text-xs text-gray-500">
                                {cand.department_name || 'Faculty'} | {cand.designation || 'Lecturer'}
                              </div>
                            </div>
                          </div>

                          <div className="text-right">
                            <span
                              className={`inline-block px-2 py-0.5 text-xs font-semibold rounded-full ${
                                cand.qualification_tier === 'DIRECT_ASSIGNMENT'
                                  ? 'bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300'
                                  : cand.qualification_tier === 'DEPARTMENT_MATCH'
                                  ? 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300'
                                  : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300'
                              }`}
                            >
                              {cand.qualification_tier.replace('_', ' ')}
                            </span>
                            <div className="text-xs font-medium text-gray-600 dark:text-gray-400 mt-1">
                              Load: {cand.current_weekly_load}/{cand.max_weekly_load} hrs ({cand.load_percentage}%)
                            </div>
                          </div>
                        </div>

                        {/* Breakdown pills */}
                        <div className="mt-2 pt-2 border-t border-gray-100 dark:border-gray-800 flex flex-wrap gap-1.5">
                          {cand.eligibility_breakdown.map((b, idx) => (
                            <span
                              key={idx}
                              title={b.detail}
                              className={`text-[10px] px-2 py-0.5 rounded font-medium ${
                                b.status === 'PASS'
                                  ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                                  : 'bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300'
                              }`}
                            >
                              {b.factor}: {b.status}
                            </span>
                          ))}
                        </div>

                        {!cand.is_eligible && (
                          <div className="mt-1.5 text-xs text-red-600 dark:text-red-400 font-medium">
                            Ineligible: {cand.ineligibility_reasons.join(', ')}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="pt-3 border-t border-gray-200 dark:border-gray-800 flex justify-between items-center">
              <button
                type="button"
                onClick={() => setRejectModalOpen(true)}
                className="text-xs text-red-600 hover:text-red-800 font-medium transition-colors"
              >
                Reject Request...
              </button>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setInspectingRequest(null)}
                  className="px-4 py-2 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={reviewMutation.isPending || !selectedCandidateId}
                  className="px-4 py-2 text-xs font-semibold text-white bg-primary-600 hover:bg-primary-700 rounded-lg shadow-sm transition-colors disabled:opacity-50"
                >
                  {reviewMutation.isPending ? 'Approving...' : 'Approve Substitution'}
                </button>
              </div>
            </div>
          </form>
        </FormModal>
      )}

      {/* Rejection Confirmation Modal */}
      {rejectModalOpen && inspectingRequest && (
        <FormModal
          isOpen={true}
          title="Reject Substitution Request"
          onClose={() => setRejectModalOpen(false)}
        >
          <form onSubmit={handleReject} className="space-y-4">
            <div className="text-sm text-gray-700 dark:text-gray-300">
              Are you sure you want to reject the substitution request for{' '}
              <span className="font-semibold text-gray-900 dark:text-gray-100">
                {inspectingRequest.course_code}
              </span>{' '}
              on <span className="font-semibold">{inspectingRequest.substitution_date}</span>?
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                Reason for Rejection <span className="text-red-500">*</span>
              </label>
              <textarea
                rows={3}
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="Explain why this request is being declined..."
                className="w-full text-sm p-2.5 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
              />
              <p className="text-xs text-gray-500 mt-1">
                The requesting faculty member will be notified of this reason.
              </p>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-gray-200 dark:border-gray-800">
              <button
                type="button"
                onClick={() => setRejectModalOpen(false)}
                className="px-4 py-2 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={reviewMutation.isPending}
                className="px-4 py-2 text-xs font-semibold text-white bg-red-600 hover:bg-red-700 rounded-lg shadow-sm transition-colors disabled:opacity-50"
              >
                {reviewMutation.isPending ? 'Rejecting...' : 'Confirm Rejection'}
              </button>
            </div>
          </form>
        </FormModal>
      )}
    </div>
  );
}
