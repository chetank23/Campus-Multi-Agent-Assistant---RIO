import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CalendarDays,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Send,
  Loader2,
  ShieldCheck,
  Info,
} from 'lucide-react';
import {
  getTimetableAcademicYears,
  getTimetableSemesters,
  getTimetableDepartments,
  getTimetableSections,
  getCanonicalTimetables,
  generateTimetablePreview,
  publishCanonicalTimetable,
  type TimetablePreviewResponse,
  type TimetablePreviewEntry,
} from '@/api/timetable';
import { PageHeader } from '@/components/common';

const DAY_LABELS: Record<string, string> = {
  MON: 'Monday',
  TUE: 'Tuesday',
  WED: 'Wednesday',
  THU: 'Thursday',
  FRI: 'Friday',
  SAT: 'Saturday',
};

// 7 Instructional Periods + 2 Breaks (Time-only bold headers)
const TIME_COLUMNS = [
  { key: 'P1', timeLabel: '08:30–09:25', name: 'Period 1', start: '08:30', end: '09:25', isBreak: false },
  { key: 'P2', timeLabel: '09:25–10:20', name: 'Period 2', start: '09:25', end: '10:20', isBreak: false },
  { key: 'TEA_BREAK', timeLabel: '10:20–10:40', name: 'Tea Break', start: '10:20', end: '10:40', isBreak: true },
  { key: 'P3', timeLabel: '10:40–11:35', name: 'Period 3', start: '10:40', end: '11:35', isBreak: false },
  { key: 'P4', timeLabel: '11:35–12:30', name: 'Period 4', start: '11:35', end: '12:30', isBreak: false },
  { key: 'LUNCH_BREAK', timeLabel: '12:30–13:30', name: 'Lunch Break', start: '12:30', end: '13:30', isBreak: true },
  { key: 'P5', timeLabel: '13:30–14:25', name: 'Period 5', start: '13:30', end: '14:25', isBreak: false },
  { key: 'P6', timeLabel: '14:25–15:20', name: 'Period 6', start: '14:25', end: '15:20', isBreak: false },
  { key: 'P7', timeLabel: '15:20–16:15', name: 'Period 7', start: '15:20', end: '16:15', isBreak: false },
];

const normalizeDay = (d?: string | null): string => {
  if (!d) return 'MON';
  const u = d.toUpperCase().trim();
  if (u.startsWith('MON')) return 'MON';
  if (u.startsWith('TUE')) return 'TUE';
  if (u.startsWith('WED')) return 'WED';
  if (u.startsWith('THU')) return 'THU';
  if (u.startsWith('FRI')) return 'FRI';
  if (u.startsWith('SAT')) return 'SAT';
  return u.slice(0, 3);
};

