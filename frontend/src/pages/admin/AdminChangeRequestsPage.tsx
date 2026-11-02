import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, X, RefreshCw } from 'lucide-react';
import { getPendingChangeRequests, reviewChangeRequest } from '@/api/workflows';

export function AdminChangeRequestsPage() {
  const qc = useQueryClient();
  const [notes, setNotes] = useState<Record<number, string>>({});
  const { data = [], isLoading, isError } = useQuery({ queryKey: ['admin', 'change-requests'], queryFn: () => getPendingChangeRequests(), refetchInterval: 30000 });
  const mutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: 'APPROVED' | 'REJECTED' }) => reviewChangeRequest(id, status, notes[id]?.trim() || undefined),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'change-requests'] }),
  });
  return <div className="max-w-6xl mx-auto space-y-5">
    <header><h1 className="text-2xl font-bold text-slate-900">Change Requests</h1><p className="text-sm text-slate-500 mt-1">Review and decide pending campus requests.</p></header>
    {isLoading && <p className="text-sm text-slate-500">Loading requests…</p>}
    {isError && <p role="alert" className="text-sm text-red-600">Could not load requests. Check your connection and permissions.</p>}
    {!isLoading && !isError && data.length === 0 && <div className="rounded-xl border bg-white p-10 text-center text-sm text-slate-500">No pending requests.</div>}
    <div className="space-y-3">{data.map((item) => <article key={item.id} className="rounded-xl border border-slate-200 bg-white p-5 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2"><div><p className="font-semibold text-slate-900">{(item.request_type || 'REQUEST').replaceAll('_', ' ')}</p><p className="text-xs text-slate-500 mt-1">Request #{item.id} · User {item.requested_by ?? 'Unknown'} · {new Date(item.created_at).toLocaleString()}</p></div><span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">{item.status}</span></div>
      <p className="text-sm text-slate-700 whitespace-pre-wrap">{item.reason || 'No reason supplied'}</p>
      {item.related_entity_id && <p className="text-xs text-slate-500">Related record: #{item.related_entity_id}</p>}
      <textarea aria-label={`Review note for request ${item.id}`} value={notes[item.id] || ''} onChange={(e) => setNotes((s) => ({ ...s, [item.id]: e.target.value }))} placeholder="Optional review note" rows={2} className="w-full rounded-lg border border-slate-200 p-3 text-sm" />
      <div className="flex justify-end gap-2"><button disabled={mutation.isPending} onClick={() => mutation.mutate({ id: item.id, status: 'REJECTED' })} className="inline-flex items-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700 disabled:opacity-50"><X size={15}/>Reject</button><button disabled={mutation.isPending} onClick={() => mutation.mutate({ id: item.id, status: 'APPROVED' })} className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"><Check size={15}/>Approve</button></div>
    </article>)}</div>
    {mutation.isError && <p role="alert" className="text-sm text-red-600">Review failed. Refresh and try again.</p>}
  </div>;
}
