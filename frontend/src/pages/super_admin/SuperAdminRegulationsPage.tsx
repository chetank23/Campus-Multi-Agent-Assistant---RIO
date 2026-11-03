/**
 * pages/super_admin/SuperAdminRegulationsPage.tsx
 * -----------------------------------------------
 * Academic Schemes and Regulations Management.
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Award, Plus, Edit2, Search, CheckCircle2, XCircle } from 'lucide-react';
import { getRegulations, createRegulation, updateRegulation, type Regulation } from '@/api/curriculum';
import { LoadingState } from '@/components/common';

export const SuperAdminRegulationsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingReg, setEditingReg] = useState<Regulation | null>(null);

  // Form state
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [effectiveYear, setEffectiveYear] = useState<number>(new Date().getFullYear());
  const [description, setDescription] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const { data: regulations, isLoading } = useQuery({
    queryKey: ['super-admin', 'regulations'],
    queryFn: () => getRegulations(),
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!code.trim() || !name.trim()) {
        throw new Error('Code and Name are mandatory.');
      }
      if (editingReg) {
        return updateRegulation(editingReg.id, {
          code: code.trim().toUpperCase(),
          name: name.trim(),
          effective_year: Number(effectiveYear),
          description: description.trim(),
        });
      } else {
        return createRegulation({
          code: code.trim().toUpperCase(),
          name: name.trim(),
          effective_year: Number(effectiveYear),
          description: description.trim(),
          is_active: true,
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'regulations'] });
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'dashboard-stats'] });
      closeModal();
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.detail || err.message || 'Failed to save regulation.');
    },
  });

  const openCreateModal = () => {
    setEditingReg(null);
    setCode('');
    setName('');
    setEffectiveYear(new Date().getFullYear());
    setDescription('');
    setFormError(null);
    setIsModalOpen(true);
  };

  const openEditModal = (reg: Regulation) => {
    setEditingReg(reg);
    setCode(reg.code);
    setName(reg.name);
    setEffectiveYear(reg.effective_year);
    setDescription(reg.description || '');
    setFormError(null);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingReg(null);
    setFormError(null);
  };

  const filteredRegulations = (regulations || []).filter(
    (r) =>
      r.code.toLowerCase().includes(searchTerm.toLowerCase()) ||
      r.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ── Header ───────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Award className="w-5 h-5 text-indigo-600" />
            Institutional Academic Regulations
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Standard institutional academic schemes (e.g. R2023, R2026) governing curriculum versions and cohorts.
          </p>
        </div>

        <button
          onClick={openCreateModal}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs rounded-xl shadow-sm transition-all flex items-center gap-2 self-start"
        >
          <Plus className="w-4 h-4" />
          New Academic Regulation
        </button>
      </div>

      {/* ── Search Bar ──────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
        <Search className="w-4 h-4 text-slate-400 ml-1" />
        <input
          type="text"
          placeholder="Filter regulations by code (e.g. R2026) or name..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full text-xs bg-transparent border-0 focus:outline-none focus:ring-0 text-slate-800"
        />
      </div>

      {/* ── Table ────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="py-12 flex justify-center">
            <LoadingState message="Loading academic schemes..." />
          </div>
        ) : filteredRegulations.length === 0 ? (
          <div className="py-12 text-center text-slate-500 text-xs">
            No regulations found matching your criteria.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50/80 text-slate-700 uppercase font-bold text-[10px] tracking-wider border-b border-slate-200">
                <tr>
                  <th className="px-5 py-3">Regulation Code</th>
                  <th className="px-5 py-3">Title / Scheme Name</th>
                  <th className="px-5 py-3">Effective Year</th>
                  <th className="px-5 py-3">Cohorts</th>
                  <th className="px-5 py-3">Curricula</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {filteredRegulations.map((reg) => (
                  <tr key={reg.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-5 py-3.5 font-bold font-mono text-indigo-900">{reg.code}</td>
                    <td className="px-5 py-3.5 text-slate-900">{reg.name}</td>
                    <td className="px-5 py-3.5">{reg.effective_year}</td>
                    <td className="px-5 py-3.5">{reg.cohorts_count}</td>
                    <td className="px-5 py-3.5">{reg.curriculum_versions_count}</td>
                    <td className="px-5 py-3.5">
                      {reg.is_active ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <CheckCircle2 className="w-3 h-3" /> ACTIVE
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                          <XCircle className="w-3 h-3" /> INACTIVE
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <button
                        onClick={() => openEditModal(reg)}
                        className="p-1.5 rounded-lg text-slate-500 hover:text-indigo-600 hover:bg-slate-100 transition-colors"
                        title="Edit Regulation"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Modal Dialog ────────────────────────────────────────────── */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-100 space-y-4">
            <h3 className="text-base font-bold text-slate-900">
              {editingReg ? 'Edit Academic Regulation' : 'Create New Academic Regulation'}
            </h3>

            {formError && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs">
                {formError}
              </div>
            )}

            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  Regulation Code (Unique) *
                </label>
                <input
                  type="text"
                  placeholder="e.g. R2026"
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  Full Scheme Name *
                </label>
                <input
                  type="text"
                  placeholder="e.g. Academic Regulation 2026 Autonomous"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  Effective Year *
                </label>
                <input
                  type="number"
                  value={effectiveYear}
                  onChange={(e) => setEffectiveYear(Number(e.target.value))}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">
                  Description / Notes
                </label>
                <textarea
                  rows={3}
                  placeholder="Academic guidelines, revision notes, BoS approvals..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
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
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className="px-4 py-2 text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl shadow-sm transition-all disabled:opacity-50"
              >
                {saveMutation.isPending ? 'Saving...' : editingReg ? 'Update Regulation' : 'Create Regulation'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
