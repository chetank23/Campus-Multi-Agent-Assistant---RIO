import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Calendar, Plus, Clock, CheckCircle2, ArrowRight } from 'lucide-react';
import { getTimetableVersions } from '@/api/timetable';
import { PageHeader, StatusBadge, EmptyState, LoadingState, ErrorState, SearchBar } from '@/components/common';

export const AdminTimetableVersionsPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');

  const { data: versions, isLoading, isError, error } = useQuery({
    queryKey: ['timetable', 'versions'],
    queryFn: () => getTimetableVersions(),
  });

  const getStatusBadge = (status: string | null) => {
    switch (status) {
      case 'GENERATED':
        return <StatusBadge label="GENERATED" variant="info" size="sm" />;
      case 'REVIEWED':
        return <StatusBadge label="REVIEWED" variant="warning" size="sm" />;
      case 'VALIDATED':
        return <StatusBadge label="VALIDATED" variant="success" size="sm" />;
      case 'FINALIZED':
        return <StatusBadge label="FINALIZED" variant="primary" size="sm" />;
      case 'PUBLISHED':
        return <StatusBadge label="PUBLISHED" variant="success" size="sm" dot />;
      default:
        return <StatusBadge label={status || 'DRAFT'} variant="neutral" size="sm" />;
    }
  };

  const filteredVersions = useMemo(() => {
    if (!versions) return [];
    const sorted = [...versions].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
    if (!searchQuery.trim()) return sorted;
    const q = searchQuery.toLowerCase().trim();
    return sorted.filter((v) =>
      `v${v.id}`.includes(q) ||
      `${v.id}`.includes(q) ||
      (v.status && v.status.toLowerCase().includes(q))
    );
  }, [versions, searchQuery]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Timetable Versions"
        subtitle="Manage academic timetable lifecycle states, solver optimization versions, and publication status."
        breadcrumbs={[
          { label: 'Admin', href: '/admin' },
          { label: 'Timetable', href: '/admin/timetable/versions' },
          { label: 'Versions' },
        ]}
        actions={
          <button
            onClick={() => navigate('/admin/timetable/generate')}
            className="academic-btn-primary inline-flex items-center gap-2"
          >
            <Plus size={16} />
            <span>Generate New Timetable</span>
          </button>
        }
      />

      {isLoading ? (
        <LoadingState message="Loading timetable versions and lifecycle records…" />
      ) : isError ? (
        <ErrorState
          title="Failed to Load Timetable Versions"
          message={error instanceof Error ? error.message : 'An unknown server error occurred while retrieving timetable versions.'}
        />
      ) : !versions || versions.length === 0 ? (
        <EmptyState
          icon={<Calendar size={24} className="text-primary-600" />}
          title="No Timetables Generated"
          description="There are no timetable versions saved in the system yet. Click the button below to start generating a new timetable."
          action={
            <button
              onClick={() => navigate('/admin/timetable/generate')}
              className="academic-btn-primary text-xs inline-flex items-center gap-1.5"
            >
              <Plus size={14} />
              <span>Generate First Timetable</span>
            </button>
          }
        />
      ) : (

        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <SearchBar
              value={searchQuery}
              onChange={setSearchQuery}
              placeholder="Search by version ID (e.g. V1) or status…"
              className="max-w-md w-full"
            />
            <div className="text-xs text-slate-500 font-medium">
              Showing {filteredVersions.length} of {versions.length} versions
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-50/75 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                    <th className="py-3 px-5">Version</th>
                    <th className="py-3 px-5">Lifecycle Status</th>
                    <th className="py-3 px-5">Created At</th>
                    <th className="py-3 px-5">Published At</th>
                    <th className="py-3 px-5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-xs">
                  {filteredVersions.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-10 text-center text-slate-500">
                        No timetable versions matched your search criteria.
                      </td>
                    </tr>
                  ) : (
                    filteredVersions.map((version) => (
                      <tr
                        key={version.id}
                        onClick={() => navigate(`/admin/timetable/versions/${version.id}`)}
                        className="hover:bg-slate-50/75 cursor-pointer transition-colors group"
                      >
                        <td className="py-4 px-5">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-bold text-sm text-primary-700 bg-primary-50 px-2 py-0.5 rounded-md border border-primary-200/60">
                              V{version.id}
                            </span>
                          </div>
                        </td>
                        <td className="py-4 px-5">
                          {getStatusBadge(version.status)}
                        </td>
                        <td className="py-4 px-5 text-slate-600">
                          <div className="flex items-center gap-1.5">
                            <Clock size={13} className="text-slate-400" />
                            <span>{new Date(version.created_at).toLocaleString()}</span>
                          </div>
                        </td>
                        <td className="py-4 px-5">
                          {version.published_at ? (
                            <div className="flex items-center gap-1.5 text-emerald-700 font-medium">
                              <CheckCircle2 size={13} className="text-emerald-500" />
                              <span>{new Date(version.published_at).toLocaleString()}</span>
                            </div>
                          ) : (
                            <span className="text-slate-400 italic">Not Published</span>
                          )}
                        </td>
                        <td className="py-4 px-5 text-right">
                          <div className="inline-flex items-center gap-1 text-primary-600 group-hover:text-primary-800 font-semibold transition-colors">
                            <span>Review</span>
                            <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
