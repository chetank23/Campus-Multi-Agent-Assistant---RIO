/**
 * pages/super_admin/SuperAdminPDFExtractionPage.tsx
 * -------------------------------------------------
 * AI Syllabus Document Processing & Extraction Review Studio.
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Upload,
  Sparkles,
  CheckCircle2,
} from 'lucide-react';
import {
  uploadCurriculumPDF,
  triggerExtractionJob,
  getExtractionJob,
  reviewExtractionJob,
  getCurriculumVersions,
  type ExtractedSubjectItem,
} from '@/api/curriculum';

export const SuperAdminPDFExtractionPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [file, setFile] = useState<File | null>(null);
  const [docTitle, setDocTitle] = useState('');
  const [targetVersionId, setTargetVersionId] = useState<number | ''>('');
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Review & Edit State
  const [editedSubjects, setEditedSubjects] = useState<ExtractedSubjectItem[]>([]);
  const [reviewFeedback] = useState('');

  const { data: versions } = useQuery({
    queryKey: ['super-admin', 'curriculum-versions'],
    queryFn: () => getCurriculumVersions({ status: 'DRAFT' }),
  });

  const { data: job } = useQuery({
    queryKey: ['super-admin', 'extraction-job', activeJobId],
    queryFn: () => (activeJobId ? getExtractionJob(activeJobId) : null),
    enabled: activeJobId !== null,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && ['QUEUED', 'PROCESSING'].includes(data.status)) {
        return 2000;
      }
      return false;
    },
  });

  // When job data loads with extracted subjects, initialize editedSubjects
  React.useEffect(() => {
    if (job?.extracted_data && editedSubjects.length === 0) {
      setEditedSubjects(job.extracted_data);
    }
  }, [job, editedSubjects.length]);

  const uploadAndExtractMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error('Please select a valid institutional PDF file.');
      if (!docTitle.trim()) throw new Error('Document title is required.');

      const formData = new FormData();
      formData.append('file', file);
      formData.append('title', docTitle.trim());
      if (targetVersionId) {
        formData.append('curriculum_version_id', String(targetVersionId));
      }

      const uploadedDoc = await uploadCurriculumPDF(formData);
      const jobRes = await triggerExtractionJob(uploadedDoc.id, targetVersionId ? Number(targetVersionId) : undefined);
      return jobRes;
    },
    onSuccess: (jobRes) => {
      setActiveJobId(jobRes.id);
      setEditedSubjects([]);
      setUploadError(null);
    },
    onError: (err: any) => {
      setUploadError(err.response?.data?.detail || err.message || 'Extraction pipeline failed.');
    },
  });

  const reviewMutation = useMutation({
    mutationFn: async (action: 'APPROVE' | 'REJECT') => {
      if (!activeJobId) return;
      return reviewExtractionJob(activeJobId, {
        action,
        feedback: reviewFeedback,
        target_version_id: targetVersionId ? Number(targetVersionId) : undefined,
        edited_data: action === 'APPROVE' ? editedSubjects : undefined,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'extraction-job', activeJobId] });
      queryClient.invalidateQueries({ queryKey: ['super-admin', 'curriculum-versions'] });
      if (targetVersionId) {
        navigate(`/super-admin/curriculum-versions/${targetVersionId}`);
      }
    },
  });

  const handleSubjectChange = (index: number, field: keyof ExtractedSubjectItem, value: any) => {
    setEditedSubjects((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* ── Header ───────────────────────────────────────────────────── */}
      <div>
        <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-amber-500" />
          AI Syllabus Document Extraction Studio
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Automated syllabus parsing, course matrix extraction, credit heuristics, and source page citations.
        </p>
      </div>

      {/* ── Upload & Job Launch Card ──────────────────────────────────── */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
          <Upload className="w-4 h-4 text-indigo-600" /> Upload Official Syllabus PDF
        </h3>

        {uploadError && (
          <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs">
            {uploadError}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="text-xs font-semibold text-slate-700 block mb-1">Document Title *</label>
            <input
              type="text"
              placeholder="e.g. CSE R2026 Official Syllabus"
              value={docTitle}
              onChange={(e) => setDocTitle(e.target.value)}
              className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700 block mb-1">Target Curriculum Version</label>
            <select
              value={targetVersionId}
              onChange={(e) => setTargetVersionId(e.target.value ? Number(e.target.value) : '')}
              className="w-full text-xs px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
            >
              <option value="">Select Target Version (Draft)...</option>
              {(versions || []).map((v) => (
                <option key={v.id} value={v.id}>{v.version_code} - {v.program_name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700 block mb-1">Syllabus PDF File *</label>
            <input
              type="file"
              accept=".pdf"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  setFile(e.target.files[0]);
                  if (!docTitle) {
                    setDocTitle(e.target.files[0].name.replace('.pdf', ''));
                  }
                }
              }}
              className="w-full text-xs px-2 py-1.5 border border-slate-200 rounded-xl text-slate-600 focus:outline-none file:mr-2 file:py-1 file:px-2.5 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
            />
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <button
            onClick={() => uploadAndExtractMutation.mutate()}
            disabled={uploadAndExtractMutation.isPending || !file}
            className="px-5 py-2 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-700 hover:to-indigo-800 text-white font-bold text-xs rounded-xl shadow-md transition-all flex items-center gap-2 disabled:opacity-50"
          >
            <Sparkles className="w-4 h-4 text-amber-400" />
            {uploadAndExtractMutation.isPending ? 'Extracting Syllabus...' : 'Extract Curriculum Table'}
          </button>
        </div>
      </div>

      {/* ── Active Job Processing & Verification Studio ───────────────── */}
      {job && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden space-y-4">
          <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-slate-900">
                  Extraction Results: {job.document_title || 'Syllabus PDF'}
                </h3>
                <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                  job.status === 'APPROVED'
                    ? 'bg-emerald-100 text-emerald-800'
                    : job.status === 'AWAITING_REVIEW'
                    ? 'bg-amber-100 text-amber-800'
                    : 'bg-slate-100 text-slate-700'
                }`}>
                  {job.status}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Processed {job.total_pages} pages • Identified {job.extracted_semesters_count} semesters • Extracted {job.extracted_subjects_count} subject mappings
              </p>
            </div>

            {job.status === 'AWAITING_REVIEW' && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => reviewMutation.mutate('REJECT')}
                  disabled={reviewMutation.isPending}
                  className="px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-700 text-xs font-semibold rounded-xl border border-red-200 transition-colors"
                >
                  Reject
                </button>
                <button
                  onClick={() => reviewMutation.mutate('APPROVE')}
                  disabled={reviewMutation.isPending}
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl shadow-sm transition-all flex items-center gap-1.5"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" /> Approve & Apply to Version
                </button>
              </div>
            )}
          </div>

          {/* Editable Subjects Table */}
          <div className="p-5 overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50 text-slate-700 uppercase font-bold text-[10px] tracking-wider border-b border-slate-200">
                <tr>
                  <th className="px-3 py-2.5">Sem</th>
                  <th className="px-3 py-2.5">Code</th>
                  <th className="px-3 py-2.5">Subject Title</th>
                  <th className="px-3 py-2.5">Type</th>
                  <th className="px-3 py-2.5">L-T-P</th>
                  <th className="px-3 py-2.5">Credits</th>
                  <th className="px-3 py-2.5">Lab</th>
                  <th className="px-3 py-2.5">Confidence</th>
                  <th className="px-3 py-2.5">Source Citation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {editedSubjects.map((sub, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/50">
                    <td className="px-3 py-2">
                      <input
                        type="number"
                        min="1"
                        max="8"
                        value={sub.semester}
                        onChange={(e) => handleSubjectChange(idx, 'semester', Number(e.target.value))}
                        className="w-12 px-1.5 py-1 border border-slate-200 rounded text-center font-bold"
                      />
                    </td>
                    <td className="px-3 py-2 font-mono font-bold text-indigo-900">
                      <input
                        type="text"
                        value={sub.code}
                        onChange={(e) => handleSubjectChange(idx, 'code', e.target.value.toUpperCase())}
                        className="w-24 px-1.5 py-1 border border-slate-200 rounded uppercase font-mono"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="text"
                        value={sub.name}
                        onChange={(e) => handleSubjectChange(idx, 'name', e.target.value)}
                        className="w-56 px-1.5 py-1 border border-slate-200 rounded font-semibold text-slate-900"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <select
                        value={sub.type}
                        onChange={(e) => handleSubjectChange(idx, 'type', e.target.value)}
                        className="px-1.5 py-1 border border-slate-200 rounded text-[11px]"
                      >
                        <option value="THEORY">Theory</option>
                        <option value="PRACTICAL">Practical</option>
                        <option value="PROFESSIONAL_ELECTIVE">Elective</option>
                      </select>
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px]">
                      {sub.lecture}-{sub.tutorial}-{sub.practical}
                    </td>
                    <td className="px-3 py-2 font-bold text-slate-800">
                      <input
                        type="number"
                        step="0.5"
                        value={sub.credits}
                        onChange={(e) => handleSubjectChange(idx, 'credits', Number(e.target.value))}
                        className="w-14 px-1.5 py-1 border border-slate-200 rounded text-center font-bold"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={sub.requires_lab}
                        onChange={(e) => handleSubjectChange(idx, 'requires_lab', e.target.checked)}
                        className="rounded text-indigo-600 focus:ring-0"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700">
                        {Math.round(sub.confidence_score * 100)}%
                      </span>
                    </td>
                    <td className="px-3 py-2 text-[11px] text-slate-400 font-mono">
                      p. {sub.source_page || 1}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
