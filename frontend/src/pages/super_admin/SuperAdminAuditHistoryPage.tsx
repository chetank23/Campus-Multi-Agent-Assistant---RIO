/**
 * pages/super_admin/SuperAdminAuditHistoryPage.tsx
 * ------------------------------------------------
 * Institutional Curriculum Audit Trail & Governance Log.
 */

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { ShieldCheck, Search, RefreshCw } from 'lucide-react';
import { apiClient } from '@/api/client';
import { LoadingState } from '@/components/common';

export const SuperAdminAuditHistoryPage: React.FC = () => {
  const [searchTerm, setSearchTerm] = React.useState('');

  const { data: auditLogs, isLoading, refetch } = useQuery({
    queryKey: ['super-admin', 'audit-history'],
    queryFn: async () => {
      const { data } = await apiClient.get<any[]>('/audit-logs');
      return data;
    },
    refetchInterval: 15_000,
  });

  const filteredLogs = (auditLogs || []).filter(
    (log: any) =>
      (log.action && log.action.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (log.entity_type && log.entity_type.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (log.user_name && log.user_name.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ── Top Header ──────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-indigo-600" />
            Curriculum Governance & Academic Audit Trail
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Immutable log of all academic regulation changes, curriculum publications, approvals, and allocation events.
          </p>
        </div>

        <button
          onClick={() => refetch()}
          className="px-3.5 py-1.5 bg-white border border-slate-200 text-slate-700 text-xs font-semibold rounded-xl hover:bg-slate-50 flex items-center gap-1.5 transition-colors self-start"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh Log
        </button>
      </div>

      {/* ── Search Bar ──────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
        <Search className="w-4 h-4 text-slate-400 ml-1" />
        <input
          type="text"
          placeholder="Filter audit events by action (e.g. PUBLISH_CURRICULUM), entity, or user..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full text-xs bg-transparent border-0 focus:outline-none focus:ring-0 text-slate-800"
        />
      </div>

      {/* ── Audit Logs Table ────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="py-12 flex justify-center">
            <LoadingState message="Loading governance audit log..." />
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="py-12 text-center text-slate-500 text-xs">
            No audit records found matching your search.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50/80 text-slate-700 uppercase font-bold text-[10px] tracking-wider border-b border-slate-200">
                <tr>
                  <th className="px-5 py-3">Timestamp</th>
                  <th className="px-5 py-3">Action</th>
                  <th className="px-5 py-3">Entity Type</th>
                  <th className="px-5 py-3">Entity ID</th>
                  <th className="px-5 py-3">Author</th>
                  <th className="px-5 py-3">Details / Snapshot</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {filteredLogs.map((log: any) => (
                  <tr key={log.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-5 py-3.5 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                      {new Date(log.timestamp).toLocaleString()}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="px-2 py-0.5 rounded font-mono text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-100">
                        {log.action}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 font-semibold text-slate-900">{log.entity_type}</td>
                    <td className="px-5 py-3.5 font-mono text-slate-600">#{log.entity_id}</td>
                    <td className="px-5 py-3.5">{log.user_name || log.user?.name || 'System'}</td>
                    <td className="px-5 py-3.5 font-mono text-[10px] text-slate-500 max-w-xs truncate">
                      {JSON.stringify(log.new_value || log.details || {})}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