export const AdminTimetableManagementPage: React.FC = () => {
  const queryClient = useQueryClient();

  // Scope selection state
  const [selectedAyId, setSelectedAyId] = useState<number | ''>('');
  const [selectedSemId, setSelectedSemId] = useState<number | ''>('');
  const [selectedDeptId, setSelectedDeptId] = useState<number | ''>('');
  const [workingDays, setWorkingDays] = useState<'MON_SAT' | 'MON_FRI'>('MON_SAT');
  const [activeSectionId, setActiveSectionId] = useState<number | null>(null);

  // Preview & Workflow state
  const [previewData, setPreviewData] = useState<TimetablePreviewResponse | null>(null);
  const [showPublishModal, setShowPublishModal] = useState(false);
  const [publishSuccessMsg, setPublishSuccessMsg] = useState<string | null>(null);

  // 1. Fetch Academic Years
  const { data: academicYears = [], isLoading: loadingAy } = useQuery({
    queryKey: ['timetable-academic-years'],
    queryFn: getTimetableAcademicYears,
  });

  // 2. Fetch Semesters (dependent on Academic Year)
  const { data: semesters = [], isLoading: loadingSem } = useQuery({
    queryKey: ['timetable-semesters', selectedAyId],
    queryFn: () => getTimetableSemesters(Number(selectedAyId)),
    enabled: typeof selectedAyId === 'number' && selectedAyId > 0,
  });

  // 3. Fetch Departments (dependent on Academic Year + Semester)
  const { data: departments = [], isLoading: loadingDept } = useQuery({
    queryKey: ['timetable-departments', selectedAyId, selectedSemId],
    queryFn: () => getTimetableDepartments(Number(selectedAyId), Number(selectedSemId)),
    enabled: typeof selectedAyId === 'number' && typeof selectedSemId === 'number',
  });

  // 4. Fetch Sections for selected Scope (Academic Year + Semester + Department)
  const { data: sections = [] } = useQuery({
    queryKey: ['timetable-sections', selectedAyId, selectedDeptId, selectedSemId],
    queryFn: () => getTimetableSections(Number(selectedAyId), Number(selectedDeptId), Number(selectedSemId)),
    enabled: typeof selectedAyId === 'number' && typeof selectedDeptId === 'number' && typeof selectedSemId === 'number',
  });

  // 5. Fetch Existing Published Timetables for this scope
  const { data: publishedTimetables = [], refetch: refetchPublished } = useQuery({
    queryKey: ['timetable-canonical', selectedAyId, selectedSemId, selectedDeptId],
    queryFn: () =>
      getCanonicalTimetables({
        academic_year_id: Number(selectedAyId),
        semester_id: Number(selectedSemId),
        department_id: Number(selectedDeptId),
      }),
    enabled: typeof selectedAyId === 'number' && typeof selectedSemId === 'number' && typeof selectedDeptId === 'number',
  });

  // Derive effective active section id without cascading setState in effect
  const currentSectionId = useMemo(() => {
    if (activeSectionId && sections.some((s) => s.id === activeSectionId)) {
      return activeSectionId;
    }
    return sections.length > 0 ? sections[0].id : null;
  }, [sections, activeSectionId]);

  // Derive active display days from previewData, published canonical timetable, or state
  const displayDays = useMemo(() => {
    const effectiveWd = previewData?.working_days || (publishedTimetables[0]?.working_days) || workingDays;
    return effectiveWd === 'MON_FRI' ? ['MON', 'TUE', 'WED', 'THU', 'FRI'] : ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
  }, [previewData, publishedTimetables, workingDays]);

  // Generation Mutation
  const generateMutation = useMutation({
    mutationFn: (scope: { academic_year_id: number; semester_id: number; department_id: number; working_days?: 'MON_FRI' | 'MON_SAT' }) =>
      generateTimetablePreview(scope),
    onSuccess: (data) => {
      setPreviewData(data);
      if (data.working_days) {
        setWorkingDays(data.working_days);
      }
      setPublishSuccessMsg(null);
      if (data.sections.length > 0) {
        const firstSec = data.sections[0] as unknown as { section_id?: number; id?: number };
        setActiveSectionId(firstSec.section_id || firstSec.id || null);
      }
    },
  });

  // Publication Mutation
  const publishMutation = useMutation({
    mutationFn: () => {
      if (!previewData || typeof selectedAyId !== 'number' || typeof selectedSemId !== 'number' || typeof selectedDeptId !== 'number') {
        throw new Error('No timetable preview available to publish.');
      }
      return publishCanonicalTimetable({
        academic_year_id: selectedAyId,
        semester_id: selectedSemId,
        department_id: selectedDeptId,
        working_days: previewData.working_days || workingDays,
        entries: previewData.entries,
      });
    },
    onSuccess: (res) => {
      setShowPublishModal(false);
      setPreviewData(null);
      setPublishSuccessMsg(`Timetable successfully published! ${res.total_entries_published} classes scheduled across ${res.published_timetables.length} sections.`);
      refetchPublished();
      queryClient.invalidateQueries({ queryKey: ['timetable-canonical'] });
    },
  });

  // Reset dependent selections
  const handleAyChange = (val: string) => {
    const id = val ? Number(val) : '';
    setSelectedAyId(id);
    setSelectedSemId('');
    setSelectedDeptId('');
    setPreviewData(null);
    setPublishSuccessMsg(null);
  };

  const handleSemChange = (val: string) => {
    const id = val ? Number(val) : '';
    setSelectedSemId(id);
    setSelectedDeptId('');
    setPreviewData(null);
    setPublishSuccessMsg(null);
  };

  const handleDeptChange = (val: string) => {
    const id = val ? Number(val) : '';
    setSelectedDeptId(id);
    setPreviewData(null);
    setPublishSuccessMsg(null);
  };

  const handleGenerate = () => {
    if (typeof selectedAyId !== 'number' || typeof selectedSemId !== 'number' || typeof selectedDeptId !== 'number') {
      return;
    }
    generateMutation.mutate({
      academic_year_id: selectedAyId,
      semester_id: selectedSemId,
      department_id: selectedDeptId,
      working_days: workingDays,
    });
  };

  const isScopeSelected =
    typeof selectedAyId === 'number' &&
    typeof selectedSemId === 'number' &&
    typeof selectedDeptId === 'number';

  const isExistingPublished = publishedTimetables.length > 0;

  // Active entries to display: either from Preview or from Published Canonical
  const activeEntries: TimetablePreviewEntry[] = useMemo(() => {
    if (previewData) {
      return previewData.entries.filter((e) => !currentSectionId || e.section_id === currentSectionId);
    }
    if (publishedTimetables.length > 0) {
      const matchTt = publishedTimetables.find((t) => !currentSectionId || t.section_id === currentSectionId);
      return matchTt ? matchTt.entries : [];
    }
    return [];
  }, [previewData, publishedTimetables, currentSectionId]);

  // Map entries into grid [day][time_signature]
  const timetableMatrix = useMemo(() => {
    const mat: Record<string, Record<string, TimetablePreviewEntry[]>> = {};
    displayDays.forEach((d) => {
      mat[d] = {};
      TIME_COLUMNS.forEach((col) => {
        mat[d][`${col.start}-${col.end}`] = [];
      });
    });

    activeEntries.forEach((entry) => {
      const day = normalizeDay(entry.day);
      if (mat[day]) {
        // match by start_time
        const col = TIME_COLUMNS.find((c) => !c.isBreak && c.start === (entry.start_time || '').slice(0, 5));
        if (col) {
          mat[day][`${col.start}-${col.end}`].push(entry);
        }
      }
    });

    return mat;
  }, [activeEntries, displayDays]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      <PageHeader
        title="Timetable Management"
        subtitle="Generate, validate, and publish canonical schedules for academic sections."
      />

      {/* ── 1. Academic Scope Selection Bar ────────────────────────────── */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4 flex items-center gap-2">
          <CalendarDays size={16} className="text-blue-600" />
          Academic Scope Selection
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Academic Year */}
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Academic Year</label>
            <select
              value={selectedAyId}
              onChange={(e) => handleAyChange(e.target.value)}
              disabled={loadingAy || generateMutation.isPending}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
            >
              <option value="">Select Academic Year...</option>
              {academicYears.map((ay) => (
                <option key={ay.id} value={ay.id}>
                  {ay.name} {ay.is_current ? '(Current)' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Semester */}
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Semester</label>
            <select
              value={selectedSemId}
              onChange={(e) => handleSemChange(e.target.value)}
              disabled={!selectedAyId || loadingSem || generateMutation.isPending}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-white disabled:bg-slate-100 disabled:text-slate-400"
            >
              <option value="">Select Semester...</option>
              {semesters.map((s) => (
                <option key={s.id} value={s.id}>
                  Semester {s.semester_number} {s.term ? `(${s.term})` : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Department */}
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Department</label>
            <select
              value={selectedDeptId}
              onChange={(e) => handleDeptChange(e.target.value)}
              disabled={!selectedSemId || loadingDept || generateMutation.isPending}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-white disabled:bg-slate-100 disabled:text-slate-400"
            >
              <option value="">Select Department...</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.department_code})
                </option>
              ))}
            </select>
          </div>

          {/* Working Days */}
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Working Days</label>
            <select
              value={workingDays}
              onChange={(e) => setWorkingDays(e.target.value as 'MON_SAT' | 'MON_FRI')}
              disabled={generateMutation.isPending}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
            >
              <option value="MON_SAT">Monday – Saturday (6 Days, Default)</option>
              <option value="MON_FRI">Monday – Friday (5 Days)</option>
            </select>
          </div>
        </div>

        {/* Action Button Bar */}
        {isScopeSelected && (
          <div className="mt-5 pt-4 border-t border-slate-100 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              {isExistingPublished ? (
                <div className="flex items-center gap-2 text-emerald-700 bg-emerald-50 px-3 py-1.5 rounded-lg border border-emerald-200 text-xs font-medium">
                  <CheckCircle2 size={16} className="text-emerald-600" />
                  Canonical Timetable is currently <strong>PUBLISHED</strong> for this scope.
                </div>
              ) : (
                <div className="flex items-center gap-2 text-amber-700 bg-amber-50 px-3 py-1.5 rounded-lg border border-amber-200 text-xs font-medium">
                  <Info size={16} className="text-amber-600" />
                  No published timetable yet for this academic scope.
                </div>
              )}
            </div>

            <div className="flex items-center gap-3">
              {previewData && (
                <button
                  type="button"
                  onClick={() => setPreviewData(null)}
                  disabled={generateMutation.isPending || publishMutation.isPending}
                  className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
                >
                  Discard Preview
                </button>
              )}

              <button
                type="button"
                onClick={handleGenerate}
                disabled={generateMutation.isPending || publishMutation.isPending}
                className={`inline-flex items-center gap-2 px-5 py-2 rounded-lg text-xs font-semibold shadow-sm text-white transition-all ${
                  isExistingPublished
                    ? 'bg-amber-600 hover:bg-amber-700 focus:ring-amber-500'
                    : 'bg-blue-600 hover:bg-blue-700 focus:ring-blue-500'
                } disabled:opacity-50`}
              >
                {generateMutation.isPending ? (
                  <>
                    <Loader2 size={15} className="animate-spin" />
                    Generating Timetable...
                  </>
                ) : (
                  <>
                    <Sparkles size={15} />
                    {isExistingPublished ? 'REGENERATE TIMETABLE' : 'GENERATE TIMETABLE'}
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Success Toast ────────────────────────────────────────────────── */}
      {publishSuccessMsg && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 p-4 rounded-xl flex items-center justify-between animate-fadeIn">
          <div className="flex items-center gap-3">
            <CheckCircle2 size={20} className="text-emerald-600 shrink-0" />
            <p className="text-sm font-medium">{publishSuccessMsg}</p>
          </div>
          <button
            onClick={() => setPublishSuccessMsg(null)}
            className="text-emerald-600 hover:text-emerald-800 text-xs font-semibold"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ── Generation Progress State ───────────────────────────────────── */}
      {generateMutation.isPending && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center space-y-4">
          <div className="inline-flex p-3 rounded-full bg-blue-50 text-blue-600">
            <Loader2 size={32} className="animate-spin" />
          </div>
          <h3 className="text-base font-semibold text-slate-900">Solving Timetable with OR-Tools CP-SAT</h3>
          <p className="text-sm text-slate-500 max-w-md mx-auto">
            Evaluating classroom availability, faculty workload, lab pairings, and student group constraints across sections...
          </p>
          <div className="max-w-xs mx-auto space-y-1 text-xs text-slate-400">
            <p className="flex items-center justify-center gap-1.5 text-blue-600 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse" />
              Verifying 7 instructional periods + tea and lunch breaks
            </p>
          </div>
        </div>
      )}

      {/* ── Preview Validation & Publication Panel ───────────────────────── */}
      {previewData && !generateMutation.isPending && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wider text-purple-700 bg-purple-50 px-2.5 py-1 rounded-md border border-purple-200">
                  Temporary Generated Preview
                </span>
                <span className="text-xs text-slate-500">
                  (Not yet published to students or faculty)
                </span>
              </div>
              <h3 className="text-base font-bold text-slate-900 mt-1">
                Preview for {previewData.department_name} — Semester {previewData.semester_number} ({previewData.academic_year_name})
              </h3>
            </div>

            {/* Validation & Publish Action */}
            <div className="flex items-center gap-3">
              {previewData.can_publish ? (
                <button
                  type="button"
                  onClick={() => setShowPublishModal(true)}
                  disabled={publishMutation.isPending}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 shadow-sm focus:ring-2 focus:ring-emerald-500 transition-all"
                >
                  {publishMutation.isPending ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      Publishing...
                    </>
                  ) : (
                    <>
                      <Send size={16} />
                      PUBLISH TIMETABLE
                    </>
                  )}
                </button>
              ) : (
                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold text-slate-400 bg-slate-100 cursor-not-allowed">
                  <XCircle size={16} className="text-rose-500" />
                  Publish Disabled (Hard Conflicts Detected)
                </div>
              )}
            </div>
          </div>

          {/* Validation Status Banner */}
          {previewData.can_publish ? (
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-xs text-emerald-800 flex items-center justify-between">
              <div className="flex items-center gap-2 font-medium">
                <ShieldCheck size={18} className="text-emerald-600" />
                Validation Passed: Zero hard constraint violations. Schedule is feasible and ready to publish.
              </div>
              <span className="text-emerald-700 font-semibold">{previewData.entries.length} scheduled periods</span>
            </div>
          ) : (
            <div className="bg-rose-50 border border-rose-200 rounded-lg p-3 text-xs text-rose-800 space-y-2">
              <div className="flex items-center gap-2 font-bold">
                <AlertTriangle size={18} className="text-rose-600" />
                Validation Failed: {previewData.blocker_count} hard blocker conflict(s) must be resolved.
              </div>
              <ul className="list-disc list-inside space-y-1 pl-2 text-rose-700">
                {previewData.violations
                  .filter((v) => v.severity === 'BLOCKER')
                  .map((v, idx) => (
                    <li key={idx}>
                      <strong>{v.rule}:</strong> {v.message}
                    </li>
                  ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* ── Main Timetable View ─────────────────────────────────────────── */}
      {isScopeSelected && (previewData || isExistingPublished) && !generateMutation.isPending && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          {/* Section Selector Tabs */}
          <div className="bg-slate-50 border-b border-slate-200 px-4 py-2.5 flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-1.5 overflow-x-auto py-1">
              <span className="text-xs font-semibold text-slate-500 mr-2 uppercase tracking-wide">
                Sections:
              </span>
              {sections.map((sec) => {
                const isActive = currentSectionId === sec.id;
                return (
                  <button
                    key={sec.id}
                    onClick={() => setActiveSectionId(sec.id)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      isActive
                        ? 'bg-blue-600 text-white shadow-sm'
                        : 'bg-white text-slate-700 hover:bg-slate-200 border border-slate-200'
                    }`}
                  >
                    {sec.section_name}
                  </button>
                );
              })}
            </div>

            <div className="text-xs text-slate-500">
              {previewData ? (
                <span className="text-purple-700 font-medium">Viewing Preview Data</span>
              ) : (
                <span className="text-emerald-700 font-medium">Viewing Published Canonical Timetable</span>
              )}
            </div>
          </div>

          {/* Grid Container */}
          <div className="overflow-x-auto p-4 pb-8">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="bg-slate-100 border-b border-slate-300">
                  <th className="p-3.5 font-bold text-slate-800 w-28 uppercase tracking-wider text-xs">
                    Day / Time
                  </th>
                  {TIME_COLUMNS.map((col) => (
                    <th
                      key={col.key}
                      className={`p-3 font-bold text-center border-l border-slate-200 tracking-tight ${
                        col.isBreak
                          ? 'bg-amber-50/90 text-amber-900 w-28'
                          : 'text-slate-900 min-w-[150px]'
                      }`}
                    >
                      <div className="text-xs font-bold font-tabular text-slate-900 leading-snug">
                        {col.timeLabel}
                      </div>
                      <div className="text-[10px] font-medium text-slate-500 mt-0.5">
                        {col.name}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {displayDays.map((day, dIdx) => (
                  <tr
                    key={day}
                    className={`hover:bg-slate-50/50 transition-colors ${
                      dIdx === displayDays.length - 1 ? 'border-b-2 border-slate-300' : ''
                    }`}
                  >
                    {/* Day Column */}
                    <td className="p-3.5 font-extrabold text-slate-800 bg-slate-50/90 border-r border-slate-200 uppercase tracking-wide text-xs align-top">
                      {DAY_LABELS[day]}
                    </td>

                    {/* Periods */}
                    {TIME_COLUMNS.map((col) => {
                      if (col.isBreak) {
                        return (
                          <td
                            key={col.key}
                            className="bg-amber-50/40 text-center text-[11px] font-bold text-amber-800/70 border-l border-slate-200 select-none align-middle p-2"
                          >
                            <span className="block px-2 py-1 rounded bg-amber-100/50 font-semibold uppercase tracking-wider text-[10px]">
                              {col.name}
                            </span>
                          </td>
                        );
                      }

                      const entriesInSlot = timetableMatrix[day][`${col.start}-${col.end}`] || [];

                      return (
                        <td
                          key={col.key}
                          className="p-2 border-l border-slate-200 align-top min-h-[110px]"
                        >
                          {entriesInSlot.length > 0 ? (
                            <div className="space-y-2">
                              {entriesInSlot.map((entry, idx) => {
                                const isPractical =
                                  entry.hour_type === 'PRACTICAL' ||
                                  entry.hour_type === 'LAB';
                                return (
                                  <div
                                    key={`${entry.course_code}-${entry.start_time}-${entry.day}-${idx}`}
                                    className={`p-2.5 rounded-lg border text-xs shadow-2xs transition-all ${
                                      entriesInSlot.length > 1
                                        ? 'bg-amber-50 border-amber-300 ring-1 ring-amber-400'
                                        : isPractical
                                        ? 'bg-indigo-50/90 border-indigo-200 text-indigo-950'
                                        : 'bg-blue-50/90 border-blue-200 text-blue-950'
                                    }`}
                                  >
                                    {entriesInSlot.length > 1 && (
                                      <div className="mb-1 inline-flex items-center gap-1 text-[10px] font-bold text-amber-800 bg-amber-100 px-1.5 py-0.5 rounded">
                                        Slot Conflict #{idx + 1}
                                      </div>
                                    )}
                                    <div className="flex items-start justify-between gap-1 mb-1">
                                      <span className="font-extrabold text-[12px] text-slate-900 tracking-tight">
                                        {entry.course_code}
                                      </span>
                                      <span
                                        className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${
                                          isPractical
                                            ? 'bg-indigo-200 text-indigo-900'
                                            : 'bg-blue-200 text-blue-900'
                                        }`}
                                      >
                                        Class Type: {entry.hour_type === 'PRACTICAL' ? 'Lab / Practical' : entry.hour_type || 'Theory'}
                                      </span>
                                    </div>

                                    {/* Complete Subject Title - wrapped, NO line-clamp, NO truncation */}
                                    <div className="text-[11px] font-medium text-slate-800 leading-snug mb-2 break-words">
                                      {entry.course_name}
                                    </div>

                                    <div className="pt-1.5 border-t border-slate-200/80 text-[11px] text-slate-700 space-y-1">
                                      <div className="flex items-start gap-1">
                                        <span className="text-slate-500 font-normal shrink-0">Faculty:</span>
                                        <span className="font-semibold text-slate-900 break-words">
                                          {entry.faculty_name || 'Unassigned'}
                                        </span>
                                      </div>
                                      <div className="flex items-center gap-1">
                                        <span className="text-slate-500 font-normal">Room No.:</span>
                                        <span className="font-bold text-slate-900">
                                          {entry.room_number || 'TBD'}
                                        </span>
                                      </div>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="min-h-[85px] flex items-center justify-center text-slate-300 text-xs italic">
                              —
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Empty State ─────────────────────────────────────────────────── */}
      {isScopeSelected && !isExistingPublished && !previewData && !generateMutation.isPending && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-12 text-center space-y-3">
          <div className="inline-flex p-3 rounded-full bg-slate-100 text-slate-400">
            <CalendarDays size={28} />
          </div>
          <h3 className="text-base font-semibold text-slate-900">No Timetable Published Yet</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Click <strong>GENERATE TIMETABLE</strong> above to calculate optimal class schedules and room assignments for all sections.
          </p>
        </div>
      )}

      {/* ── Publish Confirmation Modal ───────────────────────────────────── */}
      {showPublishModal && previewData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4 animate-scaleUp">
            <div className="flex items-center gap-3 text-emerald-600">
              <div className="p-2 rounded-full bg-emerald-50">
                <CheckCircle2 size={24} />
              </div>
              <h3 className="text-base font-bold text-slate-900">Publish Canonical Timetable?</h3>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              This will publish the generated schedule as the <strong>single canonical timetable</strong> for{' '}
              <strong>{previewData.department_name} (Semester {previewData.semester_number})</strong>.
            </p>

            <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 text-xs space-y-1 text-slate-700">
              <div className="flex justify-between">
                <span>Sections Included:</span>
                <span className="font-semibold">{previewData.sections.length}</span>
              </div>
              <div className="flex justify-between">
                <span>Total Classes:</span>
                <span className="font-semibold">{previewData.entries.length}</span>
              </div>
              <div className="flex justify-between">
                <span>Hard Constraint Violations:</span>
                <span className="font-semibold text-emerald-600">0 (Passed)</span>
              </div>
            </div>

            <p className="text-[11px] text-amber-700 bg-amber-50 p-2.5 rounded-lg border border-amber-200">
              Note: Once published, students and faculty can immediately view this schedule on their dashboards. Any previously published schedule for this scope will be transactionally replaced.
            </p>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowPublishModal(false)}
                disabled={publishMutation.isPending}
                className="px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => publishMutation.mutate()}
                disabled={publishMutation.isPending}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg shadow-sm transition-all"
              >
                {publishMutation.isPending ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Publishing...
                  </>
                ) : (
                  'Confirm & Publish'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
