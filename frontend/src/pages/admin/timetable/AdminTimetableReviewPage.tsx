import React, { useMemo, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import {
  ArrowLeft,
  CheckCircle2,
  ShieldCheck,
  Send,
  Loader2,
  AlertCircle,
  Lock,
  Edit3,
  Save,
  Undo2,
  Redo2,
  RotateCcw,
  History,
  GitBranch,
  Wifi,
  WifiOff,
  RefreshCw,
} from 'lucide-react';

import {
  getTimetableVersion,
  validateTimetableVersion,
  publishTimetableVersion,
  approveTimetableVersion,
  getTimetableCoordinators,
  getMoveOptions,
  validateArrangements,
  saveArrangements,
  createTimetableRevision,
  getTimetableChangeHistory,
  type MoveOptionSlot,
  type ProposedMoveItem,
  type TimetableEntryDetailResponse,
  type ValidationResult,
  type PublishPreflightResponse,
} from '@/api/timetable';
import { academicYearsApi } from '@/api/academicYears';
import { semestersApi } from '@/api/semesters';
import { departmentsApi } from '@/api/departments';
import { programsApi } from '@/api/programs';
import { getTimeSlots } from '@/api/timeSlots';
import { getCourseAssignments } from '@/api/courseAssignments';
import { coursesApi } from '@/api/courses';
import { facultyApi } from '@/api/faculty';
import { roomsApi } from '@/api/rooms';
import { TimetableGrid } from '@/components/timetable/TimetableGrid';
import { ValidationResultDisplay } from '@/components/timetable/ValidationResultDisplay';
import { PageHeader, StatusBadge, LoadingState, ErrorState } from '@/components/common';
import { useTimetableSync } from '@/hooks/useTimetableSync';

const extractErrorMessage = (err: unknown, fallback: string): string => {
  if (isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object' && 'message' in detail) {
      return String((detail as { message?: unknown }).message || fallback);
    }
  }
  return err instanceof Error ? err.message : fallback;
};

