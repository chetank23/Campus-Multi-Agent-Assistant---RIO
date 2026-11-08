/**
 * pages/admin/curriculum/AdminCurriculumAllocationPage.tsx
 * --------------------------------------------------------
 * Admin Operational Course-Section & Faculty Teaching Allocations.
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  UserCheck,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import {
  getSectionOfferings,
  allocateFacultyOffering,
  type SectionCourseOffering,
} from '@/api/curriculum';
import { apiClient } from '@/api/client';
import { LoadingState } from '@/components/common';

export const AdminCurriculumAllocationPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [academicYearId, setAcademicYearId] = useState<number | ''>('');
  const [semesterId, setSemesterId] = useState<number | ''>('');
  const [sectionId, setSectionId] = useState<number | ''>('');
  const [selectedOffering, setSelectedOffering] = useState<SectionCourseOffering | null>(null);

  // Faculty Allocation Modal
  const [facultyId, setFacultyId] = useState<number | ''>('');
  const [assignedRole, setAssignedRole] = useState('PRIMARY_LECTURER');
  const [assignedHours, setAssignedHours] = useState<number>(3);
  const [allocError, setAllocError] = useState<string | null>(null);

  // Fetch Academic Years, Semesters, Sections, Faculty
  const { data: academicYears } = useQuery({
    queryKey: ['academic-years'],
    queryFn: async () => {
      const { data } = await apiClient.get<any[]>('/academic-years/');
      return data;
    },
  });

  const effectiveAcademicYearId = academicYearId !== '' ? academicYearId : (academicYears?.[0]?.id ?? '');

  const { data: semesters } = useQuery({
    queryKey: ['semesters', effectiveAcademicYearId],
    queryFn: async () => {
      const { data } = await apiClient.get<any[]>('/semesters/');
      return effectiveAcademicYearId ? data.filter((s) => s.academic_year_id === effectiveAcademicYearId) : data;
    },
  });

  const effectiveSemesterId = semesterId !== '' ? semesterId : (semesters?.[0]?.id ?? '');

  const { data: sections } = useQuery({
    queryKey: ['sections'],
    queryFn: async () => {
      const { data } = await apiClient.get<any[]>('/sections/');
      return data;
    },
  });

  const effectiveSectionId = sectionId !== '' ? sectionId : (sections?.[0]?.id ?? '');

  const { data: facultyList } = useQuery({
    queryKey: ['faculty'],
    queryFn: async () => {
      const { data } = await apiClient.get<any[]>('/faculty/');
      return data;
    },
  });

  const { data: offerings, isLoading } = useQuery({
    queryKey: ['admin', 'offerings', effectiveAcademicYearId, effectiveSemesterId, effectiveSectionId],
    queryFn: () =>
      getSectionOfferings({
        academic_year_id: Number(effectiveAcademicYearId),
        semester_id: Number(effectiveSemesterId),
        section_id: effectiveSectionId ? Number(effectiveSectionId) : undefined,
      }),
    enabled: Boolean(effectiveAcademicYearId && effectiveSemesterId),
  });

  const allocateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedOffering || !facultyId) throw new Error('Please select a faculty member.');
      return allocateFacultyOffering({
        section_course_offering_id: selectedOffering.id,
        faculty_id: Number(facultyId),
        assigned_role: assignedRole,
        assigned_hours: Number(assignedHours),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'offerings'] });
      setSelectedOffering(null);
      setAllocError(null);
    },
    onError: (err: any) => {
      setAllocError(err.response?.data?.detail || err.message || 'Failed to allocate faculty.');
    },
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ── Top Header ──────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Users className="w-5 h-5 text-indigo-600" />
            Curriculum Course & Faculty Allocation
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Map curriculum subjects to section deliveries and assign faculty lecturers before timetable generation.
          </p>
        </div>

        <button
          onClick={() => navigate('/admin/curriculum/readiness')}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs rounded-xl shadow-sm transition-all flex items-center gap-2 self-start"
        >
          <CheckCircle2 className="w-4 h-4" /> Verify Scheduling Readiness
        </button>
      </div>

      {/* ── Filter Strip ────────────────────────────────────────────── */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <label className="text-xs font-semibold text-slate-700 block mb-1">Academic Year</label>
          <select
            value={effectiveAcademicYearId}
            onChange={(e) => setAcademicYearId(Number(e.target.value))}
            className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
          >
            {(academicYears || []).map((ay: any) => (
              <option key={ay.id} value={ay.id}>{ay.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-700 block mb-1">Semester</label>
          <select
            value={effectiveSemesterId}
            onChange={(e) => setSemesterId(Number(e.target.value))}
            className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
          >
            {(semesters || []).map((sem: any) => (
              <option key={sem.id} value={sem.id}>{sem.name || `Semester ${sem.semester_number}`}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-700 block mb-1">Class Section</label>
          <select
            value={effectiveSectionId}
            onChange={(e) => setSectionId(Number(e.target.value))}
            className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
          >
            {(sections || []).map((sec: any) => (
              <option key={sec.id} value={sec.id}>Section {sec.section_name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Offerings & Allocations Table ───────────────────────────── */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="py-12 flex justify-center">
            <LoadingState message="Loading section course offerings..." />
          </div>
        ) : (offerings || []).length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-xs">
            No course offerings mapped to this section yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50/80 text-slate-700 uppercase font-bold text-[10px] tracking-wider border-b border-slate-200">
                <tr>
                  <th className="px-5 py-3">Subject Code</th>
                  <th className="px-5 py-3">Subject Title</th>
                  <th className="px-5 py-3">Section</th>
                  <th className="px-5 py-3">Type</th>
                  <th className="px-5 py-3">Assigned Faculty</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {(offerings || []).map((off) => (
                  <tr key={off.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-5 py-3.5 font-mono font-bold text-indigo-900">{off.subject_code}</td>
                    <td className="px-5 py-3.5 font-semibold text-slate-900">{off.subject_name}</td>
                    <td className="px-5 py-3.5">Section {off.section_name}</td>
                    <td className="px-5 py-3.5">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700 uppercase">
                        {off.subject_type || 'CORE'}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      {off.faculty_allocations.length === 0 ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-600">
                          <AlertTriangle className="w-3.5 h-3.5" /> Unassigned
                        </span>
                      ) : (
                        <div className="space-y-1">
                          {off.faculty_allocations.map((fa) => (
                            <div key={fa.id} className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200 mr-1.5">
                              <UserCheck className="w-3 h-3" />
                              {fa.faculty_name} ({fa.assigned_hours} hrs)
                            </div>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <button
                        onClick={() => {
                          setSelectedOffering(off);
                          setFacultyId(facultyList?.[0]?.id || '');
                          setAssignedRole('PRIMARY_LECTURER');
                          setAssignedHours(3);
                          setAllocError(null);
                        }}
                        className="px-3 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold rounded-lg border border-indigo-200 transition-colors"
                      >
                        Assign Faculty
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Assign Faculty Modal ─────────────────────────────────────── */}
      {selectedOffering && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-100 space-y-4">
            <h3 className="text-base font-bold text-slate-900">
              Assign Faculty Lecturer
            </h3>
            <p className="text-xs text-slate-600">
              Offering: <strong>{selectedOffering.subject_code} - {selectedOffering.subject_name}</strong> (Section {selectedOffering.section_name})
            </p>

            {allocError && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs">
                {allocError}
              </div>
            )}

            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Select Faculty Member *</label>
                <select
                  value={facultyId}
                  onChange={(e) => setFacultyId(Number(e.target.value))}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
                >
                  {(facultyList || []).map((f: any) => (
                    <option key={f.id} value={f.id}>
                      {f.name || f.faculty_id || `Faculty #${f.id}`} ({f.department_name || 'Dept'})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Teaching Role</label>
                <select
                  value={assignedRole}
                  onChange={(e) => setAssignedRole(e.target.value)}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
                >
                  <option value="PRIMARY_LECTURER">Primary Lecturer</option>
                  <option value="CO_LECTURER">Co-Lecturer</option>
                  <option value="LAB_INSTRUCTOR">Lab Instructor</option>
                  <option value="TUTORIAL_MENTOR">Tutorial Mentor</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Weekly Assigned Contact Hours</label>
                <input
                  type="number"
                  min="1"
                  max="40"
                  value={assignedHours}
                  onChange={(e) => setAssignedHours(Number(e.target.value))}
                  className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setSelectedOffering(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => allocateMutation.mutate()}
                disabled={allocateMutation.isPending}
                className="px-4 py-2 text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl shadow-sm transition-all disabled:opacity-50"
              >
                {allocateMutation.isPending ? 'Allocating...' : 'Confirm Allocation'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
