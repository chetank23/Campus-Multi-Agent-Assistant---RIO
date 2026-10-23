import React, { useState } from 'react';
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
} from 'lucide-react';

import {
  getTimetableVersion,
  validateTimetableVersion,
  finalizeTimetableVersion,
  publishTimetableVersion,
  type ValidationResult,
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

export const AdminTimetableReviewPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const versionId = Number(id);

  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [errorStatus, setErrorStatus] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [showPublishConfirm, setShowPublishConfirm] = useState(false);

  // Fetch Version Data
  const { data: version, isLoading: isVersionLoading, isError: isVersionError } = useQuery({
    queryKey: ['timetable', 'version', versionId],
    queryFn: () => getTimetableVersion(versionId),
  });

  // Fetch Contextual Data
  const { data: academicYears } = useQuery({ queryKey: ['academicYears'], queryFn: academicYearsApi.getAll });
  const { data: semesters } = useQuery({ queryKey: ['semesters'], queryFn: semestersApi.getAll });
  const { data: departments } = useQuery({ queryKey: ['departments'], queryFn: departmentsApi.getAll });
  const { data: programs } = useQuery({ queryKey: ['programs'], queryFn: programsApi.getAll });
  const { data: timeSlots } = useQuery({ queryKey: ['timeSlots'], queryFn: getTimeSlots });
  const { data: assignments } = useQuery({ queryKey: ['courseAssignments'], queryFn: getCourseAssignments });
  const { data: courses } = useQuery({ queryKey: ['courses'], queryFn: coursesApi.getAll });
  const { data: facultyList } = useQuery({ queryKey: ['faculty'], queryFn: facultyApi.getAll });
  const { data: rooms } = useQuery({ queryKey: ['rooms'], queryFn: roomsApi.getAll });

  // Mutations
  const validateMutation = useMutation({
    mutationFn: () => validateTimetableVersion(versionId),
    onSuccess: (data) => {
      setValidationResult(data);
      queryClient.invalidateQueries({ queryKey: ['timetable', 'version', versionId] });
      queryClient.invalidateQueries({ queryKey: ['timetable', 'versions'] });
      setErrorStatus('');
      setErrorMessage('');
    },
    onError: (err: unknown) => {
      setValidationResult(null);
      if (isAxiosError(err) && err.response) {
        setErrorStatus('VALIDATION_ERROR');
        setErrorMessage(err.response.data?.detail || 'Validation failed due to a server error.');
      } else {
        setErrorStatus('ERROR');
        setErrorMessage('An unexpected error occurred during validation.');
      }
    },
  });

  const finalizeMutation = useMutation({
    mutationFn: () => finalizeTimetableVersion(versionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timetable', 'version', versionId] });
      queryClient.invalidateQueries({ queryKey: ['timetable', 'versions'] });
      setErrorStatus('');
      setErrorMessage('');
    },
    onError: (err: unknown) => {
      if (isAxiosError(err) && err.response) {
        setErrorStatus('FINALIZE_ERROR');
        setErrorMessage(err.response.data?.detail || 'Failed to finalize timetable.');
      }
    },
  });

  const publishMutation = useMutation({
    mutationFn: () => publishTimetableVersion(versionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timetable', 'version', versionId] });
      queryClient.invalidateQueries({ queryKey: ['timetable', 'versions'] });
      setErrorStatus('');
      setErrorMessage('');
    },
    onError: (err: unknown) => {
      if (isAxiosError(err) && err.response) {
        setErrorStatus('PUBLISH_ERROR');
        setErrorMessage(err.response.data?.detail || 'Failed to publish timetable.');
      }
    },
  });

  if (isVersionLoading) {
    return (
      <div className="py-16">
        <LoadingState message="Loading timetable version and schedule entries…" />
      </div>
    );
  }

  if (isVersionError || !version) {
    return (
      <div className="space-y-6">
        <button
          onClick={() => navigate('/admin/timetable/versions')}
          className="academic-btn-secondary inline-flex items-center gap-1.5 text-xs"
        >
          <ArrowLeft size={14} />
          <span>Back to Versions</span>
        </button>
        <ErrorState
          title="Error Loading Timetable Version"
          message={`Unable to retrieve record for Version #${versionId}. It may have been deleted or the server is unavailable.`}
        />
      </div>
    );
  }

  // Derive Context Names
  const ayName = academicYears?.find((ay) => ay.id === version.academic_year_id)?.year_name || 'N/A';
  const firstEntry = version.timetable_entries[0];
  const deptName = departments?.find((d) => d.id === firstEntry?.department_id)?.name || 'N/A';
  const progName = programs?.find((p) => p.id === firstEntry?.program_id)?.program_name || 'N/A';
  const semNumber = semesters?.find((s) => s.id === firstEntry?.semester_id)?.semester_number;
  const semName = semNumber ? `Semester ${semNumber}` : 'N/A';

  const getStatusBadge = (status: string | null) => {
    switch (status) {
      case 'GENERATED':
        return <StatusBadge label="GENERATED" variant="info" size="md" />;
      case 'REVIEWED':
        return <StatusBadge label="REVIEWED" variant="warning" size="md" />;
      case 'VALIDATED':
        return <StatusBadge label="VALIDATED" variant="success" size="md" />;
      case 'FINALIZED':
        return <StatusBadge label="FINALIZED" variant="primary" size="md" />;
      case 'PUBLISHED':
        return <StatusBadge label="PUBLISHED" variant="success" size="md" dot />;
      default:
        return <StatusBadge label={status || 'UNKNOWN'} variant="neutral" size="md" />;
    }
  };

  const isEditable =
    version.status === 'GENERATED' || version.status === 'REVIEWED' || version.status === 'VALIDATED';

  return (
    <div className="space-y-6">
      {/* Header and Intentional Actions */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <button
            onClick={() => navigate('/admin/timetable/versions')}
            className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors"
          >
            <ArrowLeft size={14} />
            <span>Back to All Timetable Versions</span>
          </button>
          <div className="flex items-center gap-2">
            {getStatusBadge(version.status)}
          </div>
        </div>

        <PageHeader
          title={`Review Timetable Version V${version.id}`}
          subtitle={`${deptName} • ${progName} • ${semName} (${ayName})`}
          breadcrumbs={[
            { label: 'Admin', href: '/admin' },
            { label: 'Timetable', href: '/admin/timetable/versions' },
            { label: `Version V${version.id}` },
          ]}
          actions={
            <div className="flex flex-wrap items-center gap-2.5">
              {/* Action: Validate / Revalidate */}
              {(version.status === 'GENERATED' ||
                version.status === 'REVIEWED' ||
                version.status === 'VALIDATED') && (
                <button
                  onClick={() => validateMutation.mutate()}
                  disabled={validateMutation.isPending}
                  className="academic-btn-secondary inline-flex items-center gap-1.5 text-xs font-semibold"
                >
                  {validateMutation.isPending ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <ShieldCheck size={15} className="text-primary-600" />
                  )}
                  <span>{version.status === 'REVIEWED' ? 'Revalidate Engine' : 'Validate Engine'}</span>
                </button>
              )}

              {/* Action: Finalize */}
              {version.status === 'VALIDATED' && (
                <button
                  onClick={() => {
                    if (confirm('Finalize this timetable? It will lock it from further editing.')) {
                      finalizeMutation.mutate();
                    }
                  }}
                  disabled={finalizeMutation.isPending}
                  className="academic-btn-primary inline-flex items-center gap-1.5 text-xs font-semibold"
                >
                  {finalizeMutation.isPending ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <CheckCircle2 size={15} />
                  )}
                  <span>Finalize & Lock</span>
                </button>
              )}

              {/* Action: Publish */}
              {version.status === 'FINALIZED' && (
                showPublishConfirm ? (
                  <div className="inline-flex items-center gap-1.5 p-1 bg-emerald-50 rounded-xl border border-emerald-200">
                    <button
                      onClick={() => {
                        setShowPublishConfirm(false);
                        publishMutation.mutate();
                      }}
                      disabled={publishMutation.isPending}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs transition-colors disabled:opacity-50"
                    >
                      {publishMutation.isPending ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <Send size={13} />
                      )}
                      <span>Confirm Publish</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowPublishConfirm(false)}
                      disabled={publishMutation.isPending}
                      className="px-2 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-200/60 transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setShowPublishConfirm(true)}
                    disabled={publishMutation.isPending}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition-colors disabled:opacity-50"
                  >
                    {publishMutation.isPending ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Send size={15} />
                    )}
                    <span>Publish to Portal</span>
                  </button>
                )
              )}
            </div>
          }
        />
      </div>

      {/* Institutional Metadata Context Strip */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          <div className="p-3 rounded-xl bg-slate-50/70 border border-slate-200/60">
            <span className="font-semibold text-slate-500 uppercase tracking-wider text-[10px] block mb-1">
              Academic Context
            </span>
            <div className="font-bold text-slate-900 truncate">{deptName}</div>
            <div className="text-slate-500 mt-0.5">{progName} • {semName}</div>
          </div>

          <div className="p-3 rounded-xl bg-slate-50/70 border border-slate-200/60">
            <span className="font-semibold text-slate-500 uppercase tracking-wider text-[10px] block mb-1">
              Academic Year
            </span>
            <div className="font-bold text-slate-900">{ayName}</div>
            <div className="text-slate-500 mt-0.5">{version.timetable_entries?.length || 0} scheduled classes</div>
          </div>

          <div className="p-3 rounded-xl bg-slate-50/70 border border-slate-200/60">
            <span className="font-semibold text-slate-500 uppercase tracking-wider text-[10px] block mb-1">
              Timestamps
            </span>
            <div className="text-slate-700">Created: {new Date(version.created_at).toLocaleDateString()}</div>
            <div className="text-slate-500 mt-0.5">
              {version.published_at ? `Published: ${new Date(version.published_at).toLocaleDateString()}` : 'Unpublished'}
            </div>
          </div>

          <div className="p-3 rounded-xl bg-slate-50/70 border border-slate-200/60">
            <span className="font-semibold text-slate-500 uppercase tracking-wider text-[10px] block mb-1">
              Workspace State
            </span>
            <div className="flex items-center gap-1.5 font-semibold text-slate-800">
              {isEditable ? (
                <>
                  <Edit3 size={14} className="text-primary-600" />
                  <span>Manual Editing Enabled</span>
                </>
              ) : (
                <>
                  <Lock size={14} className="text-slate-400" />
                  <span>Locked from Edits</span>
                </>
              )}
            </div>
            <div className="text-slate-500 mt-0.5 text-[11px]">
              {isEditable ? 'Click any cell to override room/slot' : 'Version finalized or published'}
            </div>
          </div>
        </div>
      </div>

      {/* Error Displays */}
      {errorStatus && (
        <div className="bg-rose-50 border border-rose-200 p-4 rounded-xl flex items-start gap-3 text-rose-900 shadow-xs">
          <AlertCircle size={18} className="text-rose-600 shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm font-semibold">Action Encountered an Error</h4>
            <p className="text-xs text-rose-800 mt-0.5">{errorMessage}</p>
          </div>
        </div>
      )}

      {/* Validation Result UI */}
      {validationResult && <ValidationResultDisplay result={validationResult} />}

      {/* Timetable Grid */}
      {timeSlots && assignments && courses && facultyList && rooms ? (
        <TimetableGrid
          entries={version.timetable_entries}
          timeSlots={timeSlots}
          assignments={assignments}
          courses={courses}
          facultyList={facultyList}
          rooms={rooms}
          versionDetail={version}
          isEditable={isEditable}
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
    </div>
  );
};
