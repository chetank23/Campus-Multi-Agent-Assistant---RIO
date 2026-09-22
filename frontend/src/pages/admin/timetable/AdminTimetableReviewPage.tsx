import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { ArrowLeft, CheckCircle2, ShieldCheck, Send, Loader2, AlertCircle } from 'lucide-react';
import { getTimetableVersion, validateTimetableVersion, finalizeTimetableVersion, publishTimetableVersion, type ValidationResult } from '@/api/timetable';
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

export const AdminTimetableReviewPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const versionId = Number(id);

  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [errorStatus, setErrorStatus] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string>('');

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
    }
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
    }
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
    }
  });

  if (isVersionLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mb-4" />
        <p className="text-gray-500">Loading version details...</p>
      </div>
    );
  }

  if (isVersionError || !version) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6">
        <h3 className="text-sm font-medium text-red-800">Error loading timetable version</h3>
      </div>
    );
  }

  // Derive Context Names
  const ayName = academicYears?.find(ay => ay.id === version.academic_year_id)?.year_name || 'N/A';
  const firstEntry = version.timetable_entries[0];
  const deptName = departments?.find(d => d.id === firstEntry?.department_id)?.name || 'N/A';
  const progName = programs?.find(p => p.id === firstEntry?.program_id)?.program_name || 'N/A';
  const semName = semesters?.find(s => s.id === firstEntry?.semester_id)?.semester_number ? `Semester ${semesters.find(s => s.id === firstEntry?.semester_id)?.semester_number}` : 'N/A';

  const getStatusBadge = (status: string | null) => {
    switch (status) {
      case 'GENERATED': return <span className="px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800">GENERATED</span>;
      case 'REVIEWED': return <span className="px-3 py-1 rounded-full text-sm font-medium bg-yellow-100 text-yellow-800">REVIEWED</span>;
      case 'VALIDATED': return <span className="px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800">VALIDATED</span>;
      case 'FINALIZED': return <span className="px-3 py-1 rounded-full text-sm font-medium bg-purple-100 text-purple-800">FINALIZED</span>;
      case 'PUBLISHED': return <span className="px-3 py-1 rounded-full text-sm font-medium bg-emerald-100 text-emerald-800">PUBLISHED</span>;
      default: return <span className="px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-800">{status || 'UNKNOWN'}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div>
          <button 
            onClick={() => navigate('/admin/timetable/versions')}
            className="flex items-center text-sm text-gray-500 hover:text-gray-700 mb-2 transition-colors"
          >
            <ArrowLeft className="w-4 h-4 mr-1" /> Back to Versions
          </button>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">Review Version V{version.id}</h1>
            {getStatusBadge(version.status)}
          </div>
          <div className="mt-2 text-sm text-gray-600 space-y-1">
            <p><strong>Academic Year:</strong> {ayName}</p>
            <p><strong>Department:</strong> {deptName} &bull; <strong>Program:</strong> {progName} &bull; <strong>Semester:</strong> {semName}</p>
          </div>
        </div>
        
        {/* Actions */}
        <div className="flex flex-wrap items-center gap-3">
          {(version.status === 'GENERATED' || version.status === 'REVIEWED' || version.status === 'VALIDATED') && (
            <button
              onClick={() => validateMutation.mutate()}
              disabled={validateMutation.isPending}
              className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
            >
              {validateMutation.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <ShieldCheck className="w-4 h-4 mr-2" />}
              {version.status === 'REVIEWED' ? 'Revalidate' : 'Validate'}
            </button>
          )}

          {version.status === 'VALIDATED' && (
            <button
              onClick={() => {
                if (confirm('Finalize this timetable? It will lock it from further editing.')) {
                  finalizeMutation.mutate();
                }
              }}
              disabled={finalizeMutation.isPending}
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
            >
              {finalizeMutation.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-2" />}
              Finalize
            </button>
          )}

          {version.status === 'FINALIZED' && (
            <button
              onClick={() => {
                if (confirm('Publish this timetable? This will make it visible to faculty and students.')) {
                  publishMutation.mutate();
                }
              }}
              disabled={publishMutation.isPending}
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 disabled:opacity-50"
            >
              {publishMutation.isPending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
              Publish
            </button>
          )}
        </div>
      </div>

      {/* Error Displays */}
      {errorStatus && (
        <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-r-md">
          <div className="flex">
            <AlertCircle className="h-5 w-5 text-red-500 mr-2" />
            <h3 className="text-sm font-medium text-red-800">{errorMessage}</h3>
          </div>
        </div>
      )}

      {/* Validation Result UI */}
      {validationResult && <ValidationResultDisplay result={validationResult} />}

      {/* Grid */}
      {timeSlots && assignments && courses && facultyList && rooms ? (
        <TimetableGrid
          entries={version.timetable_entries}
          timeSlots={timeSlots}
          assignments={assignments}
          courses={courses}
          facultyList={facultyList}
          rooms={rooms}
          isEditable={version.status === 'GENERATED' || version.status === 'REVIEWED' || version.status === 'VALIDATED'}
          onEntryUpdated={() => {
            queryClient.invalidateQueries({ queryKey: ['timetable', 'version', versionId] });
            setValidationResult(null); // Clear validation output since state changed to REVIEWED
          }}
        />
      ) : (
        <div className="py-10 text-center text-gray-500 flex flex-col items-center">
          <Loader2 className="w-8 h-8 animate-spin mb-4 text-indigo-400" />
          <p>Loading schedule context...</p>
        </div>
      )}
    </div>
  );
};
