/**
 * pages/super_admin/SuperAdminRequestsPage.tsx
 * --------------------------------------------
 * Super Admin Correction Requests Management & Threaded Discussions.
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Inbox,
  MessageSquare,
  Send,
  Filter,
} from 'lucide-react';
import {
  getSuperAdminRequests,
  getSuperAdminRequest,
  updateSuperAdminRequestStatus,
  addSuperAdminRequestMessage,
} from '@/api/curriculum';

export const SuperAdminRequestsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedRequestId, setSelectedRequestId] = useState<number | null>(null);
  const [replyMessage, setReplyMessage] = useState('');
  const [resolutionNotes, setResolutionNotes] = useState('');

  const { data: requests, isLoading } = useQuery({
    queryKey: ['super-admin', 'requests', statusFilter],
    queryFn: () => getSuperAdminRequests(statusFilter || undefined),
    refetchInterval: 10_000,
  });

  const { data: activeRequest } = useQuery({
    queryKey: ['super-admin', 'request', selectedRequestId],
    queryFn: () => (selectedRequestId ? getSuperAdminRequest(selectedRequestId) : null),
    enabled: selectedRequestId !== null,
    refetchInterval: 5_000,
  });

  const messageMutation = useMutation({
    mutationFn: async () => {
      if (!selectedRequestId || !replyMessage.trim()) return;
      return addSuperAdminRequestMessage(selectedRequestId, replyMessage.trim());
    },
    onSuccess: () => {
      setReplyMessage('');
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'request', selectedRequestId] });
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'requests'] });
    },
  });

  const statusMutation = useMutation({
    mutationFn: async (newStatus: string) => {
      if (!selectedRequestId) return;
      return updateSuperAdminRequestStatus(selectedRequestId, {
        status: newStatus,
        resolution_notes: resolutionNotes.trim() || undefined,
      });
    },
    onSuccess: () => {
      setResolutionNotes('');
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'request', selectedRequestId] });
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'requests'] });
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'dashboard-stats'] });
    },
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ── Top Header ──────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Inbox className="w-5 h-5 text-indigo-600" />
            Department Curriculum Correction Requests
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Review academic change requests submitted by department administrators and communicate resolutions.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="text-xs border border-slate-200 rounded-xl px-3 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">All Statuses</option>
            <option value="OPEN">Open</option>
            <option value="UNDER_REVIEW">Under Review</option>
            <option value="NEEDS_INFORMATION">Needs Information</option>
            <option value="RESOLVED">Resolved</option>
            <option value="REJECTED">Rejected</option>
          </select>
        </div>
      </div>

      {/* ── Split Layout: Requests List + Active Conversation Panel ──── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Request List */}
        <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden divide-y divide-slate-100">
          <div className="p-4 bg-slate-50/70 border-b border-slate-100 font-bold text-xs text-slate-700 uppercase tracking-wider">
            All Inbound Requests ({(requests || []).length})
          </div>

          {isLoading ? (
            <div className="p-8 text-center text-xs text-slate-400">Loading requests...</div>
          ) : (requests || []).length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400 italic">No correction requests found.</div>
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
                <div className="flex items-center justify-between text-[10px] text-slate-400 mt-2">
                  <span>{req.department_name}</span>
                  <span>{new Date(req.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Right Column: Detail & Thread Conversation */}
        <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex flex-col min-h-[550px]">
          {!activeRequest ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 text-slate-400 text-xs">
              <MessageSquare className="w-8 h-8 text-slate-300 mb-2" />
              Select a request from the left column to inspect details and respond.
            </div>
          ) : (
            <div className="flex-1 flex flex-col">
              {/* Header */}
              <div className="p-5 border-b border-slate-100 bg-slate-50/50">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-sm text-indigo-900">{activeRequest.request_number}</span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-100 text-indigo-800 uppercase">
                      {activeRequest.request_type}
                    </span>
                  </div>
                  <span className="text-xs font-semibold text-slate-500">
                    Status: <span className="font-bold text-slate-800">{activeRequest.status}</span>
                  </span>
                </div>
                <h3 className="text-sm font-bold text-slate-900 mt-2">{activeRequest.title}</h3>
                <p className="text-xs text-slate-600 mt-1">{activeRequest.description}</p>
                <div className="mt-3 flex items-center gap-4 text-[11px] text-slate-500">
                  <span>From: <strong className="text-slate-800">{activeRequest.requesting_admin_name}</strong></span>
                  <span>Department: <strong className="text-slate-800">{activeRequest.department_name}</strong></span>
                </div>
              </div>

              {/* Status Controls */}
              <div className="px-5 py-3 border-b border-slate-100 bg-white flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold text-slate-500 mr-2">Update Status:</span>
                <button
                  onClick={() => statusMutation.mutate('UNDER_REVIEW')}
                  className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200"
                >
                  Under Review
                </button>
                <button
                  onClick={() => statusMutation.mutate('NEEDS_INFORMATION')}
                  className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-sky-50 hover:bg-sky-100 text-sky-800 border border-sky-200"
                >
                  Needs Info
                </button>
                <button
                  onClick={() => statusMutation.mutate('RESOLVED')}
                  className="px-2.5 py-1 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white"
                >
                  Resolve
                </button>
                <button
                  onClick={() => statusMutation.mutate('REJECTED')}
                  className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-red-50 hover:bg-red-100 text-red-700 border border-red-200"
                >
                  Reject
                </button>
              </div>

              {/* Threaded Messages */}
              <div className="flex-1 p-5 space-y-3 overflow-y-auto max-h-[350px] bg-slate-50/30">
                {activeRequest.messages.map((msg) => {
                  const isSuperAdmin = msg.sender_role === 'SUPER_ADMIN';
                  return (
                    <div
                      key={msg.id}
                      className={`flex flex-col max-w-[85%] ${
                        isSuperAdmin ? 'ml-auto items-end' : 'mr-auto items-start'
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
                          isSuperAdmin
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

              {/* Reply Box */}
              <div className="p-4 border-t border-slate-100 bg-white flex items-center gap-2">
                <input
                  type="text"
                  placeholder="Type a response or resolution message to the department administrator..."
                  value={replyMessage}
                  onChange={(e) => setReplyMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
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
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
