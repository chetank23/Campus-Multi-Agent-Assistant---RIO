/**
 * pages/super_admin/SuperAdminCurriculumVersionsPage.tsx
 * -----------------------------------------------------
 * Curriculum Versions Catalog and Governance Lifecycle.
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  BookOpen,
  Plus,
  GitBranch,
  CheckCircle2,
  Clock,
  Search,
  Filter,
  Eye,
  Send,
  FileCheck,
} from 'lucide-react';
import {
  getCurriculumVersions,
  createCurriculumVersion,
  publishCurriculumVersion,
  reviseCurriculumVersion,
  getRegulations,
  getCohorts,
} from '@/api/curriculum';
import { apiClient } from '@/api/client';
import { LoadingState } from '@/components/common';

export const SuperAdminCurriculumVersionsPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  // Create Form State
  const [departmentId, setDepartmentId] = useState<number | ''>('');
  const [programId, setProgramId] = useState<number | ''>('');
  const [regulationId, setRegulationId] = useState<number | ''>('');
  const [cohortId, setCohortId] = useState<number | ''>('');
  const [description, setDescription] = useState('');
  const [totalSemesters, setTotalSemesters] = useState<number>(8);
  const [formError, setFormError] = useState<string | null>(null);

  const { data: versions, isLoading } = useQuery({
    queryKey: ['super-admin', 'curriculum-versions', statusFilter],
    queryFn: () => getCurriculumVersions({ status: statusFilter || undefined }),
  });

  const { data: departments } = useQuery({
    queryKey: ['departments'],
    queryFn: async () => {
      const { data } = await apiClient.get<any[]>('/departments');
      return data;
    },
  });

  const { data: programs } = useQuery({
    queryKey: ['programs', departmentId],
    queryFn: async () => {
      const { data } = await apiClient.get<any[]>('/programs');
      return departmentId ? data.filter((p) => p.department_id === departmentId) : data;
    },
  });

  const { data: regulations } = useQuery({
    queryKey: ['super-admin', 'regulations'],
    queryFn: () => getRegulations(),
  });

  const { data: cohorts } = useQuery({
    queryKey: ['super-admin', 'cohorts', programId],
    queryFn: () => getCohorts(programId ? Number(programId) : undefined),
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!departmentId || !programId || !regulationId) {
        throw new Error('Department, Program, and Regulation are required.');
      }
      return createCurriculumVersion({
        department_id: Number(departmentId),
        program_id: Number(programId),
        regulation_id: Number(regulationId),
        cohort_id: cohortId ? Number(cohortId) : null,
        description: description.trim(),
        total_semesters: Number(totalSemesters),
      });
    },
    onSuccess: (newVersion) => {
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'curriculum-versions'] });
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'dashboard-stats'] });
      setIsCreateOpen(false);
      navigate(`/super-admin/curriculum-versions/${newVersion.id}`);
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.detail || err.message || 'Failed to create curriculum.');
    },
  });

  const reviseMutation = useMutation({
    mutationFn: async (versionId: number) => reviseCurriculumVersion(versionId),
    onSuccess: (revised) => {
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'curriculum-versions'] });
      navigate(`/super-admin/curriculum-versions/${revised.id}`);
    },
  });

  const publishMutation = useMutation({
    mutationFn: async (versionId: number) => publishCurriculumVersion(versionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'curriculum-versions'] });
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'dashboard-stats'] });
    },
  });

  const filteredVersions = (versions || []).filter(
    (v) =>
      v.version_code.toLowerCase().includes(searchTerm.toLowerCase()) ||
      v.department_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      v.program_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      v.regulation_code.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'PUBLISHED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
            <CheckCircle2 className="w-3 h-3" /> PUBLISHED
          </span>
        );
      case 'APPROVED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 border border-blue-300">
            <FileCheck className="w-3 h-3" /> APPROVED
          </span>
        );
      case 'NEEDS_REVIEW':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
            <Clock className="w-3 h-3" /> IN REVIEW
          </span>
        );
      case 'DRAFT':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-300">
            DRAFT
          </span>
        );
      case 'SUPERSEDED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 text-purple-700 border border-purple-200">
            SUPERSEDED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ── Top Header ──────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-indigo-600" />
            Central Curriculum Versions
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Governed academic curricula with semester subject allocations, credits, and timetable synchronization.
          </p>
        </div>

        <button
          onClick={() => {
            setDepartmentId(departments?.[0]?.id || '');
            setProgramId(programs?.[0]?.id || '');
            setRegulationId(regulations?.[0]?.id || '');
            setCohortId(cohorts?.[0]?.id || '');
            setDescription('');
            setFormError(null);
            setIsCreateOpen(true);
          }}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs rounded-xl shadow-sm transition-all flex items-center gap-2 self-start"
        >
          <Plus className="w-4 h-4" />
          Draft New Curriculum
        </button>
      </div>

      {/* ── Filter & Search Toolbar ──────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-center gap-3 bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex-1 flex items-center gap-2 w-full">
          <Search className="w-4 h-4 text-slate-400 ml-1" />
          <input
            type="text"
            placeholder="Search by version code (e.g. CURR-CSE-R2026-V1), department, or regulation..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full text-xs bg-transparent border-0 focus:outline-none focus:ring-0 text-slate-800"
          />
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">All Statuses</option>
            <option value="DRAFT">Draft</option>
            <option value="NEEDS_REVIEW">Needs Review</option>
            <option value="APPROVED">Approved</option>
            <option value="PUBLISHED">Published</option>
            <option value="SUPERSEDED">Superseded</option>
          </select>
        </div>
      </div>

      {/* ── Curriculum Table ─────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="py-12 flex justify-center">
            <LoadingState message="Loading curriculum versions..." />
          </div>
        ) : filteredVersions.length === 0 ? (
          <div className="py-12 text-center text-slate-500 text-xs">
            No curriculum versions found.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50/80 text-slate-700 uppercase font-bold text-[10px] tracking-wider border-b border-slate-200">
                <tr>
                  <th className="px-5 py-3">Version Code</th>
                  <th className="px-5 py-3">Department & Program</th>
                  <th className="px-5 py-3">Regulation</th>
                  <th className="px-5 py-3">Cohort</th>
                  <th className="px-5 py-3">Credits</th>
                  <th className="px-5 py-3">Semesters</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {filteredVersions.map((v) => (
                  <tr key={v.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-5 py-3.5">
                      <button
                        onClick={() => navigate(`/super-admin/curriculum-versions/${v.id}`)}
                        className="font-bold font-mono text-indigo-900 hover:text-indigo-600 hover:underline flex items-center gap-1.5"
                      >
                        {v.version_code}
                      </button>
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="text-slate-900 font-semibold">{v.program_name}</div>
                      <div className="text-[11px] text-slate-400">{v.department_name}</div>
                    </td>
                    <td className="px-5 py-3.5 font-mono font-semibold text-indigo-700">{v.regulation_code}</td>
                    <td className="px-5 py-3.5">{v.cohort_name || 'All Cohorts'}</td>
                    <td className="px-5 py-3.5 font-bold text-slate-800">{v.total_credits} cr</td>
                    <td className="px-5 py-3.5">{v.total_semesters} sem</td>
                    <td className="px-5 py-3.5">{getStatusBadge(v.status)}</td>
                    <td className="px-5 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => navigate(`/super-admin/curriculum-versions/${v.id}`)}
                          className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1"
                          title="Open Workspace"
                        >
                          <Eye className="w-3 h-3" /> Open
                        </button>

                        {v.status === 'APPROVED' && (
                          <button
                            onClick={() => publishMutation.mutate(v.id)}
                            disabled={publishMutation.isPending}
                            className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold transition-colors flex items-center gap-1"
                            title="Publish to Department"
                          >
                            <Send className="w-3 h-3" /> Publish
                          </button>
                        )}

                        {v.status === 'PUBLISHED' && (
                          <button
                            onClick={() => reviseMutation.mutate(v.id)}
                            disabled={reviseMutation.isPending}
                            className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1"
                            title="Create Revision"
                          >
                            <GitBranch className="w-3 h-3" /> Revise
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Create Modal ────────────────────────────────────────────── */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-100 space-y-4">
            <h3 className="text-base font-bold text-slate-900">Draft New Institutional Curriculum</h3>

            {formError && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs">
                {formError}
              </div>
            )}

            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Academic Department *</label>
                <select
                  value={departmentId}
                  onChange={(e) => setDepartmentId(Number(e.target.value))}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
                >
                  <option value="">Select Department...</option>
                  {(departments || []).map((d: any) => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Degree Program *</label>
                <select
                  value={programId}
                  onChange={(e) => setProgramId(Number(e.target.value))}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
                >
                  <option value="">Select Degree Program...</option>
                  {(programs || []).map((p: any) => (
                    <option key={p.id} value={p.id}>{p.program_name}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Academic Regulation *</label>
                  <select
                    value={regulationId}
                    onChange={(e) => setRegulationId(Number(e.target.value))}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
                  >
                    <option value="">Select Regulation...</option>
                    {(regulations || []).map((r) => (
                      <option key={r.id} value={r.id}>{r.code}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Cohort (Optional)</label>
                  <select
                    value={cohortId}
                    onChange={(e) => setCohortId(e.target.value ? Number(e.target.value) : '')}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
                  >
                    <option value="">All Cohorts</option>
                    {(cohorts || []).map((c) => (
                      <option key={c.id} value={c.id}>{c.cohort_name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Total Semesters</label>
                <input
                  type="number"
                  min={1}
                  max={12}
                  value={totalSemesters}
                  onChange={(e) => setTotalSemesters(Number(e.target.value))}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Curriculum Notes / Description</label>
                <textarea
                  rows={2}
                  placeholder="e.g. Outcome-Based Education, Choice Based Credit System (CBCS)..."
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
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => createMutation.mutate()}
                disabled={createMutation.isPending}
                className="px-4 py-2 text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl shadow-sm transition-all disabled:opacity-50"
              >
                {createMutation.isPending ? 'Creating...' : 'Draft Curriculum'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
