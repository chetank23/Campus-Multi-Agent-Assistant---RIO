/**
 * pages/admin/curriculum/AdminCurriculumReadinessPage.tsx
 * -------------------------------------------------------
 * Curriculum-to-Timetable Scheduling Preflight Verification Engine.
 */

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Play,
  ShieldCheck,
} from 'lucide-react';
import {
  getCurriculumReadiness,
} from '@/api/curriculum';
import { apiClient } from '@/api/client';
import { LoadingState } from '@/components/common';

export const AdminCurriculumReadinessPage: React.FC = () => {
  const navigate = useNavigate();

  const [versionId, setVersionId] = useState<number | ''>('');
  const [semesterNumber, setSemesterNumber] = useState<number>(1);
  const [academicYearId, setAcademicYearId] = useState<number | ''>('');
  const [semesterId, setSemesterId] = useState<number | ''>('');

  const { data: publishedVersions } = useQuery({
    queryKey: ['curriculum-versions', 'published'],
    queryFn: async () => {
      const { data } = await apiClient.get<any[]>('/admin/curriculum/versions', {
        params: { status: 'PUBLISHED' },
      });
      return data;
    },
  });

  const { data: academicYears } = useQuery({
    queryKey: ['academic-years'],
    queryFn: async () => {
      const { data } = await apiClient.get<any[]>('/academic-years/');
      return data;
    },
  });

  const effectiveVersionId = versionId !== '' ? versionId : (publishedVersions?.[0]?.id ?? '');
  const effectiveAcademicYearId = academicYearId !== '' ? academicYearId : (academicYears?.[0]?.id ?? '');

  const { data: semesters } = useQuery({
    queryKey: ['semesters', effectiveAcademicYearId],
    queryFn: async () => {
      const { data } = await apiClient.get<any[]>('/semesters/');
      return effectiveAcademicYearId ? data.filter((s) => s.academic_year_id === effectiveAcademicYearId) : data;
    },
  });

  const effectiveSemesterId = semesterId !== '' ? semesterId : (semesters?.[0]?.id ?? '');

  const { data: readiness, isLoading } = useQuery({
    queryKey: ['admin', 'curriculum-readiness', effectiveVersionId, semesterNumber, effectiveAcademicYearId, effectiveSemesterId],
    queryFn: () =>
      getCurriculumReadiness({
        curriculum_version_id: Number(effectiveVersionId),
        semester_number: Number(semesterNumber),
        academic_year_id: Number(effectiveAcademicYearId),
        semester_id: Number(effectiveSemesterId),
      }),
    enabled: Boolean(effectiveVersionId && effectiveAcademicYearId && effectiveSemesterId),
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ── Header ───────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-emerald-600" />
            Curriculum Timetable Scheduling Preflight Verification
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Automated verification ensuring all published curriculum courses have valid section offerings and allocated faculty before solving.
          </p>
        </div>

        {readiness?.is_ready_for_scheduling && (
          <button
            onClick={() => navigate('/admin/timetable/generate')}
            className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs rounded-xl shadow-md transition-all flex items-center gap-2 self-start animate-bounce"
          >
            <Play className="w-4 h-4 fill-current" />
            Launch Timetable Solver
          </button>
        )}
      </div>

      {/* ── Selection Strip ─────────────────────────────────────────── */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div>
          <label className="text-xs font-semibold text-slate-700 block mb-1">Published Curriculum *</label>
          <select
            value={effectiveVersionId}
            onChange={(e) => setVersionId(Number(e.target.value))}
            className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-emerald-500 focus:outline-none bg-white font-mono"
          >
            {(publishedVersions || []).map((v) => (
              <option key={v.id} value={v.id}>{v.version_code} ({v.program_name})</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-700 block mb-1">Curriculum Semester Number</label>
          <input
            type="number"
            min={1}
            max={8}
            value={semesterNumber}
            onChange={(e) => setSemesterNumber(Number(e.target.value))}
            className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-emerald-500 focus:outline-none font-bold"
          />
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-700 block mb-1">Academic Year</label>
          <select
            value={effectiveAcademicYearId}
            onChange={(e) => setAcademicYearId(Number(e.target.value))}
            className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-emerald-500 focus:outline-none bg-white"
          >
            {(academicYears || []).map((ay: any) => (
              <option key={ay.id} value={ay.id}>{ay.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-700 block mb-1">Academic Term / Semester</label>
          <select
            value={effectiveSemesterId}
            onChange={(e) => setSemesterId(Number(e.target.value))}
            className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-emerald-500 focus:outline-none bg-white"
          >
            {(semesters || []).map((sem: any) => (
              <option key={sem.id} value={sem.id}>{sem.name || `Semester ${sem.semester_number}`}</option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Preflight Evaluation Card ─────────────────────────────────── */}
      {isLoading ? (
        <div className="py-12 flex justify-center">
          <LoadingState message="Analyzing curriculum readiness..." />
        </div>
      ) : !readiness ? (
        <div className="p-8 text-center text-slate-400 text-xs bg-white rounded-2xl border border-slate-200">
          Select target curriculum version and semester to run preflight check.
        </div>
      ) : (
        <div className="space-y-6">
          {/* Readiness Gauge Banner */}
          <div className={`p-6 rounded-2xl border text-white shadow-md flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
            readiness.is_ready_for_scheduling
              ? 'bg-gradient-to-r from-emerald-600 to-teal-700 border-emerald-500'
              : 'bg-gradient-to-r from-amber-600 to-orange-700 border-amber-500'
          }`}>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                {readiness.is_ready_for_scheduling ? (
                  <CheckCircle2 className="w-6 h-6 text-emerald-200" />
                ) : (
                  <AlertTriangle className="w-6 h-6 text-amber-200 animate-pulse" />
                )}
                <h3 className="text-lg font-extrabold">
                  {readiness.is_ready_for_scheduling
                    ? '100% Ready for Timetable Generation'
                    : 'Action Required: Incomplete Offerings or Missing Faculty'}
                </h3>
              </div>
              <p className="text-xs text-white/90">
                {readiness.allocated_subjects} of {readiness.total_subjects} subjects fully allocated to faculty lecturers across all sections.
              </p>
            </div>

            <div className="text-right">
              <span className="text-3xl font-black">{readiness.readiness_percentage}%</span>
              <span className="text-xs text-white/80 block">Preflight Integrity Score</span>
            </div>
          </div>

          {/* Blocking Reasons (if any) */}
          {readiness.blocking_reasons.length > 0 && (
            <div className="bg-red-50 p-5 rounded-2xl border border-red-200 text-red-800 space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider flex items-center gap-1.5">
                <XCircle className="w-4 h-4 text-red-600" />
                Scheduling Blockers ({readiness.blocking_reasons.length})
              </h4>
              <ul className="text-xs space-y-1 pl-5 list-disc font-medium">
                {readiness.blocking_reasons.map((reason, i) => (
                  <li key={i}>{reason}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Subject Matrix Checklist */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="p-4 bg-slate-50 border-b border-slate-100 font-bold text-xs text-slate-700 uppercase tracking-wider">
              Subject Readiness Breakdown
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-600">
                <thead className="bg-slate-50/50 text-slate-700 uppercase font-bold text-[10px] tracking-wider border-b border-slate-200">
                  <tr>
                    <th className="px-5 py-3">Code</th>
                    <th className="px-5 py-3">Subject Name</th>
                    <th className="px-5 py-3">Type</th>
                    <th className="px-5 py-3">Sections Covered</th>
                    <th className="px-5 py-3">Allocated Faculty</th>
                    <th className="px-5 py-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-medium">
                  {readiness.subjects.map((sub) => (
                    <tr key={sub.subject_code} className="hover:bg-slate-50/50">
                      <td className="px-5 py-3.5 font-mono font-bold text-indigo-900">{sub.subject_code}</td>
                      <td className="px-5 py-3.5 font-semibold text-slate-900">{sub.subject_name}</td>
                      <td className="px-5 py-3.5">{sub.subject_type}</td>
                      <td className="px-5 py-3.5">{sub.sections_covered} / {sub.sections_total} sections</td>
                      <td className="px-5 py-3.5">
                        {sub.allocated_faculty_names.length === 0 ? (
                          <span className="text-amber-600 font-semibold text-[11px]">None assigned</span>
                        ) : (
                          <span className="text-emerald-700 font-semibold text-[11px]">
                            {sub.allocated_faculty_names.join(', ')}
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3.5">
                        {sub.is_fully_allocated ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                            <CheckCircle2 className="w-3 h-3" /> READY
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800">
                            <AlertTriangle className="w-3 h-3" /> INCOMPLETE
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
