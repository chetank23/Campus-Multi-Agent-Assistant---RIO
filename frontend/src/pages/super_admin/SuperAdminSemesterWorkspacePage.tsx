/**
 * pages/super_admin/SuperAdminSemesterWorkspacePage.tsx
 * -----------------------------------------------------
 * Interactive Semester & Subject Matrix Workspace for Super Admin.
 */

import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Plus,
  Edit2,
  Trash2,
  Send,
  GitBranch,
  FlaskConical,
  Lock,
  FileCheck,
} from 'lucide-react';
import {
  getCurriculumVersion,
  addSubjectMapping,
  updateSubjectMapping,
  deleteSubjectMapping,
  updateCurriculumVersionStatus,
  publishCurriculumVersion,
  reviseCurriculumVersion,
  type CurriculumSubjectMapping,
} from '@/api/curriculum';
import { LoadingState } from '@/components/common';

export const SuperAdminSemesterWorkspacePage: React.FC = () => {
  const { versionId } = useParams<{ versionId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const numericVersionId = Number(versionId);

  const [selectedSemesterIdx, setSelectedSemesterIdx] = useState(0);
  const [isSubjectModalOpen, setIsSubjectModalOpen] = useState(false);
  const [editingSubject, setEditingSubject] = useState<CurriculumSubjectMapping | null>(null);

  // Subject Form State
  const [subjectCode, setSubjectCode] = useState('');
  const [subjectName, setSubjectName] = useState('');
  const [subjectType, setSubjectType] = useState('THEORY');
  const [credits, setCredits] = useState<number>(3.0);
  const [lectureHours, setLectureHours] = useState<number>(3);
  const [tutorialHours, setTutorialHours] = useState<number>(0);
  const [practicalHours, setPracticalHours] = useState<number>(0);
  const [requiresLab, setRequiresLab] = useState(false);
  const [consecutivePeriods, setConsecutivePeriods] = useState<number>(2);
  const [isMandatory, setIsMandatory] = useState(true);
  const [electiveGroup, setElectiveGroup] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const { data: version, isLoading } = useQuery({
    queryKey: ['super-admin', 'curriculum-version', numericVersionId],
    queryFn: () => getCurriculumVersion(numericVersionId),
    enabled: !isNaN(numericVersionId),
  });

  const isPublished = version?.status === 'PUBLISHED';

  const saveSubjectMutation = useMutation({
    mutationFn: async () => {
      if (!subjectCode.trim() || !subjectName.trim()) {
        throw new Error('Subject Code and Title are required.');
      }
      const activeSem = version?.semesters[selectedSemesterIdx];
      if (!activeSem) throw new Error('No active semester selected.');

      const payload = {
        subject_code: subjectCode.trim().toUpperCase(),
        subject_name: subjectName.trim(),
        subject_type: subjectType,
        credits: Number(credits),
        lecture_hours: Number(lectureHours),
        tutorial_hours: Number(tutorialHours),
        practical_hours: Number(practicalHours),
        contact_hours: Number(lectureHours) + Number(tutorialHours) + Number(practicalHours),
        requires_lab: requiresLab,
        practical_consecutive_periods: Number(consecutivePeriods),
        is_mandatory: isMandatory,
        elective_group_name: electiveGroup.trim() || null,
      };

      if (editingSubject) {
        return updateSubjectMapping(editingSubject.id, payload);
      } else {
        return addSubjectMapping(numericVersionId, {
          ...payload,
          curriculum_semester_id: activeSem.id,
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'curriculum-version', numericVersionId] });
      closeSubjectModal();
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.detail || err.message || 'Failed to save subject mapping.');
    },
  });

  const deleteSubjectMutation = useMutation({
    mutationFn: async (mappingId: number) => deleteSubjectMapping(mappingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'curriculum-version', numericVersionId] });
    },
  });

  const statusMutation = useMutation({
    mutationFn: async (newStatus: string) => updateCurriculumVersionStatus(numericVersionId, newStatus),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'curriculum-version', numericVersionId] });
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'curriculum-versions'] });
    },
  });

  const publishMutation = useMutation({
    mutationFn: async () => publishCurriculumVersion(numericVersionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'curriculum-version', numericVersionId] });
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'curriculum-versions'] });
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'dashboard-stats'] });
    },
  });

  const reviseMutation = useMutation({
    mutationFn: async () => reviseCurriculumVersion(numericVersionId),
    onSuccess: (rev) => {
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'curriculum-versions'] });
      navigate(`/super-admin/curriculum-versions/${rev.id}`);
    },
  });

  const openAddSubjectModal = () => {
    setEditingSubject(null);
    setSubjectCode('');
    setSubjectName('');
    setSubjectType('THEORY');
    setCredits(3.0);
    setLectureHours(3);
    setTutorialHours(0);
    setPracticalHours(0);
    setRequiresLab(false);
    setConsecutivePeriods(2);
    setIsMandatory(true);
    setElectiveGroup('');
    setFormError(null);
    setIsSubjectModalOpen(true);
  };

  const openEditSubjectModal = (sub: CurriculumSubjectMapping) => {
    setEditingSubject(sub);
    setSubjectCode(sub.subject_code);
    setSubjectName(sub.subject_name);
    setSubjectType(sub.subject_type);
    setCredits(sub.credits);
    setLectureHours(sub.lecture_hours);
    setTutorialHours(sub.tutorial_hours);
    setPracticalHours(sub.practical_hours);
    setRequiresLab(sub.requires_lab);
    setConsecutivePeriods(sub.practical_consecutive_periods || 2);
    setIsMandatory(sub.is_mandatory);
    setElectiveGroup(sub.elective_group_name || '');
    setFormError(null);
    setIsSubjectModalOpen(true);
  };

  const closeSubjectModal = () => {
    setIsSubjectModalOpen(false);
    setEditingSubject(null);
    setFormError(null);
  };

  if (isLoading) {
    return (
      <div className="py-12 flex justify-center">
        <LoadingState message="Loading curriculum workspace..." />
      </div>
    );
  }

  if (!version) {
    return (
      <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
        Curriculum version not found.
      </div>
    );
  }

  const activeSemester = version.semesters[selectedSemesterIdx] || version.semesters[0];

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ── Top Bar with Back Button & Lifecycle Controls ────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/super-admin/curriculum-versions')}
            className="p-2 rounded-xl text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
            title="Back to Versions"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold font-mono text-slate-900">{version.version_code}</h2>
              <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                isPublished
                  ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                  : version.status === 'APPROVED'
                  ? 'bg-blue-100 text-blue-800'
                  : 'bg-slate-100 text-slate-700'
              }`}>
                {version.status}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              {version.program_name} • {version.department_name} • Regulation {version.regulation_code}
            </p>
          </div>
        </div>

        {/* Action Buttons based on status */}
        <div className="flex items-center gap-2 self-end sm:self-auto">
          {version.status === 'DRAFT' && (
            <button
              onClick={() => statusMutation.mutate('NEEDS_REVIEW')}
              disabled={statusMutation.isPending}
              className="px-3.5 py-1.5 bg-amber-500 hover:bg-amber-600 text-white text-xs font-semibold rounded-xl shadow-sm transition-all"
            >
              Submit for Review
            </button>
          )}

          {version.status === 'NEEDS_REVIEW' && (
            <button
              onClick={() => statusMutation.mutate('APPROVED')}
              disabled={statusMutation.isPending}
              className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-all flex items-center gap-1.5"
            >
              <FileCheck className="w-3.5 h-3.5" /> Approve Scheme
            </button>
          )}

          {version.status === 'APPROVED' && (
            <button
              onClick={() => publishMutation.mutate()}
              disabled={publishMutation.isPending}
              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl shadow-sm transition-all flex items-center gap-1.5"
            >
              <Send className="w-3.5 h-3.5" /> Publish to Department
            </button>
          )}

          {isPublished && (
            <button
              onClick={() => reviseMutation.mutate()}
              disabled={reviseMutation.isPending}
              className="px-3.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 text-xs font-semibold rounded-xl transition-all flex items-center gap-1.5"
            >
              <GitBranch className="w-3.5 h-3.5" /> Branch Revision
            </button>
          )}
        </div>
      </div>

      {/* ── Summary Metrics Strip ────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <span className="text-[11px] font-semibold text-slate-500 block">TOTAL CREDITS</span>
          <span className="text-xl font-black text-slate-900 mt-1 block">{version.total_credits} Credits</span>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <span className="text-[11px] font-semibold text-slate-500 block">PROGRAM DURATION</span>
          <span className="text-xl font-black text-slate-900 mt-1 block">{version.total_semesters} Semesters</span>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <span className="text-[11px] font-semibold text-slate-500 block">ACTIVE SEMESTER CREDITS</span>
          <span className="text-xl font-black text-indigo-700 mt-1 block">{activeSemester?.total_credits || 0} Credits</span>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <span className="text-[11px] font-semibold text-slate-500 block">WEEKLY CONTACT HOURS</span>
          <span className="text-xl font-black text-slate-900 mt-1 block">{activeSemester?.total_contact_hours || 0} Hours</span>
        </div>
      </div>

      {/* ── Semester Tabs ────────────────────────────────────────────── */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-slate-200">
        {version.semesters.map((sem, idx) => (
          <button
            key={sem.id}
            onClick={() => setSelectedSemesterIdx(idx)}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all whitespace-nowrap flex items-center gap-2 ${
              selectedSemesterIdx === idx
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
            }`}
          >
            <span>Semester {sem.semester_number}</span>
            <span className={`px-1.5 py-0.2 rounded-md text-[10px] ${
              selectedSemesterIdx === idx ? 'bg-indigo-700 text-white' : 'bg-slate-100 text-slate-600'
            }`}>
              {sem.total_credits} cr
            </span>
          </button>
        ))}
      </div>

      {/* ── Subjects Matrix for Active Semester ───────────────────────── */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900">
              Semester {activeSemester?.semester_number} Course Curriculum Matrix
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Subject definitions, L-T-P lecture-tutorial-practical hours, laboratory requirements, and credit allocations.
            </p>
          </div>

          {!isPublished && (
            <button
              onClick={openAddSubjectModal}
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs rounded-xl shadow-sm transition-all flex items-center gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" /> Add Subject
            </button>
          )}

          {isPublished && (
            <span className="inline-flex items-center gap-1 text-xs text-slate-400 font-semibold">
              <Lock className="w-3.5 h-3.5" /> Immutable Published Scheme
            </span>
          )}
        </div>

        {(!activeSemester || activeSemester.subject_mappings.length === 0) ? (
          <div className="py-12 text-center text-slate-500 text-xs">
            No subjects added to Semester {activeSemester?.semester_number} yet. Click "Add Subject" to populate.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50/80 text-slate-700 uppercase font-bold text-[10px] tracking-wider border-b border-slate-200">
                <tr>
                  <th className="px-5 py-3">Code</th>
                  <th className="px-5 py-3">Course / Subject Name</th>
                  <th className="px-5 py-3">Type</th>
                  <th className="px-5 py-3">L - T - P</th>
                  <th className="px-5 py-3">Contact Hrs</th>
                  <th className="px-5 py-3">Credits</th>
                  <th className="px-5 py-3">Lab Req</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {activeSemester.subject_mappings.map((sub) => (
                  <tr key={sub.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-5 py-3.5 font-mono font-bold text-indigo-900">{sub.subject_code}</td>
                    <td className="px-5 py-3.5 font-semibold text-slate-900">{sub.subject_name}</td>
                    <td className="px-5 py-3.5">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700 uppercase">
                        {sub.subject_type}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 font-mono">
                      {sub.lecture_hours} - {sub.tutorial_hours} - {sub.practical_hours}
                    </td>
                    <td className="px-5 py-3.5 font-bold">{sub.contact_hours} hrs/wk</td>
                    <td className="px-5 py-3.5 font-bold text-indigo-900">{sub.credits}</td>
                    <td className="px-5 py-3.5">
                      {sub.requires_lab ? (
                        <span className="inline-flex items-center gap-1 text-emerald-700 font-semibold text-[11px]">
                          <FlaskConical className="w-3.5 h-3.5" /> Lab ({sub.practical_consecutive_periods} periods)
                        </span>
                      ) : (
                        <span className="text-slate-400">No</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      {!isPublished && (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => openEditSubjectModal(sub)}
                            className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-slate-100"
                            title="Edit Subject"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => {
                              if (confirm(`Delete subject ${sub.subject_code}?`)) {
                                deleteSubjectMutation.mutate(sub.id);
                              }
                            }}
                            className="p-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50"
                            title="Delete Subject"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Add / Edit Subject Modal ──────────────────────────────────── */}
      {isSubjectModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-100 space-y-4">
            <h3 className="text-base font-bold text-slate-900">
              {editingSubject ? 'Edit Subject Mapping' : 'Add Subject to Semester ' + activeSemester?.semester_number}
            </h3>

            {formError && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs">
                {formError}
              </div>
            )}

            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-1">
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Subject Code *</label>
                  <input
                    type="text"
                    placeholder="e.g. CS301"
                    value={subjectCode}
                    onChange={(e) => setSubjectCode(e.target.value.toUpperCase())}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none uppercase font-mono"
                  />
                </div>
                <div className="col-span-2">
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Subject Title *</label>
                  <input
                    type="text"
                    placeholder="e.g. Data Structures and Algorithms"
                    value={subjectName}
                    onChange={(e) => setSubjectName(e.target.value)}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Subject Type</label>
                  <select
                    value={subjectType}
                    onChange={(e) => setSubjectType(e.target.value)}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
                  >
                    <option value="THEORY">Theory</option>
                    <option value="PRACTICAL">Practical / Lab</option>
                    <option value="INTEGRATED">Integrated (L+P)</option>
                    <option value="PROFESSIONAL_ELECTIVE">Professional Elective</option>
                    <option value="OPEN_ELECTIVE">Open Elective</option>
                    <option value="PROJECT">Project Work</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Credits</label>
                  <input
                    type="number"
                    step="0.5"
                    min="0"
                    value={credits}
                    onChange={(e) => setCredits(Number(e.target.value))}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none font-bold"
                  />
                </div>
              </div>

              {/* L-T-P Hours */}
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                <span className="text-xs font-bold text-slate-700 block">Weekly Contact Hours (L - T - P)</span>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="text-[11px] text-slate-500 block mb-1">Lecture (L)</label>
                    <input
                      type="number"
                      min="0"
                      value={lectureHours}
                      onChange={(e) => setLectureHours(Number(e.target.value))}
                      className="w-full text-xs px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-slate-500 block mb-1">Tutorial (T)</label>
                    <input
                      type="number"
                      min="0"
                      value={tutorialHours}
                      onChange={(e) => setTutorialHours(Number(e.target.value))}
                      className="w-full text-xs px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-slate-500 block mb-1">Practical (P)</label>
                    <input
                      type="number"
                      min="0"
                      value={practicalHours}
                      onChange={(e) => setPracticalHours(Number(e.target.value))}
                      className="w-full text-xs px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white"
                    />
                  </div>
                </div>
                <p className="text-[11px] text-slate-500">
                  Total weekly contact hours: <span className="font-bold text-slate-800">{lectureHours + tutorialHours + practicalHours} hrs</span>
                </p>
              </div>

              {/* Lab Requirement */}
              <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-200">
                <div className="space-y-0.5">
                  <span className="text-xs font-semibold text-slate-800 block">Requires Specialized Laboratory</span>
                  <p className="text-[11px] text-slate-500">Enforces laboratory room constraints in solver</p>
                </div>
                <input
                  type="checkbox"
                  checked={requiresLab}
                  onChange={(e) => setRequiresLab(e.target.checked)}
                  className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
                />
              </div>

              {requiresLab && (
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">
                    Consecutive Practical Periods (Solver block size)
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="4"
                    value={consecutivePeriods}
                    onChange={(e) => setConsecutivePeriods(Number(e.target.value))}
                    className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={closeSubjectModal}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => saveSubjectMutation.mutate()}
                disabled={saveSubjectMutation.isPending}
                className="px-4 py-2 text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl shadow-sm transition-all disabled:opacity-50"
              >
                {saveSubjectMutation.isPending ? 'Saving...' : editingSubject ? 'Update Subject' : 'Add Subject'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
