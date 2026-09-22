import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { academicYearsApi } from '@/api/academicYears';
import { semestersApi } from '@/api/semesters';
import { departmentsApi } from '@/api/departments';
import { programsApi } from '@/api/programs';
import { type GenerationScope, generateTimetable, type GenerationSummary } from '@/api/timetable';
import { getTimeSlots, type TimeSlotResponse } from '@/api/timeSlots';
import { getCourseAssignments, type CourseAssignmentResponse } from '@/api/courseAssignments';
import { coursesApi, type CourseResponse } from '@/api/courses';
import { facultyApi, type FacultyResponse } from '@/api/faculty';
import { roomsApi, type RoomResponse } from '@/api/rooms';
import { TimetableGrid } from '@/components/timetable/TimetableGrid';
import { GenerationDiagnostics } from '@/components/timetable/GenerationDiagnostics';
import { GenerationSummary as SummaryComponent } from '@/components/timetable/GenerationSummary';
import { Loader2, Calendar } from 'lucide-react';

export const TimetableGenerationPage: React.FC = () => {
  // Selectors State
  const [academicYearId, setAcademicYearId] = useState<number | ''>('');
  const [semesterId, setSemesterId] = useState<number | ''>('');
  const [departmentId, setDepartmentId] = useState<number | ''>('');
  const [programId, setProgramId] = useState<number | ''>('');

  // Result State
  const [summary, setSummary] = useState<GenerationSummary | null>(null);
  const [errorStatus, setErrorStatus] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [errorDiagnostics, setErrorDiagnostics] = useState<string[]>([]);

  // Fetch contextual data
  const { data: academicYears } = useQuery({ queryKey: ['academicYears'], queryFn: academicYearsApi.getAll });
  const { data: semesters } = useQuery({ queryKey: ['semesters'], queryFn: semestersApi.getAll });
  const { data: departments } = useQuery({ queryKey: ['departments'], queryFn: departmentsApi.getAll });
  const { data: programs } = useQuery({ queryKey: ['programs'], queryFn: programsApi.getAll });

  // Fetch timetable lookup data (Ideally these would be fetched only when generation succeeds, but React Query caches them)
  const { data: timeSlots } = useQuery<TimeSlotResponse[]>({ queryKey: ['timeSlots'], queryFn: getTimeSlots, enabled: !!summary });
  const { data: assignments } = useQuery<CourseAssignmentResponse[]>({ queryKey: ['courseAssignments'], queryFn: getCourseAssignments, enabled: !!summary });
  const { data: courses } = useQuery<CourseResponse[]>({ queryKey: ['courses'], queryFn: coursesApi.getAll, enabled: !!summary });
  const { data: facultyList } = useQuery<FacultyResponse[]>({ queryKey: ['faculty'], queryFn: facultyApi.getAll, enabled: !!summary });
  const { data: rooms } = useQuery<RoomResponse[]>({ queryKey: ['rooms'], queryFn: roomsApi.getAll, enabled: !!summary });

  const generateMutation = useMutation({
    mutationFn: (scope: GenerationScope) => generateTimetable(scope),
    onSuccess: (data) => {
      setSummary(data);
      setErrorStatus('');
      setErrorMessage('');
      setErrorDiagnostics([]);
    },
    onError: (err: unknown) => {
      setSummary(null);
      if (isAxiosError(err) && err.response) {
        if (err.response.status === 422) {
          setErrorStatus('INFEASIBLE');
          setErrorMessage(err.response.data?.detail?.message || 'The timetable cannot be generated with the given constraints.');
          setErrorDiagnostics(err.response.data?.detail?.diagnostics || []);
        } else if (err.response.status === 500) {
          setErrorStatus('SERVER_ERROR');
          setErrorMessage(err.response.data?.detail || 'An internal server error occurred during generation.');
          setErrorDiagnostics([]);
        } else {
          setErrorStatus('ERROR');
          setErrorMessage(err.response.data?.detail || 'An unexpected error occurred.');
          setErrorDiagnostics([]);
        }
      } else if (err instanceof Error) {
        setErrorStatus('ERROR');
        setErrorMessage(err.message);
        setErrorDiagnostics([]);
      } else {
        setErrorStatus('ERROR');
        setErrorMessage('An unknown error occurred.');
        setErrorDiagnostics([]);
      }
    }
  });

  const handleGenerate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!academicYearId || !semesterId || !departmentId || !programId) return;

    generateMutation.mutate({
      academic_year_id: Number(academicYearId),
      semester_id: Number(semesterId),
      department_id: Number(departmentId),
      program_id: Number(programId),
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Calendar className="h-6 w-6 text-indigo-600" />
          Timetable Generation
        </h1>
      </div>

      {/* Generation Form */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <form onSubmit={handleGenerate} className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Academic Year</label>
            <select
              required
              value={academicYearId}
              onChange={(e) => setAcademicYearId(e.target.value ? Number(e.target.value) : '')}
              className="w-full border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
              disabled={generateMutation.isPending}
            >
              <option value="">Select Year</option>
              {academicYears?.map(ay => (
                <option key={ay.id} value={ay.id}>{ay.year_name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Semester</label>
            <select
              required
              value={semesterId}
              onChange={(e) => setSemesterId(e.target.value ? Number(e.target.value) : '')}
              className="w-full border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
              disabled={generateMutation.isPending}
            >
              <option value="">Select Semester</option>
              {semesters?.map(sem => (
                <option key={sem.id} value={sem.id}>Semester {sem.semester_number}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Department</label>
            <select
              required
              value={departmentId}
              onChange={(e) => setDepartmentId(e.target.value ? Number(e.target.value) : '')}
              className="w-full border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
              disabled={generateMutation.isPending}
            >
              <option value="">Select Department</option>
              {departments?.map(dept => (
                <option key={dept.id} value={dept.id}>{dept.department_code}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Program</label>
            <select
              required
              value={programId}
              onChange={(e) => setProgramId(e.target.value ? Number(e.target.value) : '')}
              className="w-full border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
              disabled={generateMutation.isPending}
            >
              <option value="">Select Program</option>
              {programs?.map(prog => (
                <option key={prog.id} value={prog.id}>{prog.program_name}</option>
              ))}
            </select>
          </div>

          <div className="md:col-span-4 mt-4 flex justify-end">
            <button
              type="submit"
              disabled={generateMutation.isPending || !academicYearId || !semesterId || !departmentId || !programId}
              className="bg-indigo-600 text-white px-6 py-2 rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 flex items-center justify-center min-w-[200px]"
            >
              {generateMutation.isPending ? (
                <>
                  <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                  Generating...
                </>
              ) : (
                'Generate Timetable'
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Loading Overlay State for Long Generation */}
      {generateMutation.isPending && (
        <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-8 flex flex-col items-center justify-center text-center">
          <Loader2 className="w-10 h-10 text-indigo-600 animate-spin mb-4" />
          <h3 className="text-lg font-medium text-indigo-900">Generating optimal timetable...</h3>
          <p className="text-indigo-700 mt-2">This process may take up to 60 seconds as the AI engine explores thousands of possibilities.</p>
        </div>
      )}

      {/* Error / Diagnostics State */}
      {errorStatus && (
        <GenerationDiagnostics
          status={errorStatus}
          message={errorMessage}
          diagnostics={errorDiagnostics}
        />
      )}

      {/* Success State */}
      {summary && summary.status === 'SUCCESS' && (
        <div className="space-y-6">
          <GenerationDiagnostics
            status={summary.status}
            message={summary.message}
            diagnostics={summary.diagnostics}
          />
          <SummaryComponent summary={summary} />

          {summary.generated_entries && timeSlots && assignments && courses && facultyList && rooms ? (
            <TimetableGrid
              entries={summary.generated_entries}
              timeSlots={timeSlots}
              assignments={assignments}
              courses={courses}
              facultyList={facultyList}
              rooms={rooms}
            />
          ) : (
            <div className="py-10 text-center text-gray-500 flex flex-col items-center">
               <Loader2 className="w-8 h-8 animate-spin mb-4 text-indigo-400" />
               <p>Loading additional schedule context...</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