export const AdminTimetableReviewPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const versionId = Number(id);

  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [errorStatus, setErrorStatus] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [showCoordinatorModal, setShowCoordinatorModal] = useState(false);
  const [showApproveModal, setShowApproveModal] = useState(false);

  const notifySuccess = (msg: string) => {
    setStatusMessage(msg);
  };
  const notifyError = (msg: string) => {
    setErrorStatus('ERROR');
    setErrorMessage(msg);
  };

  // Smart Editor State
  const [isEditMode, setIsEditMode] = useState(false);
  const [pendingMoves, setPendingMoves] = useState<Record<number, ProposedMoveItem>>({});
  const [undoStack, setUndoStack] = useState<Record<number, ProposedMoveItem>[]>([]);
  const [redoStack, setRedoStack] = useState<Record<number, ProposedMoveItem>[]>([]);
  const [moveOptionsMap, setMoveOptionsMap] = useState<Record<number, MoveOptionSlot>>({});
  const [highlightedEntryIds, setHighlightedEntryIds] = useState<Set<number>>(new Set());
  const [showHistory, setShowHistory] = useState(false);

  // Filters
  const [selectedSectionId, setSelectedSectionId] = useState<number | 'ALL'>('ALL');
  const [selectedDay, setSelectedDay] = useState<string>('ALL');
  const [selectedFacultyId, setSelectedFacultyId] = useState<number | 'ALL'>('ALL');
  const [selectedCourseId, setSelectedCourseId] = useState<number | 'ALL'>('ALL');

  // Fetch Version Data
  const {
    data: version,
    isLoading: isVersionLoading,
    isError: isVersionError,
    refetch: refetchVersion,
  } = useQuery({
    queryKey: ['timetable', 'version', versionId],
    queryFn: () => getTimetableVersion(versionId),
    enabled: Number.isFinite(versionId) && versionId > 0,
  });

  // Real-time WebSocket + polling fallback sync
  const { connectionStatus, remoteNotice, clearRemoteNotice } = useTimetableSync({
    versionId: Number.isFinite(versionId) && versionId > 0 ? versionId : null,
    enabled: Boolean(version),
    onRemoteUpdate: useCallback(() => {
      if (Object.keys(pendingMoves).length === 0) {
        queryClient.invalidateQueries({ queryKey: ['timetable', 'version', versionId] });
      }
    }, [pendingMoves, queryClient, versionId]),
    onPollTick: useCallback(() => {
      if (Object.keys(pendingMoves).length === 0) {
        queryClient.invalidateQueries({ queryKey: ['timetable', 'version', versionId] });
      }
    }, [pendingMoves, queryClient, versionId]),
  });

  // Contextual Lookups
  const { data: academicYears } = useQuery({ queryKey: ['academicYears'], queryFn: academicYearsApi.getAll });
  const { data: semesters } = useQuery({ queryKey: ['semesters'], queryFn: semestersApi.getAll });
  const { data: departments } = useQuery({ queryKey: ['departments'], queryFn: departmentsApi.getAll });
  const { data: programs } = useQuery({ queryKey: ['programs'], queryFn: programsApi.getAll });
  const { data: timeSlots } = useQuery({ queryKey: ['timeSlots'], queryFn: getTimeSlots });
  const { data: assignments } = useQuery({ queryKey: ['courseAssignments'], queryFn: getCourseAssignments });
  const { data: courses } = useQuery({ queryKey: ['courses'], queryFn: coursesApi.getAll });
  const { data: facultyList } = useQuery({ queryKey: ['faculty'], queryFn: facultyApi.getAll });
  const { data: rooms } = useQuery({ queryKey: ['rooms'], queryFn: roomsApi.getAll });

  const { data: changeHistory, refetch: refetchHistory } = useQuery({
    queryKey: ['timetable', 'version', versionId, 'history'],
    queryFn: () => getTimetableChangeHistory(versionId),
    enabled: showHistory && Number.isFinite(versionId) && versionId > 0,
  });

  const clearError = () => {
    setErrorStatus('');
    setErrorMessage('');
  };

  // Mutations
  const saveMutation = useMutation({
    mutationFn: () =>
      saveArrangements(
        versionId,
        version?.revision ?? 1,
        Object.values(pendingMoves),
      ),
    onSuccess: (res) => {
      clearError();
      setPendingMoves({});
      setUndoStack([]);
      setRedoStack([]);
      setMoveOptionsMap({});
      setValidationResult(res.validation_result);
      queryClient.invalidateQueries({ queryKey: ['timetable', 'version', versionId] });
      queryClient.invalidateQueries({ queryKey: ['timetable', 'versions'] });
      if (showHistory) refetchHistory();
      notifySuccess(`Saved changes (Revision ${res.revision}). Revalidate before finalizing.`);
    },
    onError: (err) => {
      const msg = extractErrorMessage(err, 'Failed to save timetable changes.');
      notifyError(msg);
    },
  });

  const validateMutation = useMutation({
    mutationFn: () => validateTimetableVersion(versionId),
    onSuccess: (res) => {
      clearError();
      setValidationResult(res);
      queryClient.invalidateQueries({ queryKey: ['timetable', 'version', versionId] });
      queryClient.invalidateQueries({ queryKey: ['timetable', 'versions'] });
      if (res.is_valid) {
        notifySuccess('Validation passed with 0 hard conflicts.');
      } else {
        notifyError(`Validation found ${res.blocker_count ?? 1} conflict(s).`);
      }
    },
    onError: (err) => {
      notifyError(extractErrorMessage(err, 'Validation engine failed.'));
    },
  });

  const approveMutation = useMutation({
    mutationFn: () => approveTimetableVersion(versionId),
    onSuccess: (data) => {
      notifySuccess(data.message || 'Timetable approved successfully.');
      queryClient.invalidateQueries({ queryKey: ['timetable', 'version', versionId] });
      queryClient.invalidateQueries({ queryKey: ['timetable', 'versions'] });
      setShowApproveModal(false);
    },
    onError: (err) => {
      notifyError(extractErrorMessage(err, 'Failed to approve timetable.'));
    },
  });

  const {
    data: preflightData,
    isLoading: loadingPreflight,
  } = useQuery<PublishPreflightResponse>({
    queryKey: ['timetable', 'coordinators', versionId],
    queryFn: () => getTimetableCoordinators(versionId),
    enabled: showCoordinatorModal && Number.isFinite(versionId) && versionId > 0,
  });

  const publishMutation = useMutation({
    mutationFn: () => publishTimetableVersion(versionId),
    onSuccess: () => {
      clearError();
      setIsEditMode(false);
      setShowCoordinatorModal(false);
      queryClient.invalidateQueries({ queryKey: ['timetable', 'version', versionId] });
      queryClient.invalidateQueries({ queryKey: ['timetable', 'versions'] });
      queryClient.invalidateQueries({ queryKey: ['timetable-canonical'] });
      notifySuccess('Timetable published to related coordinators, student & faculty portals.');
    },
    onError: (err) => {
      notifyError(extractErrorMessage(err, 'Publication failed.'));
    },
  });

  const reviseMutation = useMutation({
    mutationFn: () => createTimetableRevision(versionId),
    onSuccess: (newVer) => {
      notifySuccess(`Created draft Revision Version V${newVer.id}.`);
      navigate(`/admin/timetable/versions/${newVer.id}`);
    },
    onError: (err) => {
      notifyError(extractErrorMessage(err, 'Failed to create new revision.'));
    },
  });

  // Derived entries with optimistic local pending moves applied
  const workingEntries = useMemo<TimetableEntryDetailResponse[]>(() => {
    if (!version?.timetable_entries) return [];
    const slotById = new Map((timeSlots || []).map((s) => [s.id, s]));
    const roomById = new Map((rooms || []).map((r) => [r.id, r]));

    return version.timetable_entries.map((entry) => {
      const move = pendingMoves[entry.id];
      if (!move) return entry;
      const newSlot = slotById.get(move.target_slot_id);
      const newRoom = move.target_room_id ? roomById.get(move.target_room_id) : undefined;
      return {
        ...entry,
        slot_id: move.target_slot_id,
        room_id: move.target_room_id ?? entry.room_id,
        faculty_id: move.target_faculty_id ?? entry.faculty_id,
        day: newSlot?.day ?? entry.day,
        start_time: newSlot?.start_time?.slice(0, 5) ?? entry.start_time,
        end_time: newSlot?.end_time?.slice(0, 5) ?? entry.end_time,
        room_number: newRoom?.room_number ?? entry.room_number,
      };
    });
  }, [version, pendingMoves, timeSlots, rooms]);

  // Available sections, faculty, courses for filter dropdowns
  const sectionOptions = useMemo(() => {
    const map = new Map<number, string>();
    workingEntries.forEach((e) => {
      if (e.section_id) map.set(e.section_id, e.section_name || `Section ${e.section_id}`);
    });
    return Array.from(map.entries()).map(([sid, name]) => ({ id: sid, name }));
  }, [workingEntries]);

  const facultyOptions = useMemo(() => {
    const map = new Map<number, string>();
    workingEntries.forEach((e) => {
      if (e.faculty_id) map.set(e.faculty_id, e.faculty_name || `Faculty ${e.faculty_id}`);
    });
    return Array.from(map.entries()).map(([fid, name]) => ({ id: fid, name }));
  }, [workingEntries]);

  const courseOptions = useMemo(() => {
    const map = new Map<number, string>();
    workingEntries.forEach((e) => {
      if (e.course_id) map.set(e.course_id, `${e.course_code || ''} ${e.course_name || ''}`.trim());
    });
    return Array.from(map.entries()).map(([cid, name]) => ({ id: cid, name }));
  }, [workingEntries]);

  const filteredEntries = useMemo(() => {
    return workingEntries.filter((e) => {
      if (selectedSectionId !== 'ALL' && e.section_id !== selectedSectionId) return false;
      if (selectedDay !== 'ALL' && (e.day || '').toUpperCase().slice(0, 3) !== selectedDay) return false;
      if (selectedFacultyId !== 'ALL' && e.faculty_id !== selectedFacultyId) return false;
      if (selectedCourseId !== 'ALL' && e.course_id !== selectedCourseId) return false;
      return true;
    });
  }, [workingEntries, selectedSectionId, selectedDay, selectedFacultyId, selectedCourseId]);

  // 7 Live Summary Metrics
  const summaryMetrics = useMemo(() => {
    const total = workingEntries.length;
    const sectionsCount = new Set(workingEntries.map((e) => e.section_id).filter(Boolean)).size;
    const facultyCount = new Set(workingEntries.map((e) => e.faculty_id).filter(Boolean)).size;
    const roomsCount = new Set(workingEntries.map((e) => e.room_id).filter(Boolean)).size;
    const practicalCount = workingEntries.filter((e) => e.hour_type === 'PRACTICAL' || e.course_type === 'LAB').length;
    const theoryCount = total - practicalCount;
    const rawScore = version?.score_summary && typeof version.score_summary.total_score === 'number'
      ? Math.round(version.score_summary.total_score as number)
      : null;
    return { total, sectionsCount, facultyCount, roomsCount, theoryCount, practicalCount, rawScore };
  }, [workingEntries, version]);

  const pendingCount = Object.keys(pendingMoves).length;
  const pendingEntryIds = useMemo(() => new Set(Object.keys(pendingMoves).map(Number)), [pendingMoves]);

  // Drag & Drop handlers
  const handleDragStartEntry = useCallback(async (entryId: number) => {
    try {
      const res = await getMoveOptions(versionId, entryId);
      const map: Record<number, MoveOptionSlot> = {};
      res.slots.forEach((s) => {
        map[s.slot_id] = s;
      });
      setMoveOptionsMap(map);
    } catch (err) {
      notifyError(extractErrorMessage(err, 'Failed to check slot availability.'));
    }
  }, [versionId]);

  const handleDropOnSlot = useCallback(async (entryId: number, targetSlotId: number, slotOption?: MoveOptionSlot) => {
    setMoveOptionsMap({});
    const entry = workingEntries.find((e) => e.id === entryId);
    if (!entry || entry.slot_id === targetSlotId) return;

    if (slotOption && slotOption.status === 'BLOCKED') {
      const reason = slotOption.reasons.join('; ') || 'Target slot is blocked due to a conflict.';
      setErrorStatus('BLOCKED');
      setErrorMessage(reason);
      return;
    }

    const nextMoves: Record<number, ProposedMoveItem> = { ...pendingMoves };
    const chosenRoomId = slotOption?.alternative_rooms?.[0]?.room_id ?? entry.room_id;

    // Multi-period block support
    if (entry.block_group_id && slotOption && slotOption.block_target_slot_ids.length > 1) {
      const groupEntries = workingEntries
        .filter((e) => e.block_group_id === entry.block_group_id)
        .sort((a, b) => (a.start_time || '').localeCompare(b.start_time || ''));
      if (groupEntries.length === slotOption.block_target_slot_ids.length) {
        groupEntries.forEach((ge, idx) => {
          nextMoves[ge.id] = {
            entry_id: ge.id,
            target_slot_id: slotOption.block_target_slot_ids[idx],
            target_room_id: chosenRoomId ?? undefined,
          };
        });
      } else {
        nextMoves[entryId] = {
          entry_id: entryId,
          target_slot_id: targetSlotId,
          target_room_id: chosenRoomId ?? undefined,
        };
      }
    } else {
      nextMoves[entryId] = {
        entry_id: entryId,
        target_slot_id: targetSlotId,
        target_room_id: chosenRoomId ?? undefined,
      };
    }

    try {
      const valRes = await validateArrangements(versionId, Object.values(nextMoves));
      if (!valRes.can_save) {
        const blockedReasons = valRes.move_outcomes
          .filter((m) => m.status === 'BLOCKED')
          .flatMap((m) => m.reasons);
        const msg = blockedReasons.join('; ') || 'Proposed move violates timetable constraints.';
        setErrorStatus('BLOCKED');
        setErrorMessage(msg);
        return;
      }

      clearError();
      setUndoStack((prev) => [...prev, pendingMoves]);
      setRedoStack([]);
      setPendingMoves(nextMoves);
      setValidationResult(valRes.validation_result);
      notifySuccess('Class moved in draft. Click "Save Changes" to persist.');
    } catch (err) {
      notifyError(extractErrorMessage(err, 'Failed to validate move.'));
    }
  }, [pendingMoves, versionId, workingEntries]);

  const handleUndo = () => {
    if (undoStack.length === 0) return;
    const prev = undoStack[undoStack.length - 1];
    setRedoStack((r) => [...r, pendingMoves]);
    setUndoStack((u) => u.slice(0, -1));
    setPendingMoves(prev);
  };

  const handleRedo = () => {
    if (redoStack.length === 0) return;
    const next = redoStack[redoStack.length - 1];
    setUndoStack((u) => [...u, pendingMoves]);
    setRedoStack((r) => r.slice(0, -1));
    setPendingMoves(next);
  };

  const handleDiscard = () => {
    setPendingMoves({});
    setUndoStack([]);
    setRedoStack([]);
    setMoveOptionsMap({});
    clearError();
    notifySuccess('Discarded unsaved arrangement changes.');
  };

  if (isVersionLoading) {
    return <LoadingState message={`Loading Timetable Version V${versionId}...`} />;
  }

  if (isVersionError || !version) {
    return (
      <ErrorState
        title="Version Not Found"
        message={`Unable to load timetable version #${versionId}.`}
        onRetry={() => refetchVersion()}
      />
    );
  }

  const firstEntry = version.timetable_entries?.[0];
  const deptName =
    departments?.find((d) => d.id === (version.department_id ?? firstEntry?.department_id))?.name ||
    version.department_name ||
    'Department';
  const progName =
    programs?.find((p) => p.id === (version.program_id ?? firstEntry?.program_id))?.program_name ||
    version.program_name ||
    'Program';
  const semNum =
    semesters?.find((s) => s.id === (version.semester_id ?? firstEntry?.semester_id))?.semester_number ??
    version.semester_number;
  const semName = semNum ? `Semester ${semNum}` : 'Semester N/A';
  const ayName =
    academicYears?.find((ay) => ay.id === version.academic_year_id)?.year_name ||
    version.academic_year_name ||
    'Academic Year';

  const getStatusBadge = (statusVal?: string | null) => {
    switch (statusVal) {
      case 'GENERATED':
        return <StatusBadge label="GENERATED — UNPUBLISHED" variant="info" size="md" />;
      case 'REVIEWED':
        return <StatusBadge label="REVIEWED — UNPUBLISHED" variant="warning" size="md" />;
      case 'VALIDATED':
        return <StatusBadge label="VALIDATED — UNPUBLISHED" variant="info" size="md" />;
      case 'FINALIZED':
      case 'APPROVED':
        return <StatusBadge label="APPROVED — READY TO PUBLISH" variant="success" size="md" />;
      case 'PUBLISHED':
        return <StatusBadge label="PUBLISHED" variant="success" size="md" dot />;
      case 'ARCHIVED':
        return <StatusBadge label="ARCHIVED" variant="neutral" size="md" />;
      default:
        return <StatusBadge label={statusVal || 'UNKNOWN'} variant="neutral" size="md" />;
    }
  };

  const isEditable =
    version.status === 'GENERATED' ||
    version.status === 'REVIEWED' ||
    version.status === 'VALIDATED' ||
    version.status === 'APPROVED' ||
    version.status === 'FINALIZED';
  const currentRevision = version.revision ?? 1;
  const isValidatedAtCurrentRev = version.validated_revision === currentRevision;

  return (
    <div className="space-y-6">
      {/* Header & Lifecycle Actions */}
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            onClick={() => navigate('/admin/timetable/versions')}
            className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors"
          >
            <ArrowLeft size={14} />
            <span>Back to All Timetable Versions</span>
          </button>

          <div className="flex flex-wrap items-center gap-2">
            {/* Sync Connection Pill */}
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border ${connectionStatus === 'connected'
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : connectionStatus === 'polling'
                  ? 'bg-amber-50 text-amber-700 border-amber-200'
                  : 'bg-slate-100 text-slate-600 border-slate-200'
                }`}
            >
              {connectionStatus === 'connected' ? <Wifi size={12} /> : <WifiOff size={12} />}
              <span>
                {connectionStatus === 'connected'
                  ? 'Live Sync'
                  : connectionStatus === 'polling'
                    ? 'Polling Sync'
                    : 'Syncing...'}
              </span>
            </span>

            <span className="px-2.5 py-1 rounded-full text-[11px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
              Rev {currentRevision}
            </span>

            {getStatusBadge(version.status)}
          </div>
        </div>

        {/* Remote Update Banner */}
        {remoteNotice && (
          <div className="bg-sky-50 border border-sky-200 rounded-xl p-3 flex items-center justify-between text-xs text-sky-900">
            <div className="flex items-center gap-2">
              <RefreshCw size={14} className="text-sky-600" />
              <span>
                Updated by <strong>{remoteNotice.actor_name || 'another admin'}</strong> (Rev{' '}
                {remoteNotice.revision ?? '?'}) — status: <strong>{remoteNotice.status}</strong>.
              </span>
            </div>
            <button
              onClick={() => {
                clearRemoteNotice();
                refetchVersion();
              }}
              className="px-2.5 py-1 rounded-lg bg-sky-600 text-white font-semibold hover:bg-sky-700"
            >
              Reload Latest
            </button>
          </div>
        )}

        <PageHeader
          title={`Timetable Review & Arrangement • V${version.id}`}
          subtitle={`${deptName} • ${progName} • ${semName} (${ayName})`}
          breadcrumbs={[
            { label: 'Admin', href: '/admin' },
            { label: 'Timetable', href: '/admin/timetable/versions' },
            { label: `Version V${version.id}` },
          ]}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              {isEditable && (
                <button
                  onClick={() => setIsEditMode((v) => !v)}
                  data-testid="toggle-edit-mode-btn"
                  className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold border transition-colors ${isEditMode
                    ? 'bg-indigo-600 text-white border-indigo-600'
                    : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'
                    }`}
                >
                  <Edit3 size={14} />
                  <span>{isEditMode ? 'Exit Edit Mode' : 'Edit Timetable'}</span>
                </button>
              )}

              <button
                onClick={() => setShowHistory((v) => !v)}
                className="academic-btn-secondary inline-flex items-center gap-1.5 text-xs font-semibold"
              >
                <History size={14} />
                <span>History</span>
              </button>

              {isEditable && (
                <button
                  onClick={() => validateMutation.mutate()}
                  disabled={validateMutation.isPending || pendingCount > 0}
                  title={pendingCount > 0 ? 'Save or discard pending changes before validating' : undefined}
                  className="academic-btn-secondary inline-flex items-center gap-1.5 text-xs font-semibold disabled:opacity-50"
                >
                  {validateMutation.isPending ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <ShieldCheck size={15} className="text-primary-600" />
                  )}
                  <span>{version.status === 'REVIEWED' || !isValidatedAtCurrentRev ? 'Revalidate' : 'Validate'}</span>
                </button>
              )}

              {/* Approve Timetable Button */}
              {version.status === 'VALIDATED' && isValidatedAtCurrentRev && pendingCount === 0 && (
                <button
                  onClick={() => setShowApproveModal(true)}
                  disabled={approveMutation.isPending}
                  data-testid="approve-btn"
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition-colors"
                >
                  {approveMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={15} />}
                  <span>Approve Timetable</span>
                </button>
              )}

              {/* Publish to Coordinators Button */}
              {(version.status === 'APPROVED' || version.status === 'FINALIZED') && pendingCount === 0 && (
                <button
                  onClick={() => setShowCoordinatorModal(true)}
                  disabled={publishMutation.isPending}
                  data-testid="publish-btn"
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-teal-600 hover:bg-teal-700 text-white shadow-sm transition-colors"
                >
                  <Send size={15} />
                  <span>Publish to Coordinators</span>
                </button>
              )}

              {(version.status === 'PUBLISHED' || version.status === 'FINALIZED' || version.status === 'ARCHIVED') && (
                <button
                  onClick={() => reviseMutation.mutate()}
                  disabled={reviseMutation.isPending}
                  className="academic-btn-secondary inline-flex items-center gap-1.5 text-xs font-semibold"
                >
                  {reviseMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <GitBranch size={14} />}
                  <span>Create New Revision</span>
                </button>
              )}
            </div>
          }
        />
      </div>

      {/* Edit Mode Toolbar */}
      {isEditMode && isEditable && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3">
          <div className="text-xs text-indigo-950">
            <span className="font-bold">Drag-and-Drop Arrangement Mode:</span>{' '}
            {pendingCount > 0 ? (
              <span className="font-semibold text-amber-800">
                You have {pendingCount} unsaved timetable change{pendingCount > 1 ? 's' : ''}.
              </span>
            ) : (
              <span>Drag any class card to a green highlighted slot to rearrange.</span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handleUndo}
              disabled={undoStack.length === 0}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-white border border-slate-300 text-slate-700 disabled:opacity-40"
            >
              <Undo2 size={13} />
              <span>Undo</span>
            </button>
            <button
              onClick={handleRedo}
              disabled={redoStack.length === 0}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-white border border-slate-300 text-slate-700 disabled:opacity-40"
            >
              <Redo2 size={13} />
              <span>Redo</span>
            </button>
            <button
              onClick={handleDiscard}
              disabled={pendingCount === 0}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-white border border-slate-300 text-slate-700 disabled:opacity-40"
            >
              <RotateCcw size={13} />
              <span>Discard</span>
            </button>
            <button
              onClick={() => saveMutation.mutate()}
              disabled={pendingCount === 0 || saveMutation.isPending}
              data-testid="save-arrangements-btn"
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-40"
            >
              {saveMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
              <span>Save Changes ({pendingCount})</span>
            </button>
          </div>
        </div>
      )}

      {/* 7 Live Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 text-xs">
        <div className="bg-white rounded-xl border border-slate-200 p-3">
          <div className="text-[10px] font-semibold text-slate-500 uppercase">Total Classes</div>
          <div className="text-lg font-bold text-slate-900 mt-0.5">{summaryMetrics.total}</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-3">
          <div className="text-[10px] font-semibold text-slate-500 uppercase">Sections</div>
          <div className="text-lg font-bold text-slate-900 mt-0.5">{summaryMetrics.sectionsCount}</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-3">
          <div className="text-[10px] font-semibold text-slate-500 uppercase">Active Faculty</div>
          <div className="text-lg font-bold text-slate-900 mt-0.5">{summaryMetrics.facultyCount}</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-3">
          <div className="text-[10px] font-semibold text-slate-500 uppercase">Rooms Used</div>
          <div className="text-lg font-bold text-slate-900 mt-0.5">{summaryMetrics.roomsCount}</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-3">
          <div className="text-[10px] font-semibold text-slate-500 uppercase">Theory / Lab</div>
          <div className="text-lg font-bold text-slate-900 mt-0.5">
            {summaryMetrics.theoryCount} / {summaryMetrics.practicalCount}
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-3">
          <div className="text-[10px] font-semibold text-slate-500 uppercase">Quality Score</div>
          <div className="text-lg font-bold text-slate-900 mt-0.5">
            {summaryMetrics.rawScore !== null ? summaryMetrics.rawScore : '—'}
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-3">
          <div className="text-[10px] font-semibold text-slate-500 uppercase">Validation</div>
          <div className="text-xs font-bold mt-1 flex items-center gap-1">
            {isValidatedAtCurrentRev && pendingCount === 0 ? (
              <span className="text-emerald-700">Valid (Rev {currentRevision})</span>
            ) : (
              <span className="text-amber-700 inline-flex items-center gap-1">
                {!isEditable && <Lock size={12} />}
                Needs Validation
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="bg-white rounded-xl border border-slate-200 p-3 flex flex-wrap items-center gap-3 text-xs">
        <span className="font-semibold text-slate-600">Filters:</span>
        <select
          value={selectedSectionId}
          onChange={(e) => setSelectedSectionId(e.target.value === 'ALL' ? 'ALL' : Number(e.target.value))}
          className="academic-input py-1.5 text-xs max-w-[180px]"
        >
          <option value="ALL">All Sections ({sectionOptions.length})</option>
          {sectionOptions.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>

        <select
          value={selectedDay}
          onChange={(e) => setSelectedDay(e.target.value)}
          className="academic-input py-1.5 text-xs max-w-[140px]"
        >
          <option value="ALL">All Days</option>
          {['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'].map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        <select
          value={selectedFacultyId}
          onChange={(e) => setSelectedFacultyId(e.target.value === 'ALL' ? 'ALL' : Number(e.target.value))}
          className="academic-input py-1.5 text-xs max-w-[200px]"
        >
          <option value="ALL">All Faculty</option>
          {facultyOptions.map((f) => (
            <option key={f.id} value={f.id}>{f.name}</option>
          ))}
        </select>

        <select
          value={selectedCourseId}
          onChange={(e) => setSelectedCourseId(e.target.value === 'ALL' ? 'ALL' : Number(e.target.value))}
          className="academic-input py-1.5 text-xs max-w-[220px]"
        >
          <option value="ALL">All Courses</option>
          {courseOptions.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      </div>

      {/* Success Banner */}
      {statusMessage && (
        <div className="bg-emerald-50 border border-emerald-200 p-3.5 rounded-xl flex items-center justify-between gap-3 text-emerald-900 shadow-xs text-xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
            <span className="font-medium">{statusMessage}</span>
          </div>
          <button
            onClick={() => setStatusMessage('')}
            className="text-emerald-700 hover:text-emerald-950 font-semibold"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Error Banner */}
      {errorStatus && (
        <div className="bg-rose-50 border border-rose-200 p-4 rounded-xl flex items-start gap-3 text-rose-900 shadow-xs">
          <AlertCircle size={18} className="text-rose-600 shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm font-semibold">Action Encountered an Error</h4>
            <p className="text-xs text-rose-800 mt-0.5">{errorMessage}</p>
          </div>
        </div>
      )}

      {/* Validation Result Panel */}
      {validationResult && (
        <div className="space-y-2">
          <ValidationResultDisplay result={validationResult} />
          {validationResult.violations.some((v) => v.entry_ids && v.entry_ids.length > 0) && (
            <div className="flex flex-wrap gap-2">
              {validationResult.violations
                .filter((v) => v.entry_ids && v.entry_ids.length > 0)
                .map((v, i) => (
                  <button
                    key={i}
                    onClick={() => setHighlightedEntryIds(new Set(v.entry_ids || []))}
                    className="text-xs px-2.5 py-1 rounded-lg bg-rose-100 text-rose-900 hover:bg-rose-200 font-medium"
                  >
                    Highlight Conflict #{i + 1}: {v.message}
                  </button>
                ))}
            </div>
          )}
        </div>
      )}

      {/* Change History Panel */}
      {showHistory && (
        <div className="bg-white rounded-2xl border border-slate-200 p-4 space-y-3">
          <h3 className="text-sm font-bold text-slate-900">Change History (Audit Trail)</h3>
          {!changeHistory || changeHistory.length === 0 ? (
            <p className="text-xs text-slate-500">No changes recorded yet for this version.</p>
          ) : (
            <div className="divide-y divide-slate-100 max-h-60 overflow-y-auto text-xs">
              {changeHistory.map((item) => (
                <div key={item.id} className="py-2 flex items-center justify-between gap-4">
                  <div>
                    <span className="font-bold text-slate-800">{item.action_type}</span>
                    <span className="text-slate-500 ml-2">Rev {item.revision}</span>
                    {item.note && <span className="text-slate-600 ml-2">• {item.note}</span>}
                  </div>
                  <div className="text-slate-400 shrink-0">
                    {item.actor_name || 'System'} • {new Date(item.created_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Timetable Grid */}
      {timeSlots && assignments && courses && facultyList && rooms ? (
        <TimetableGrid
          entries={filteredEntries}
          timeSlots={timeSlots}
          assignments={assignments}
          courses={courses}
          facultyList={facultyList}
          rooms={rooms}
          versionDetail={version}
          isEditable={isEditable}
          dndEnabled={isEditMode && isEditable}
          moveOptionsMap={moveOptionsMap}
          pendingEntryIds={pendingEntryIds}
          highlightedEntryIds={highlightedEntryIds}
          onDragStartEntry={handleDragStartEntry}
          onDropOnSlot={handleDropOnSlot}
          onDragCancelEntry={() => setMoveOptionsMap({})}
          onEntryUpdated={() => {
            queryClient.invalidateQueries({ queryKey: ['timetable', 'version', versionId] });
            setValidationResult(null);
          }}
        />
      ) : (
        <div className="bg-white rounded-2xl border border-slate-200/80 p-12">
          <LoadingState message="Loading schedule context (rooms, faculty, time slots)…" />
        </div>
      )}

      {/* Approve Confirmation Modal */}
      {showApproveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <CheckCircle2 size={20} className="text-emerald-600" />
                <h3 className="text-base font-bold text-slate-900">Approve Timetable Version</h3>
              </div>
              <button
                onClick={() => setShowApproveModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                ✕
              </button>
            </div>

            <p className="text-sm text-slate-600">
              You are approving <span className="font-bold text-slate-900">Version V{version.id}</span> (Revision {currentRevision}).
            </p>

            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-xs text-emerald-800 space-y-1">
              <p className="font-semibold">Approval Safeguards:</p>
              <ul className="list-disc pl-4 space-y-0.5">
                <li>Authoritative conflict validation will run immediately.</li>
                <li>Version transitions to <span className="font-semibold">APPROVED</span> status.</li>
                <li>Enables formal publishing to related department coordinators.</li>
                <li>Any subsequent edits to classes will automatically invalidate this approval.</li>
              </ul>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setShowApproveModal(false)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                onClick={() => approveMutation.mutate()}
                disabled={approveMutation.isPending}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm"
              >
                {approveMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                <span>Confirm & Approve</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Coordinator Preflight Publication Modal */}
      {showCoordinatorModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <Send size={20} className="text-teal-600" />
                <h3 className="text-base font-bold text-slate-900">Publish Timetable to Coordinators</h3>
              </div>
              <button
                onClick={() => setShowCoordinatorModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                ✕
              </button>
            </div>

            {loadingPreflight ? (
              <div className="py-8 flex flex-col items-center justify-center space-y-2">
                <Loader2 size={24} className="text-teal-600 animate-spin" />
                <p className="text-xs text-slate-500">Resolving authoritative coordinators for this academic scope...</p>
              </div>
            ) : preflightData ? (
              <div className="space-y-4">
                <div className="bg-slate-50 rounded-xl p-3 text-xs space-y-1 border border-slate-200">
                  <p className="font-semibold text-slate-800">Academic Scope:</p>
                  <p className="text-slate-600">
                    <span className="font-medium">Department:</span> {preflightData.department_name || deptName}
                    {preflightData.semester_number && ` • Semester ${preflightData.semester_number}`}
                    {preflightData.section_names.length > 0 && ` • Sections: ${preflightData.section_names.join(', ')}`}
                  </p>
                  <p className="text-slate-500">Version V{preflightData.version_id} (Rev {preflightData.revision})</p>
                </div>

                {!preflightData.can_publish && preflightData.blocking_reasons.length > 0 && (
                  <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-xs text-red-800 space-y-1">
                    <div className="flex items-center gap-1.5 font-bold">
                      <AlertCircle size={14} className="text-red-600" />
                      <span>Publication Blocked:</span>
                    </div>
                    <ul className="list-disc pl-4 space-y-0.5">
                      {preflightData.blocking_reasons.map((reason, idx) => (
                        <li key={idx}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                      Target Coordinators ({preflightData.coordinator_count})
                    </span>
                    <span className="text-[11px] text-slate-500">Authoritative DB resolution</span>
                  </div>

                  {preflightData.coordinators.length === 0 ? (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-800">
                      No eligible coordinators mapped for this department/section scope. You must assign at least one coordinator or section class teacher before publishing.
                    </div>
                  ) : (
                    <div className="max-h-48 overflow-y-auto space-y-2 pr-1 border border-slate-200 rounded-xl p-2 bg-slate-50/50">
                      {preflightData.coordinators.map((c) => (
                        <div
                          key={c.id}
                          className="bg-white p-2.5 rounded-lg border border-slate-200 shadow-2xs flex items-center justify-between text-xs"
                        >
                          <div>
                            <p className="font-bold text-slate-900">{c.name}</p>
                            <p className="text-[11px] text-slate-500">{c.role_or_designation} • {c.scope_description}</p>
                          </div>
                          {c.email && (
                            <span className="text-[11px] text-slate-400 font-mono">{c.email}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="bg-teal-50 border border-teal-200 rounded-xl p-3 text-xs text-teal-800 space-y-1">
                  <p className="font-semibold">Publication Broadcast:</p>
                  <ul className="list-disc pl-4 space-y-0.5">
                    <li>Updates canonical timetable database records.</li>
                    <li>Dispatches notifications to all resolved coordinators linking to their department schedule.</li>
                    <li>Student and faculty schedules synchronize in real-time.</li>
                  </ul>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                  <button
                    onClick={() => setShowCoordinatorModal(false)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => publishMutation.mutate()}
                    disabled={!preflightData.can_publish || publishMutation.isPending}
                    data-testid="confirm-publish-btn"
                    className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white shadow-sm transition-colors ${
                      preflightData.can_publish && !publishMutation.isPending
                        ? 'bg-teal-600 hover:bg-teal-700'
                        : 'bg-slate-300 cursor-not-allowed'
                    }`}
                  >
                    {publishMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                    <span>Confirm & Publish to Coordinators</span>
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
};
