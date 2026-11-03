/**
 * pages/super_admin/SuperAdminCohortsPage.tsx
 * -------------------------------------------
 * Student Admission Cohorts Management.
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Users2, Plus, Search, CheckCircle2, XCircle } from 'lucide-react';
import { getCohorts, createCohort, getRegulations } from '@/api/curriculum';
import { apiClient } from '@/api/client';
import { LoadingState } from '@/components/common';

export const SuperAdminCohortsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Form State
  const [cohortName, setCohortName] = useState('');
  const [startYear, setStartYear] = useState<number>(new Date().getFullYear());
  const [endYear, setEndYear] = useState<number>(new Date().getFullYear() + 4);
  const [programId, setProgramId] = useState<number | ''>('');
  const [regulationId, setRegulationId] = useState<number | ''>('');
  const [formError, setFormError] = useState<string | null>(null);

  const { data: cohorts, isLoading } = useQuery({
    queryKey: ['super-admin', 'cohorts'],
    queryFn: () => getCohorts(),
  });

  const { data: regulations } = useQuery({
    queryKey: ['super-admin', 'regulations'],
    queryFn: () => getRegulations(),
  });

  const { data: programs } = useQuery({
    queryKey: ['programs'],
    queryFn: async () => {
      const { data } = await apiClient.get<any[]>('/programs/');
      return data;
    },
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!cohortName.trim() || !programId || !regulationId) {
        throw new Error('All fields are required.');
      }
      if (Number(endYear) <= Number(startYear)) {
        throw new Error('End year must exceed start year.');
      }
      return createCohort({
        cohort_name: cohortName.trim(),
        start_year: Number(startYear),
        end_year: Number(endYear),
        program_id: Number(programId),
        regulation_id: Number(regulationId),
        is_active: true,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'cohorts'] });
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'dashboard-stats'] });
      closeModal();
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.detail || err.message || 'Failed to create cohort.');
    },
  });

  const openCreateModal = () => {
    setCohortName(`${new Date().getFullYear()}-${new Date().getFullYear() + 4}`);
    setStartYear(new Date().getFullYear());
    setEndYear(new Date().getFullYear() + 4);
    setProgramId(programs?.[0]?.id || '');
    setRegulationId(regulations?.[0]?.id || '');
    setFormError(null);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setFormError(null);
  };

  const filteredCohorts = (cohorts || []).filter(
    (c) =>
      c.cohort_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (c.program_name && c.program_name.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (c.regulation_code && c.regulation_code.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ── Header ───────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Users2 className="w-5 h-5 text-sky-600" />
            Program Admission Cohorts
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Student entry cohorts linked to degree programs and specific academic regulations.
          </p>
        </div>

        <button
          onClick={openCreateModal}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white font-semibold text-xs rounded-xl shadow-sm transition-all flex items-center gap-2 self-start"
        >
          <Plus className="w-4 h-4" />
          New Admission Cohort
        </button>
      </div>

      {/* ── Search Bar ──────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
        <Search className="w-4 h-4 text-slate-400 ml-1" />
        <input
          type="text"
          placeholder="Filter cohorts by name (e.g. 2024-2028), program, or regulation..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full text-xs bg-transparent border-0 focus:outline-none focus:ring-0 text-slate-800"
        />
      </div>

      {/* ── Table ────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="py-12 flex justify-center">
            <LoadingState message="Loading cohorts..." />
          </div>
        ) : filteredCohorts.length === 0 ? (
          <div className="py-12 text-center text-slate-500 text-xs">
            No admission cohorts found.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50/80 text-slate-700 uppercase font-bold text-[10px] tracking-wider border-b border-slate-200">
                <tr>
                  <th className="px-5 py-3">Cohort Name</th>
                  <th className="px-5 py-3">Degree Program</th>
                  <th className="px-5 py-3">Regulation Scheme</th>
                  <th className="px-5 py-3">Duration</th>
                  <th className="px-5 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {filteredCohorts.map((cohort) => (
                  <tr key={cohort.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-5 py-3.5 font-bold font-mono text-sky-900">{cohort.cohort_name}</td>
                    <td className="px-5 py-3.5 text-slate-900">{cohort.program_name || 'N/A'}</td>
                    <td className="px-5 py-3.5 font-mono font-semibold text-indigo-700">{cohort.regulation_code || 'N/A'}</td>
                    <td className="px-5 py-3.5">{cohort.start_year} – {cohort.end_year} ({cohort.end_year - cohort.start_year} yrs)</td>
                    <td className="px-5 py-3.5">
                      {cohort.is_active ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <CheckCircle2 className="w-3 h-3" /> ACTIVE
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                          <XCircle className="w-3 h-3" /> INACTIVE
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Create Modal ────────────────────────────────────────────── */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-100 space-y-4">
            <h3 className="text-base font-bold text-slate-900">Create New Admission Cohort</h3>

            {formError && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs">
                {formError}
              </div>
            )}

            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  Cohort Name (e.g. 2024-2028) *
                </label>
                <input
                  type="text"
                  value={cohortName}
                  onChange={(e) => setCohortName(e.target.value)}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-sky-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  Degree Program *
                </label>
                <select
                  value={programId}
                  onChange={(e) => setProgramId(Number(e.target.value))}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-sky-500 focus:outline-none bg-white"
                >
                  <option value="">Select Degree Program...</option>
                  {(programs || []).map((p: any) => (
                    <option key={p.id} value={p.id}>{p.program_name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  Academic Regulation Scheme *
                </label>
                <select
                  value={regulationId}
                  onChange={(e) => setRegulationId(Number(e.target.value))}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-sky-500 focus:outline-none bg-white"
                >
                  <option value="">Select Regulation Scheme...</option>
                  {(regulations || []).map((r) => (
                    <option key={r.id} value={r.id}>{r.code} - {r.name}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Start Year</label>
                  <input
                    type="number"
                    value={startYear}
                    onChange={(e) => setStartYear(Number(e.target.value))}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-sky-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">End Year</label>
                  <input
                    type="number"
                    value={endYear}
                    onChange={(e) => setEndYear(Number(e.target.value))}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-sky-500 focus:outline-none"
                  />
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={closeModal}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => createMutation.mutate()}
                disabled={createMutation.isPending}
                className="px-4 py-2 text-xs font-bold text-white bg-sky-600 hover:bg-sky-700 rounded-xl shadow-sm transition-all disabled:opacity-50"
              >
                {createMutation.isPending ? 'Creating...' : 'Create Cohort'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
