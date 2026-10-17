import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
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
import { PageHeader, LoadingState } from '@/components/common';
import { Sparkles, Cpu, Sliders, Calendar, ListChecks, CheckCircle2, ChevronRight } from 'lucide-react';

export const TimetableGenerationPage: React.FC = () => {
  const navigate = useNavigate();

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

  // Fetch timetable lookup data (enabled only when generation succeeds)
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
    },
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

  const isFormValid = !!academicYearId && !!semesterId && !!departmentId && !!programId;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Timetable Generation Engine"
        subtitle="Configure academic scope, trigger automated constraint programming solver (CP-SAT), and evaluate schedule optimization metrics."
        breadcrumbs={[
          { label: 'Admin', href: '/admin' },
          { label: 'Timetable', href: '/admin/timetable/versions' },
          { label: 'Generation Engine' },
        ]}
        actions={
          <button
            onClick={() => navigate('/admin/timetable/versions')}
            className="academic-btn-secondary inline-flex items-center gap-2"
          >
            <Calendar size={16} />
            <span>View All Versions</span>
          </button>
        }
      />

      {/* Scope Configuration Card */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200/80 bg-slate-50/50 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-primary-50 text-primary-700">
              <Sliders size={18} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-900">Optimization Scope Parameters</h3>
              <p className="text-xs text-slate-500">Define the academic boundary conditions for this solver run</p>
            </div>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
            Step 1 of 2: Define Scope
          </span>
        </div>

        <form onSubmit={handleGenerate} className="p-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            <div>
              <label className="academic-label">Academic Year</label>
              <select
                required
                value={academicYearId}
                onChange={(e) => setAcademicYearId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={generateMutation.isPending}
              >
                <option value="">Select Academic Year</option>
                {academicYears?.map((ay) => (
                  <option key={ay.id} value={ay.id}>
                    {ay.year_name} {ay.is_active ? '(Active)' : ''}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="academic-label">Semester Term</label>
              <select
                required
                value={semesterId}
                onChange={(e) => setSemesterId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={generateMutation.isPending}
              >
                <option value="">Select Semester</option>
                {semesters?.map((sem) => (
                  <option key={sem.id} value={sem.id}>
                    Semester {sem.semester_number}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="academic-label">Department</label>
              <select
                required
                value={departmentId}
                onChange={(e) => setDepartmentId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={generateMutation.isPending}
              >
                <option value="">Select Department</option>
                {departments?.map((dept) => (
                  <option key={dept.id} value={dept.id}>
                    {dept.department_code} • {dept.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="academic-label">Degree Program</label>
              <select
                required
                value={programId}
                onChange={(e) => setProgramId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={generateMutation.isPending}
              >
                <option value="">Select Program</option>
                {programs?.map((prog) => (
                  <option key={prog.id} value={prog.id}>
                    {prog.program_name} ({prog.degree})
                  </option>

                ))}
              </select>
            </div>
          </div>

          <div className="mt-6 pt-5 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="text-xs text-slate-500 flex items-center gap-1.5">
              <ListChecks size={15} className="text-primary-600" />
              <span>Hard constraints: faculty conflicts, room capacities, day slot bounds automatically applied.</span>
            </div>

            <button
              type="submit"
              disabled={generateMutation.isPending || !isFormValid}
              className="academic-btn-primary inline-flex items-center justify-center gap-2 min-w-[200px]"
            >
              {generateMutation.isPending ? (
                <>
                  <Cpu size={16} className="animate-spin text-primary-200" />
                  <span>Solving Optimization…</span>
                </>
              ) : (
                <>
                  <Sparkles size={16} />
                  <span>Generate Timetable</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Solver Execution Banner */}
      {generateMutation.isPending && (
        <div className="bg-primary-50/70 border border-primary-200/80 rounded-2xl p-8 flex flex-col items-center justify-center text-center shadow-xs animate-in fade-in-0 duration-200">
          <div className="p-3 rounded-2xl bg-primary-100 text-primary-700 mb-4 animate-pulse">
            <Cpu size={32} />
          </div>
          <h3 className="text-base font-bold text-primary-950">
            Constraint Solver Execution in Progress
          </h3>
          <p className="text-xs text-primary-800 max-w-lg mt-1.5 leading-relaxed">
            The optimization engine is exploring thousands of scheduling permutations using Google OR-Tools CP-SAT solver.
            Evaluating faculty availability, lab allocations, room limits, and gap balancing.
          </p>
          <div className="mt-4 flex items-center gap-2 text-xs font-semibold text-primary-700">
            <span className="w-2 h-2 rounded-full bg-primary-600 animate-ping" />
            Convergence typically reached within 5–30 seconds
          </div>
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
          <div className="flex items-center justify-between p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900">
            <div className="flex items-center gap-2.5">
              <CheckCircle2 size={18} className="text-emerald-600" />
              <span className="text-sm font-semibold">Timetable Generated Successfully</span>
            </div>
            <button
              onClick={() => navigate('/admin/timetable/versions')}
              className="text-xs font-semibold text-emerald-800 hover:text-emerald-950 inline-flex items-center gap-1 underline underline-offset-2"
            >
              <span>Manage in Timetable Versions</span>
              <ChevronRight size={14} />
            </button>
          </div>

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
            <div className="bg-white rounded-2xl border border-slate-200/80 p-12">
              <LoadingState message="Loading schedule lookup context (faculty, rooms, syllabus slots)…" />
            </div>
          )}
        </div>
      )}
    </div>
  );
};
