/**
 * pages/admin/curriculum/AdminCurriculumInboxPage.tsx
 * ---------------------------------------------------
 * Department Curriculum Releases Inbox & Acknowledgement Portal.
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Inbox,
  CheckCircle2,
  Clock,
  ArrowRight,
} from 'lucide-react';
import {
  getAdminCurriculumInbox,
  acknowledgeCurriculumRelease,
  type CurriculumRelease,
} from '@/api/curriculum';
import { LoadingState } from '@/components/common';

export const AdminCurriculumInboxPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedRelease, setSelectedRelease] = useState<CurriculumRelease | null>(null);
  const [ackNotes, setAckNotes] = useState('');

  const { data: inbox, isLoading } = useQuery({
    queryKey: ['admin', 'curriculum-inbox'],
    queryFn: getAdminCurriculumInbox,
    refetchInterval: 15_000,
  });

  const ackMutation = useMutation({
    mutationFn: async () => {
      if (!selectedRelease) return;
      return acknowledgeCurriculumRelease(selectedRelease.id, ackNotes.trim() || undefined);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'curriculum-inbox'] });
      setSelectedRelease(null);
      setAckNotes('');
    },
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ── Header ───────────────────────────────────────────────────── */}
      <div>
        <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
          <Inbox className="w-5 h-5 text-indigo-600" />
          Department Curriculum Release Inbox
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Official academic curricula released by the Super Administrator for this department. Acknowledge and proceed to section allocation.
        </p>
      </div>

      {/* ── Releases List ────────────────────────────────────────────── */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="py-12 flex justify-center">
            <LoadingState message="Loading department curriculum releases..." />
          </div>
        ) : (inbox || []).length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-xs">
            No published curricula in your department inbox.
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {(inbox || []).map((rel) => (
              <div key={rel.id} className="p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-slate-50/50 transition-colors">
                <div className="space-y-1">
                  <div className="flex items-center gap-2.5">
                    <span className="font-mono text-sm font-bold text-indigo-950">{rel.version_code}</span>
                    <span className="text-xs font-semibold px-2 py-0.5 rounded bg-indigo-50 text-indigo-700">
                      {rel.program_name}
                    </span>
                    {rel.is_acknowledged ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">
                        <CheckCircle2 className="w-3 h-3" /> ACKNOWLEDGED
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 animate-pulse">
                        <Clock className="w-3 h-3" /> ACTION REQUIRED
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500">
                    Regulation {rel.regulation_code} • Released by {rel.released_by_name} on {new Date(rel.released_at).toLocaleDateString()}
                  </p>
                  {rel.acknowledgement_notes && (
                    <p className="text-xs text-emerald-800 bg-emerald-50 p-2 rounded-lg mt-2 inline-block">
                      <strong>HOD Note:</strong> {rel.acknowledgement_notes}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2 self-end sm:self-auto">
                  {!rel.is_acknowledged ? (
                    <button
                      onClick={() => setSelectedRelease(rel)}
                      className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded-xl shadow-sm transition-all"
                    >
                      Acknowledge & Accept
                    </button>
                  ) : (
                    <button
                      onClick={() => navigate('/admin/curriculum/allocation')}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs rounded-xl shadow-sm transition-all flex items-center gap-1.5"
                    >
                      Allocate Courses <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Acknowledge Modal ────────────────────────────────────────── */}
      {selectedRelease && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-100 space-y-4">
            <h3 className="text-base font-bold text-slate-900">
              Acknowledge Curriculum Release
            </h3>
            <p className="text-xs text-slate-600">
              You are acknowledging receipt of curriculum <strong>{selectedRelease.version_code}</strong> for department operational execution.
            </p>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Acknowledgement Notes / HOD Approval (Optional)
              </label>
              <textarea
                rows={3}
                placeholder="e.g. Reviewed with departmental academic committee. Proceeding to section allocation..."
                value={ackNotes}
                onChange={(e) => setAckNotes(e.target.value)}
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setSelectedRelease(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => ackMutation.mutate()}
                disabled={ackMutation.isPending}
                className="px-4 py-2 text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl shadow-sm transition-all disabled:opacity-50"
              >
                {ackMutation.isPending ? 'Confirming...' : 'Confirm Acknowledgement'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
