import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getAuditLogs } from '@/api/workflows';

export function AdminAuditLogsPage() {
  const [action, setAction] = useState('');
  const [entityType, setEntityType] = useState('');
  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin', 'audit-logs', action, entityType],
    queryFn: () => getAuditLogs({ action: action.trim() || undefined, entity_type: entityType.trim() || undefined, limit: 100 }),
  });
  return <div className="max-w-7xl mx-auto space-y-5">
    <header><h1 className="text-2xl font-bold text-slate-900">Audit Logs</h1><p className="text-sm text-slate-500 mt-1">Administrative record of system actions and changes.</p></header>
    <div className="flex flex-wrap gap-3 rounded-xl border bg-white p-4"><input value={action} onChange={(e) => setAction(e.target.value)} placeholder="Filter action" className="rounded-lg border border-slate-200 px-3 py-2 text-sm"/><input value={entityType} onChange={(e) => setEntityType(e.target.value)} placeholder="Filter entity type" className="rounded-lg border border-slate-200 px-3 py-2 text-sm"/></div>
    {isLoading && <p className="text-sm text-slate-500">Loading audit events…</p>}
    {isError && <p role="alert" className="text-sm text-red-600">Could not load audit logs. Check your connection and permissions.</p>}
    {data && <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="p-3">Time</th><th className="p-3">User</th><th className="p-3">Action</th><th className="p-3">Entity</th><th className="p-3">Changes</th></tr></thead><tbody className="divide-y divide-slate-100">{data.items.map((row) => <tr key={row.id}><td className="whitespace-nowrap p-3 text-slate-600">{new Date(row.timestamp).toLocaleString()}</td><td className="p-3">{row.user_id ?? 'System'}</td><td className="p-3 font-medium">{row.action || '—'}</td><td className="p-3">{row.entity_type || '—'} {row.entity_id ? `#${row.entity_id}` : ''}</td><td className="max-w-md p-3"><details><summary className="cursor-pointer text-primary-700">View details</summary><pre className="mt-2 whitespace-pre-wrap break-words text-xs text-slate-600">{JSON.stringify({ old: row.old_value, new: row.new_value }, null, 2)}</pre></details></td></tr>)}</tbody></table>{data.items.length === 0 && <p className="p-8 text-center text-sm text-slate-500">No audit events match these filters.</p>}<p className="border-t p-3 text-xs text-slate-500">Showing {data.items.length} of {data.total} events</p></div>}
  </div>;
}
