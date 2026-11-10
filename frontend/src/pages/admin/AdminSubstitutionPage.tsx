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
  Calendar,
  User,
  MapPin,
  Info,
  TrendingUp,
  Check,
  X,
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

const getFacultyInitials = (name: string): string => {
  const cleaned = name.replace(/^(Dr\.|Prof\.|Mr\.|Ms\.|Mrs\.)\s+/i, '').trim();
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'FC';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
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
          maxWidth="2xl"
          onClose={() => setInspectingRequest(null)}
        >
          <form onSubmit={handleApprove} className="space-y-4">
            {/* Target Occurrence Summary */}
            <div className="bg-[#0B1528] text-white rounded-2xl p-4 sm:p-5 border border-slate-800 shadow-sm space-y-3.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold text-sky-400 uppercase tracking-widest">
                  CLASS OCCURRENCE
                </span>
                <span className="text-xs font-medium text-slate-300 bg-slate-800/80 border border-slate-700/60 px-2.5 py-0.5 rounded-full">
                  Version {inspectingRequest.version || 1}
                </span>
              </div>

              <div>
                <h3 className="text-base font-bold text-white tracking-tight">
                  {inspectingRequest.course_code} – {inspectingRequest.course_name}
                </h3>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1 text-xs">
                <div className="flex items-center gap-2 text-slate-300">
                  <Calendar className="h-4 w-4 text-sky-400 shrink-0" />
                  <span>
                    Date:{' '}
                    <strong className="font-semibold text-white">
                      {inspectingRequest.substitution_date} ({inspectingRequest.slot_day})
                    </strong>
                  </span>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <Clock className="h-4 w-4 text-sky-400 shrink-0" />
                  <span>
                    Time:{' '}
                    <strong className="font-semibold text-white">
                      {inspectingRequest.start_time} – {inspectingRequest.end_time}
                    </strong>
                  </span>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <User className="h-4 w-4 text-sky-400 shrink-0" />
                  <span>
                    Off-Duty Faculty:{' '}
                    <strong className="font-semibold text-white">
                      {inspectingRequest.original_faculty_name}
                    </strong>
                  </span>
                </div>
                <div className="flex items-center gap-2 text-slate-300">
                  <MapPin className="h-4 w-4 text-sky-400 shrink-0" />
                  <span>
                    Room:{' '}
                    <strong className="font-semibold text-white">
                      {inspectingRequest.room_number || 'N/A'}
                    </strong>
                  </span>
                </div>
              </div>

              <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl px-3.5 py-2.5 flex items-center gap-2.5 text-xs text-slate-300">
                <Info className="h-4 w-4 text-sky-400 shrink-0" />
                <span>
                  Faculty Reason:{' '}
                  <strong className="font-bold text-white uppercase">
                    {inspectingRequest.reason}
                  </strong>
                </span>
              </div>
            </div>

            {reviewError && (
              <div className="p-3 bg-red-50 text-red-700 text-xs rounded-xl border border-red-200 flex items-start gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <span>{reviewError}</span>
              </div>
            )}

            {/* Candidate Recommendations List */}
            <div className="space-y-3 pt-1">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-blue-600 shrink-0" />
                  <h4 className="text-sm font-bold text-slate-900 tracking-tight">
                    Deterministic Ranked Candidates
                  </h4>
                </div>
                <div className="flex items-center gap-2">
                  {candidateRecs?.evaluation_status && (
                    <span
                      className={`text-xs px-2.5 py-0.5 rounded-full font-semibold border ${
                        candidateRecs.evaluation_status === 'ELIGIBLE'
                          ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                          : candidateRecs.evaluation_status === 'NO_ELIGIBLE_CANDIDATE'
                          ? 'bg-slate-100 text-slate-700 border-slate-200'
                          : 'bg-amber-50 text-amber-800 border-amber-200'
                      }`}
                    >
                      {candidateRecs.evaluation_status === 'NO_ELIGIBLE_CANDIDATE'
                        ? 'No Eligible Candidate'
                        : candidateRecs.evaluation_status.replace(/_/g, ' ')}
                    </span>
                  )}
                  <span className="text-xs font-semibold text-slate-600">
                    {candidateRecs?.candidates.filter((c) => c.is_eligible).length || 0} Eligible
                  </span>
                </div>
              </div>

              {candidateRecs?.evaluation_status === 'CANNOT_DETERMINE' && (
                <div className="bg-[#F0F5FF] border border-blue-100 rounded-xl p-3.5 flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 mt-0.5">
                    <Info className="h-3.5 w-3.5" />
                  </div>
                  <div className="text-xs text-slate-700 leading-relaxed">
                    <strong className="font-bold text-slate-900">Cannot Determine Substitute:</strong>{' '}
                    {candidateRecs.cannot_determine_reason || 'Missing or ambiguous qualification data.'}
                  </div>
                </div>
              )}

              {candidateRecs?.evaluation_status === 'NO_ELIGIBLE_CANDIDATE' && (
                <div className="bg-[#F0F5FF] border border-blue-100 rounded-xl p-3.5 flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0 mt-0.5">
                    <Info className="h-3.5 w-3.5" />
                  </div>
                  <div className="text-xs text-slate-700 leading-relaxed">
                    <strong className="font-bold text-slate-900">No Eligible Substitute:</strong> All evaluated faculty members have active timetable clashes, lack verified course qualifications, or exceed maximum teaching loads.
                  </div>
                </div>
              )}

              {candidatesLoading ? (
                <div className="py-8 text-center text-xs text-slate-500">
                  Evaluating clashes, teaching qualifications, and workload limits...
                </div>
              ) : (
                <div className="space-y-3">
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
                        className={`rounded-2xl border p-4 space-y-3 transition-all ${
                          !cand.is_eligible
                            ? 'bg-white border-slate-200 shadow-2xs'
                            : isSelected
                            ? 'bg-blue-50/20 border-2 border-blue-600 shadow-xs cursor-pointer ring-2 ring-blue-500/10'
                            : 'bg-white border-slate-200 hover:border-blue-300 shadow-2xs cursor-pointer'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            {cand.is_eligible && (
                              <input
                                type="radio"
                                name="selectedCandidate"
                                checked={isSelected}
                                onChange={() => {
                                  setSelectedCandidateId(cand.faculty_id);
                                  setReviewError(null);
                                }}
                                className="h-4 w-4 text-blue-600 focus:ring-blue-500 shrink-0"
                              />
                            )}
                            <div className="w-9 h-9 rounded-full bg-blue-50 text-blue-700 font-bold text-xs flex items-center justify-center shrink-0 border border-blue-100">
                              {getFacultyInitials(cand.faculty_name)}
                            </div>
                            <div>
                              <h4 className="text-sm font-bold text-slate-900 tracking-tight">
                                {cand.faculty_name}
                              </h4>
                              <p className="text-xs text-slate-500 mt-0.5">
                                {cand.department_name || 'AI & DS'} | {cand.designation || 'Faculty Member'}
                              </p>
                            </div>
                          </div>

                          <div className="text-right">
                            {cand.is_eligible ? (
                              <span
                                className={`inline-block px-2.5 py-0.5 text-[10px] font-bold rounded uppercase tracking-wider ${
                                  cand.qualification_tier === 'DIRECT_ASSIGNMENT'
                                    ? 'bg-purple-100 text-purple-800 border border-purple-200'
                                    : cand.qualification_tier === 'DEPARTMENT_MATCH'
                                    ? 'bg-blue-100 text-blue-800 border border-blue-200'
                                    : 'bg-slate-100 text-slate-800 border border-slate-200'
                                }`}
                              >
                                {cand.qualification_tier.replace('_', ' ')}
                              </span>
                            ) : (
                              <span className="inline-block px-2.5 py-0.5 text-[10px] font-bold rounded bg-slate-200/80 text-slate-700 border border-slate-300/60 uppercase tracking-wider">
                                UNQUALIFIED
                              </span>
                            )}
                            <div className="text-xs font-medium text-slate-500 mt-1">
                              Load: {cand.current_weekly_load}/{cand.max_weekly_load} hrs ({cand.load_percentage}%)
                            </div>
                          </div>
                        </div>

                        {/* Breakdown pills */}
                        <div className="flex flex-wrap gap-2 pt-1">
                          {cand.eligibility_breakdown.map((b, idx) => (
                            <span
                              key={idx}
                              title={b.detail}
                              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold ${
                                b.status === 'PASS'
                                  ? 'bg-emerald-50 text-emerald-800 border border-emerald-200/80'
                                  : 'bg-slate-100 text-slate-700 border border-slate-200'
                              }`}
                            >
                              {b.status === 'PASS' ? (
                                <Check className="h-3 w-3 stroke-[3] text-emerald-600" />
                              ) : (
                                <X className="h-3 w-3 stroke-[3] text-slate-500" />
                              )}
                              <span>{b.factor}: {b.status}</span>
                            </span>
                          ))}
                        </div>

                        {!cand.is_eligible && cand.ineligibility_reasons.length > 0 && (
                          <div className="flex items-center gap-2 text-xs text-slate-500 pt-2 border-t border-slate-100">
                            <Info className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                            <span>Ineligible: {cand.ineligibility_reasons.join(', ')}</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="pt-4 border-t border-slate-100 flex justify-between items-center">
              <button
                type="button"
                onClick={() => setRejectModalOpen(true)}
                className="text-xs text-rose-600 hover:text-rose-700 font-semibold transition-colors"
              >
                Reject Request...
              </button>
              <div className="flex gap-2.5">
                <button
                  type="button"
                  onClick={() => setInspectingRequest(null)}
                  className="px-5 py-2.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={reviewMutation.isPending || !selectedCandidateId}
                  className="px-5 py-2.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-xl shadow-xs transition-colors disabled:opacity-50"
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
