import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, ClipboardList, Info } from 'lucide-react';
import { isAxiosError } from 'axios';
import {
  DataTable,
  type Column,
  FormModal,
  StatusBadge,
} from '@/components/common';
import {
  listChangeRequests,
  createChangeRequest,
  type ChangeRequestItem,
} from '@/api/workflows';

export function FacultyChangeRequestsPage() {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  // Form State
  const [requestType, setRequestType] = useState<
    'TIMETABLE_CHANGE' | 'ROOM_CHANGE' | 'FACULTY_AVAILABILITY_CHANGE' | 'RESOURCE_REQUEST'
  >('TIMETABLE_CHANGE');
  const [relatedEntityId, setRelatedEntityId] = useState<number | ''>('');
  const [reason, setReason] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data: requests, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['faculty-change-requests'],
    queryFn: () => listChangeRequests(0, 100),
  });

  const getErrorMsg = (err: unknown, defaultMsg: string) => {
    if (isAxiosError(err)) {
      return err.response?.data?.detail || defaultMsg;
    } else if (err instanceof Error) {
      return err.message;
    }
    return defaultMsg;
  };

  const createMutation = useMutation({
    mutationFn: createChangeRequest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['faculty-change-requests'] });
      setIsModalOpen(false);
      resetForm();
    },
    onError: (err) => setFormError(getErrorMsg(err, 'Failed to submit change request.')),
  });

  const resetForm = () => {
    setRequestType('TIMETABLE_CHANGE');
    setRelatedEntityId('');
    setReason('');
    setFormError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason || reason.trim().length < 5) {
      setFormError('Reason must be at least 5 characters explaining the justification.');
      return;
    }
    createMutation.mutate({
      request_type: requestType,
      related_entity_id: relatedEntityId === '' ? null : Number(relatedEntityId),
      reason: reason.trim(),
    });
  };

  const filteredRequests = (requests || []).filter((r) => {
    if (statusFilter === 'ALL') return true;
    return r.status === statusFilter;
  });

  const columns: Column<ChangeRequestItem>[] = [
    {
      header: 'Request Type & ID',
      accessor: 'request_type',
      render: (row) => (
        <div>
          <div className="font-bold text-slate-900">
            {(row.request_type || 'CHANGE_REQUEST').replace(/_/g, ' ')}
          </div>
          <div className="text-xs text-slate-500 font-mono">
            Request #{row.id}
            {row.related_entity_id ? ` · Ref Entity #${row.related_entity_id}` : ''}
          </div>
        </div>
      ),
    },
    {
      header: 'Submission Date',
      accessor: 'created_at',
      render: (row) => (
        <span className="text-xs text-slate-600 font-mono">
          {new Date(row.created_at).toLocaleDateString()}
        </span>
      ),
    },
    {
      header: 'Justification / Reason',
      accessor: 'reason',
      render: (row) => (
        <div className="max-w-md">
          <p className="text-xs text-slate-800 line-clamp-2">{row.reason}</p>
        </div>
      ),
    },
    {
      header: 'Status & Admin Review',
      accessor: 'status',
      render: (row) => {
        const variant =
          row.status === 'APPROVED'
            ? 'success'
            : row.status === 'PENDING'
            ? 'warning'
            : 'danger';
        return (
          <div className="space-y-1">
            <StatusBadge status={row.status} variant={variant} />
            {row.review_note && (
              <p className="text-[11px] text-slate-500 italic max-w-xs">
                Note: {row.review_note}
              </p>
            )}
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto pb-10">
      {/* Top Banner */}
      <div className="bg-[#142542] text-white p-6 rounded-2xl shadow-sm border border-[#1D3152] flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ClipboardList size={20} className="text-[#38BDF8]" />
            <h1 className="text-xl font-black tracking-tight">Academic Change Requests</h1>
          </div>
          <p className="text-xs text-[#94A3B8] mt-1">
            Submit formal modification petitions for room changes, timetable adjustments, or availability updates.
          </p>
        </div>
        <button
          onClick={() => {
            resetForm();
            setIsModalOpen(true);
          }}
          className="inline-flex items-center gap-2 px-4 py-2 bg-[#2B568F] hover:bg-[#1D3B5C] text-white text-xs font-bold rounded-xl shadow-xs transition-colors"
        >
          <Plus size={16} />
          New Change Request
        </button>
      </div>

      {/* Workflow Policy Callout */}
      <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-amber-900 flex items-start gap-3">
        <Info size={20} className="text-amber-600 shrink-0 mt-0.5" />
        <div className="text-xs space-y-1">
          <p className="font-bold">Administrative Governance & Audit Protocol</p>
          <p className="text-amber-800 leading-relaxed">
            All submitted change requests enter the central Administrative Queue. Approvals are checked against timetable
            conflicts, room availability, and faculty working hour policies before alterations are committed to published schedules.
          </p>
        </div>
      </div>

      {/* Filter Header */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-700">Filter by Review Status:</span>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-1.5 border border-slate-200 rounded-lg text-xs bg-white font-medium"
        >
          <option value="ALL">All Requests</option>
          <option value="PENDING">Pending Review</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
        </select>
      </div>

      <DataTable<ChangeRequestItem>
        columns={columns}
        data={filteredRequests}
        isLoading={isLoading}
        isError={isError}
        error={error as Error | null}
        onRefresh={refetch}
        keyExtractor={(row) => row.id}
        searchPlaceholder="Filter change requests…"
        emptyMessage="You have not submitted any schedule or room modification requests."
      />

      {/* Submit Change Request Modal */}
      <FormModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Submit Academic Change Request"
      >
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {formError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 font-medium">
              {formError}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Request Category *
              </label>
              <select
                value={requestType}
                onChange={(e) =>
                  setRequestType(
                    e.target.value as
                      | 'TIMETABLE_CHANGE'
                      | 'ROOM_CHANGE'
                      | 'FACULTY_AVAILABILITY_CHANGE'
                      | 'RESOURCE_REQUEST'
                  )
                }
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
              >
                <option value="TIMETABLE_CHANGE">Timetable Reschedule / Swap</option>
                <option value="ROOM_CHANGE">Classroom / Lab Reallocation</option>
                <option value="FACULTY_AVAILABILITY_CHANGE">Availability Preference Update</option>
                <option value="RESOURCE_REQUEST">Campus Facility Request</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Related Timetable Entry or Course ID (Optional)
              </label>
              <input
                type="number"
                min={1}
                placeholder="e.g. 15"
                value={relatedEntityId}
                onChange={(e) =>
                  setRelatedEntityId(e.target.value ? Number(e.target.value) : '')
                }
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Detailed Reason & Academic Justification *
              </label>
              <textarea
                rows={4}
                required
                placeholder="Provide a clear explanation for the requested change (minimum 5 characters)…"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
              />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
            <button
              type="button"
              onClick={() => setIsModalOpen(false)}
              className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="px-4 py-2 bg-[#2B568F] hover:bg-[#1D3B5C] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
            >
              {createMutation.isPending ? 'Submitting…' : 'Submit Request'}
            </button>
          </div>
        </form>
      </FormModal>
    </div>
  );
}
