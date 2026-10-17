import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, BookOpen, FlaskConical } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column, FormModal, ConfirmDialog, PageHeader, StatusBadge } from '@/components/common';
import { coursesApi, type CourseResponse, type CourseUpdate } from '@/api/courses';
import { departmentsApi } from '@/api/departments';

export function CoursesPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedCourse, setSelectedCourse] = useState<CourseResponse | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Form State
  const [courseCode, setCourseCode] = useState('');
  const [courseName, setCourseName] = useState('');
  const [departmentId, setDepartmentId] = useState<number | ''>('');
  const [courseType, setCourseType] = useState('CORE');
  const [credits, setCredits] = useState<number | ''>('');
  const [lectureHours, setLectureHours] = useState<number | ''>('');
  const [tutorialHours, setTutorialHours] = useState<number | ''>('');
  const [practicalHours, setPracticalHours] = useState<number | ''>('');
  const [requiresLab, setRequiresLab] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['courses'],
    queryFn: coursesApi.getAll,
  });

  const { data: departments } = useQuery({ queryKey: ['departments'], queryFn: departmentsApi.getAll });

  const filteredData = useMemo(() => {
    if (!data) return [];
    if (!searchTerm.trim()) return data;
    const term = searchTerm.toLowerCase();
    return data.filter((crs) => {
      const dept = departments?.find((d) => d.id === crs.department_id)?.name?.toLowerCase() || '';
      return (
        crs.course_code.toLowerCase().includes(term) ||
        crs.course_name.toLowerCase().includes(term) ||
        crs.course_type.toLowerCase().includes(term) ||
        dept.includes(term) ||
        String(crs.id).includes(term)
      );
    });
  }, [data, departments, searchTerm]);

  // Mutations
  const getErrorMsg = (err: unknown, defaultMsg: string) => {
    if (isAxiosError(err)) {
      return err.response?.data?.detail || defaultMsg;
    } else if (err instanceof Error) {
      return err.message;
    }
    return defaultMsg;
  };

  const createMutation = useMutation({
    mutationFn: coursesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create course.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, crs }: { id: number; crs: CourseUpdate }) => coursesApi.update(id, crs),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update course.'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: coursesApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] });
      setIsConfirmOpen(false);
      setSelectedCourse(null);
    },
    onError: (err: unknown) => {
      alert(getErrorMsg(err, 'Failed to delete course.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<CourseResponse>[] = [
    {
      header: 'Code',
      accessor: 'course_code',
      render: (row) => (
        <span className="inline-flex items-center px-2 py-0.5 rounded font-mono text-xs font-bold bg-slate-100 text-slate-800 border border-slate-200">
          {row.course_code}
        </span>
      ),
    },
    {
      header: 'Course Name',
      accessor: 'course_name',
      render: (row) => <span className="font-semibold text-slate-900">{row.course_name}</span>,
    },
    { 
      header: 'Department', 
      render: (row) => {
        const d = departments?.find((dept) => dept.id === row.department_id);
        return <span className="text-slate-700 text-xs font-medium">{d ? `${d.department_code} - ${d.name}` : `Dept #${row.department_id}`}</span>;
      },
    },
    {
      header: 'Type',
      accessor: 'course_type',
      render: (row) => <StatusBadge status={row.course_type} />,
    },
    {
      header: 'Credits',
      accessor: 'credits',
      render: (row) => <span className="font-tabular font-bold text-primary-800">{row.credits}</span>,
    },
    { 
      header: 'L-T-P', 
      render: (row) => (
        <span className="font-tabular font-mono text-xs text-slate-700 bg-slate-50 px-2 py-0.5 rounded border border-slate-200 font-semibold" title="Lecture - Tutorial - Practical hours">
          {row.lecture_hours}-{row.tutorial_hours}-{row.practical_hours}
        </span>
      ),
    },
    {
      header: 'Lab Needed',
      render: (row) => (
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border ${
            row.requires_lab
              ? 'bg-sky-50 text-sky-800 border-sky-200'
              : 'bg-slate-100 text-slate-500 border-slate-200'
          }`}
        >
          {row.requires_lab && <FlaskConical size={11} />}
          <span>{row.requires_lab ? 'Yes' : 'No'}</span>
        </span>
      ),
    },
  ];

  const handleEdit = (crs: CourseResponse) => {
    setSelectedCourse(crs);
    setCourseCode(crs.course_code);
    setCourseName(crs.course_name);
    setDepartmentId(crs.department_id);
    setCourseType(crs.course_type);
    setCredits(crs.credits);
    setLectureHours(crs.lecture_hours);
    setTutorialHours(crs.tutorial_hours);
    setPracticalHours(crs.practical_hours);
    setRequiresLab(crs.requires_lab);
    setFormError(null);
    setIsFormOpen(true);
  };

  const handleDeleteClick = (crs: CourseResponse) => {
    setSelectedCourse(crs);
    setIsConfirmOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedCourse(null);
    setCourseCode('');
    setCourseName('');
    setDepartmentId('');
    setCourseType('CORE');
    setCredits('');
    setLectureHours('');
    setTutorialHours('');
    setPracticalHours('');
    setRequiresLab(false);
    setFormError(null);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (
      !courseCode.trim() || !courseName.trim() || departmentId === '' ||
      credits === '' || lectureHours === '' || tutorialHours === '' || practicalHours === ''
    ) {
      setFormError('All course fields are required.');
      return;
    }

    const payload = {
      course_code: courseCode.trim(),
      course_name: courseName.trim(),
      department_id: Number(departmentId),
      course_type: courseType,
      credits: Number(credits),
      lecture_hours: Number(lectureHours),
      tutorial_hours: Number(tutorialHours),
      practical_hours: Number(practicalHours),
      requires_lab: requiresLab,
    };

    if (selectedCourse) {
      updateMutation.mutate({ id: selectedCourse.id, crs: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Course Catalog"
        subtitle="Manage academic courses, instructional credits, lecture-tutorial-practical (L-T-P) weekly distribution, and lab prerequisites."
        icon={<BookOpen size={20} />}
        actions={
          <button
            onClick={() => setIsFormOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-xs font-semibold uppercase tracking-wider shadow-xs focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2"
          >
            <Plus size={15} /> Add Course
          </button>
        }
      />

      <DataTable
        title="Master Course Register"
        subtitle="Curricular courses with credit breakdown"
        columns={columns}
        data={filteredData}
        isLoading={isLoading}
        isError={isError}
        error={error as Error}
        onRefresh={() => refetch()}
        onEdit={handleEdit}
        onDelete={handleDeleteClick}
        keyExtractor={(row) => row.id}
        searchValue={searchTerm}
        onSearchChange={setSearchTerm}
        searchPlaceholder="Filter courses by code, title, type…"
        emptyMessage="No courses found matching your search."
      />

      <FormModal
        isOpen={isFormOpen}
        title={selectedCourse ? 'Edit Course Catalog Entry' : 'Register New Course'}
        subtitle="Define course classification, credit weight, and contact hour requirements"
        maxWidth="xl"
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-rose-50 text-rose-800 text-xs rounded-lg border border-rose-200 font-medium">
              {formError}
            </div>
          )}
          
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="academic-label">Course Code</label>
              <input
                type="text"
                value={courseCode}
                onChange={(e) => setCourseCode(e.target.value)}
                className="academic-input font-mono uppercase"
                placeholder="e.g. CS201"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="academic-label">Course Classification</label>
              <select
                value={courseType}
                onChange={(e) => setCourseType(e.target.value)}
                className="academic-input"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="CORE">CORE</option>
                <option value="ELECTIVE">ELECTIVE</option>
                <option value="LAB">LAB</option>
                <option value="PROJECT">PROJECT</option>
              </select>
            </div>
          </div>

          <div>
            <label className="academic-label">Course Title</label>
            <input
              type="text"
              value={courseName}
              onChange={(e) => setCourseName(e.target.value)}
              className="academic-input"
              placeholder="e.g. Data Structures and Algorithms"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="academic-label">Department</label>
              <select
                value={departmentId}
                onChange={(e) => setDepartmentId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="">Select department…</option>
                {departments?.map((d) => (
                  <option key={d.id} value={d.id}>{d.name} ({d.department_code})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="academic-label">Total Credits</label>
              <input
                type="number"
                min="0"
                value={credits}
                onChange={(e) => setCredits(e.target.value === '' ? '' : Number(e.target.value))}
                className="academic-input font-tabular"
                placeholder="e.g. 4"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="academic-label">Lecture Hrs (L)</label>
              <input
                type="number"
                min="0"
                value={lectureHours}
                onChange={(e) => setLectureHours(e.target.value === '' ? '' : Number(e.target.value))}
                className="academic-input font-tabular"
                placeholder="e.g. 3"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="academic-label">Tutorial Hrs (T)</label>
              <input
                type="number"
                min="0"
                value={tutorialHours}
                onChange={(e) => setTutorialHours(e.target.value === '' ? '' : Number(e.target.value))}
                className="academic-input font-tabular"
                placeholder="e.g. 1"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="academic-label">Practical Hrs (P)</label>
              <input
                type="number"
                min="0"
                value={practicalHours}
                onChange={(e) => setPracticalHours(e.target.value === '' ? '' : Number(e.target.value))}
                className="academic-input font-tabular"
                placeholder="e.g. 2"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
          </div>

          <div className="pt-2">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={requiresLab}
                onChange={(e) => setRequiresLab(e.target.checked)}
                className="w-4 h-4 rounded text-primary-600 border-slate-300 focus:ring-primary-600"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
              <span className="text-xs font-semibold text-slate-700">Requires Specialized Lab Infrastructure</span>
            </label>
          </div>
          
          <div className="pt-4 flex justify-end gap-2.5 border-t border-slate-100">
            <button
              type="button"
              onClick={closeForm}
              className="px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending || updateMutation.isPending}
              className="px-4 py-2 text-xs font-semibold text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors shadow-xs disabled:opacity-50"
            >
              {createMutation.isPending || updateMutation.isPending ? 'Saving…' : 'Save Course'}
            </button>
          </div>
        </form>
      </FormModal>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Course"
        message={`Are you sure you want to delete ${selectedCourse?.course_code} - ${selectedCourse?.course_name}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedCourse && deleteMutation.mutate(selectedCourse.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
