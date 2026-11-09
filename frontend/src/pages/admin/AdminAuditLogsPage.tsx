/**
 * frontend/src/pages/admin/AdminAuditLogsPage.tsx
 * ------------------------------------------------
 * Administrative Governance Audit Trail.
 * Displays all system actions with truthful persistence, filtering,
 * historical vs active record distinction, and explicit data refresh.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ShieldCheck, History, CheckCircle, Search } from 'lucide-react';
import { getAuditLogs } from '@/api/workflows';
import { PageHeader, RefreshButton } from '@/components/common';

export function AdminAuditLogsPage() {
  const [action, setAction] = useState('');
  const [entityType, setEntityType] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'ACTIVE' | 'HISTORICAL_CLEARED'>('ALL');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin', 'audit-logs', action, entityType, statusFilter],
    queryFn: () =>
      getAuditLogs({
        action: action.trim() || undefined,
        entity_type: entityType.trim() || undefined,
        lifecycle_status: statusFilter === 'ALL' ? undefined : statusFilter,
        limit: 100,
      }),
    staleTime: 10_000,
  });

  return (
    <div className="max-w-7xl mx-auto space-y-5 pb-8">
      <PageHeader
        title="Audit Logs"
        subtitle="Immutable administrative record of campus operations, timetable publishing, and data resets."
        icon={<ShieldCheck className="w-5 h-5 text-primary-600" />}
        actions={
          <RefreshButton
            entityName="Audit Trail"
            queryKeys={[['admin', 'audit-logs', action, entityType, statusFilter]]}
            label="Refresh Logs"
            variant="outline"
          />
        }
      />

      {/* Filter Toolbar */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-2xs">
        <div className="relative min-w-[200px] flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={action}
            onChange={(e) => setAction(e.target.value)}
            placeholder="Filter by action (e.g. CLEAR, PUBLISH)..."
            className="w-full rounded-lg border border-slate-200 pl-9 pr-3 py-2 text-xs focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 focus:outline-hidden"
          />
        </div>

        <input
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
          placeholder="Filter by entity (e.g. Timetable, DATA_MANAGEMENT)..."
          className="rounded-lg border border-slate-200 px-3 py-2 text-xs min-w-[180px] focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 focus:outline-hidden"
        />

        <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg border border-slate-200 text-xs font-medium">
          <button
            type="button"
            onClick={() => setStatusFilter('ALL')}
            className={`px-3 py-1.5 rounded-md transition-all ${
              statusFilter === 'ALL'
                ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            All Logs
          </button>
          <button
            type="button"
            onClick={() => setStatusFilter('ACTIVE')}
            className={`px-3 py-1.5 rounded-md transition-all ${
              statusFilter === 'ACTIVE'
                ? 'bg-white text-emerald-800 shadow-2xs font-semibold'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Active Only
          </button>
          <button
            type="button"
            onClick={() => setStatusFilter('HISTORICAL_CLEARED')}
            className={`px-3 py-1.5 rounded-md transition-all ${
              statusFilter === 'HISTORICAL_CLEARED'
                ? 'bg-white text-amber-800 shadow-2xs font-semibold'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Historical / Cleared
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="p-8 text-center text-sm text-slate-500 bg-white rounded-xl border border-slate-200">
          Loading governance audit events…
        </div>
      )}

      {isError && (
        <div role="alert" className="p-4 bg-rose-50 border border-rose-200 text-rose-700 text-sm rounded-xl">
          Could not load audit logs. Please verify connection and admin permissions.
        </div>
      )}

      {data && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-subtle">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
                <tr>
                  <th className="p-3.5">Log ID / Time</th>
                  <th className="p-3.5">Actor</th>
                  <th className="p-3.5">Action</th>
                  <th className="p-3.5">Entity</th>
                  <th className="p-3.5">Lifecycle State</th>
                  <th className="p-3.5">Audit Payload</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-normal">
                {data.items.map((row) => {
                  const isHistorical =
                    row.is_historical ||
                    row.lifecycle_status === 'HISTORICAL_CLEARED' ||
                    ((row.new_value as any)?.lifecycle_status === 'HISTORICAL_CLEARED');

                  return (
                    <tr key={row.id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="whitespace-nowrap p-3.5 text-slate-700">
                        <span className="font-mono text-slate-400 font-semibold mr-2">#{row.id}</span>
                        <span className="font-tabular">{new Date(row.timestamp).toLocaleString()}</span>
                      </td>
                      <td className="p-3.5">
                        <span className="inline-flex items-center px-2 py-0.5 rounded font-mono text-[11px] bg-slate-100 text-slate-800 border border-slate-200">
                          {row.user_id ? `User #${row.user_id}` : 'System'}
                        </span>
                      </td>
                      <td className="p-3.5 font-bold text-slate-900">
                        {(row.action || '—').replace(/_/g, ' ')}
                      </td>
                      <td className="p-3.5 text-slate-700">
                        <span className="font-medium">{row.entity_type || '—'}</span>{' '}
                        {row.entity_id ? (
                          <span className="font-mono text-slate-500 font-medium">#{row.entity_id}</span>
                        ) : (
                          ''
                        )}
                      </td>
                      <td className="p-3.5">
                        {isHistorical ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                            <History size={11} className="shrink-0" />
                            Historical / Cleared
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                            <CheckCircle size={11} className="shrink-0" />
                            Active Record
                          </span>
                        )}
                      </td>
                      <td className="max-w-xs sm:max-w-md p-3.5">
                        <details className="cursor-pointer">
                          <summary className="text-primary-700 font-semibold hover:underline">
                            View Snapshot
                          </summary>
                          <pre className="mt-2 max-h-48 overflow-y-auto rounded-lg bg-slate-900 p-3 text-[11px] text-slate-100 font-mono">
                            {JSON.stringify({ old: row.old_value, new: row.new_value }, null, 2)}
                          </pre>
                        </details>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {data.items.length === 0 && (
            <div className="p-12 text-center text-sm text-slate-500">
              No audit events found matching the specified filters.
            </div>
          )}

          <div className="border-t border-slate-200 px-4 py-3 text-xs text-slate-500 flex items-center justify-between">
            <span>
              Showing {data.items.length} of {data.total} recorded events
            </span>
            <span className="font-medium text-slate-400">Governance Audit Trail</span>
          </div>
        </div>
      )}
    </div>
  );
}
