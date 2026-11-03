/**
 * pages/admin/curriculum/AdminCurriculumRequestsPage.tsx
 * -----------------------------------------------------
 * Department Admin Curriculum Correction Request Ticketing.
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Inbox,
  Plus,
  Send,
  MessageSquare,
} from 'lucide-react';
import {
  getAdminCurriculumRequests,
  createAdminCurriculumRequest,
  addAdminRequestMessage,
} from '@/api/curriculum';
import { useAuth } from '@/auth/AuthProvider';

export const AdminCurriculumRequestsPage: React.FC = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [selectedRequestId, setSelectedRequestId] = useState<number | null>(null);
  const [replyMessage, setReplyMessage] = useState('');

  // Form State
  const [requestType, setRequestType] = useState('MISSING_SUBJECT');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const { data: requests, isLoading } = useQuery({
    queryKey: ['admin', 'curriculum-requests'],
    queryFn: () => getAdminCurriculumRequests(),
    refetchInterval: 10_000,
  });

  const selectedRequest = (requests || []).find((r) => r.id === selectedRequestId);

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!title.trim() || !description.trim()) {
        throw new Error('Title and description are required.');
      }
      const deptId = user?.department_id || 1;
      return createAdminCurriculumRequest({
        department_id: deptId,
        request_type: requestType,
        title: title.trim(),
        description: description.trim(),
      });
    },
    onSuccess: (newReq) => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'curriculum-requests'] });
      setIsCreateOpen(false);
      setTitle('');
      setDescription('');
      setSelectedRequestId(newReq.id);
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.detail || err.message || 'Failed to submit request.');
    },
  });

  const messageMutation = useMutation({
    mutationFn: async () => {
      if (!selectedRequestId || !replyMessage.trim()) return;
      return addAdminRequestMessage(selectedRequestId, replyMessage.trim());
    },
    onSuccess: () => {
      setReplyMessage('');
      queryClient.invalidateQueries({ queryKey: ['admin', 'curriculum-requests'] });
    },
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ── Top Header ──────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Inbox className="w-5 h-5 text-indigo-600" />
            Curriculum Correction & Discrepancy Tickets
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Submit formal discrepancy requests to the Super Administrator regarding syllabus hours, missing courses, or credits.
          </p>
        </div>

        <button
          onClick={() => {
            setTitle('');
            setDescription('');
            setFormError(null);
            setIsCreateOpen(true);
          }}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded-xl shadow-sm transition-all flex items-center gap-2 self-start"
        >
          <Plus className="w-4 h-4" /> New Correction Request
        </button>
      </div>

      {/* ── Split Layout: Requests List + Thread ─────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left: Requests List */}
        <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden divide-y divide-slate-100">
          <div className="p-4 bg-slate-50 font-bold text-xs text-slate-700 uppercase tracking-wider">
            Department Tickets ({(requests || []).length})
          </div>

          {isLoading ? (
            <div className="p-8 text-center text-xs text-slate-400">Loading tickets...</div>
          ) : (requests || []).length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400 italic">No tickets filed yet.</div>
          ) : (
            (requests || []).map((req) => (
              <div
                key={req.id}
                onClick={() => setSelectedRequestId(req.id)}
                className={`p-4 cursor-pointer transition-colors ${
                  selectedRequestId === req.id
                    ? 'bg-indigo-50/70 border-l-4 border-indigo-600'
                    : 'hover:bg-slate-50/60'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-indigo-900">{req.request_number}</span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                    req.status === 'RESOLVED'
                      ? 'bg-emerald-100 text-emerald-800'
                      : req.status === 'OPEN'
                      ? 'bg-amber-100 text-amber-800'
                      : 'bg-slate-100 text-slate-700'
                  }`}>
                    {req.status}
                  </span>
                </div>
                <h4 className="text-xs font-bold text-slate-900 mt-1.5">{req.title}</h4>
                <p className="text-[11px] text-slate-500 mt-0.5 line-clamp-1">{req.description}</p>
                <div className="text-[10px] text-slate-400 mt-2">
                  {new Date(req.created_at).toLocaleDateString()} • {req.messages.length} messages
                </div>
              </div>
            ))
          )}
        </div>

        {/* Right: Conversation Thread */}
        <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex flex-col min-h-[500px]">
          {!selectedRequest ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 text-slate-400 text-xs">
              <MessageSquare className="w-8 h-8 text-slate-300 mb-2" />
              Select a ticket from the list to view the conversation with the Super Administrator.
            </div>
          ) : (
            <div className="flex-1 flex flex-col">
              <div className="p-5 border-b border-slate-100 bg-slate-50/50">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-sm text-indigo-900">{selectedRequest.request_number}</span>
                  <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                    selectedRequest.status === 'RESOLVED'
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-amber-100 text-amber-800'
                  }`}>
                    {selectedRequest.status}
                  </span>
                </div>
                <h3 className="text-sm font-bold text-slate-900 mt-2">{selectedRequest.title}</h3>
                <p className="text-xs text-slate-600 mt-1">{selectedRequest.description}</p>
                {selectedRequest.resolution_notes && (
                  <div className="mt-3 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900 text-xs">
                    <strong>Resolution from Super Admin:</strong> {selectedRequest.resolution_notes}
                  </div>
                )}
              </div>

              {/* Messages */}
              <div className="flex-1 p-5 space-y-3 overflow-y-auto max-h-[350px] bg-slate-50/30">
                {selectedRequest.messages.map((msg) => {
                  const isSuperAdmin = msg.sender_role === 'SUPER_ADMIN';
                  return (
                    <div
                      key={msg.id}
                      className={`flex flex-col max-w-[85%] ${
                        !isSuperAdmin ? 'ml-auto items-end' : 'mr-auto items-start'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1 text-[11px]">
                        <span className="font-bold text-slate-800">{msg.sender_name}</span>
                        <span className="text-[10px] text-slate-400">({msg.sender_role})</span>
                        <span className="text-[10px] text-slate-400">
                          {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                      <div
                        className={`p-3 rounded-2xl text-xs leading-relaxed ${
                          !isSuperAdmin
                            ? 'bg-indigo-600 text-white rounded-br-none shadow-sm'
                            : 'bg-white text-slate-800 border border-slate-200 rounded-bl-none shadow-sm'
                        }`}
                      >
                        {msg.message}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Reply Input */}
              {selectedRequest.status !== 'RESOLVED' && selectedRequest.status !== 'REJECTED' && (
                <div className="p-4 border-t border-slate-100 bg-white flex items-center gap-2">
                  <input
                    type="text"
                    placeholder="Type a response to the Super Administrator..."
                    value={replyMessage}
                    onChange={(e) => setReplyMessage(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        messageMutation.mutate();
                      }
                    }}
                    className="flex-1 text-xs px-3.5 py-2.5 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                  <button
                    onClick={() => messageMutation.mutate()}
                    disabled={messageMutation.isPending || !replyMessage.trim()}
                    className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 disabled:opacity-50"
                  >
                    <Send className="w-3.5 h-3.5" /> Send
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Create Modal ────────────────────────────────────────────── */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-100 space-y-4">
            <h3 className="text-base font-bold text-slate-900">
              Submit Curriculum Discrepancy Ticket
            </h3>

            {formError && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs">
                {formError}
              </div>
            )}

            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Issue Category *</label>
                <select
                  value={requestType}
                  onChange={(e) => setRequestType(e.target.value)}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
                >
                  <option value="MISSING_SUBJECT">Missing Subject in Semester</option>
                  <option value="INCORRECT_CREDITS">Incorrect Subject Credits</option>
                  <option value="INCORRECT_HOURS">Discrepancy in L-T-P Hours</option>
                  <option value="MISSING_LAB">Missing Laboratory Practical Requirement</option>
                  <option value="INCORRECT_CODE">Wrong Course / Subject Code</option>
                  <option value="REVISED_SYLLABUS">Revised BoS Syllabus</option>
                  <option value="OTHER">Other Academic Concern</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Subject / Title *</label>
                <input
                  type="text"
                  placeholder="e.g. CS301 Practical Hours Discrepancy"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Detailed Explanation & Reference *</label>
                <textarea
                  rows={4}
                  placeholder="Detail the issue, reference BoS minutes or curriculum notification, and state the expected correction..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setIsCreateOpen(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => createMutation.mutate()}
                disabled={createMutation.isPending}
                className="px-4 py-2 text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl shadow-sm transition-all disabled:opacity-50"
              >
                {createMutation.isPending ? 'Submitting...' : 'Submit to Super Admin'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
