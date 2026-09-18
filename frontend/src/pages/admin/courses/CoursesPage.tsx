import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column } from '@/components/common/DataTable';
import { FormModal } from '@/components/common/FormModal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { coursesApi, type CourseResponse, type CourseUpdate } from '@/api/courses';
import { departmentsApi } from '@/api/departments';

export function CoursesPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedCourse, setSelectedCourse] = useState<CourseResponse | null>(null);
  
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
    { header: 'Code', accessor: 'course_code' },
    { header: 'Name', accessor: 'course_name' },
    { 
      header: 'Department', 
      render: (row) => departments?.find(d => d.id === row.department_id)?.name || `ID: ${row.department_id}` 
    },
    { header: 'Type', accessor: 'course_type' },
    { header: 'Credits', accessor: 'credits' },
    { 
      header: 'L-T-P', 
      render: (row) => `${row.lecture_hours}-${row.tutorial_hours}-${row.practical_hours}` 
    },
    { 
      header: 'Lab', 
      render: (row) => (
        <span className={`px-2 py-1 rounded-full text-xs font-semibold ${row.requires_lab ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-700'}`}>
          {row.requires_lab ? 'Yes' : 'No'}
        </span>
      ) 
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
      setFormError('All fields are required.');
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
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Courses</h2>
          <p className="text-sm text-gray-500 mt-1">Manage course catalog.</p>
        </div>
        <button
          onClick={() => setIsFormOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          <Plus size={16} /> Add Course
        </button>
      </div>

      <DataTable
        columns={columns}
        data={data}
        isLoading={isLoading}
        isError={isError}
        error={error as Error}
        onRefresh={() => refetch()}
        onEdit={handleEdit}
        onDelete={handleDeleteClick}
        keyExtractor={(row) => row.id}
      />

      <FormModal
        isOpen={isFormOpen}
        title={selectedCourse ? 'Edit Course' : 'Add Course'}
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-red-50 text-red-700 text-sm rounded-lg border border-red-200">
              {formError}
            </div>
          )}
          
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Course Code</label>
              <input
                type="text"
                value={courseCode}
                onChange={(e) => setCourseCode(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. CS101"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Course Type</label>
              <select
                value={courseType}
                onChange={(e) => setCourseType(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
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
            <label className="block text-sm font-medium text-gray-700 mb-1">Course Name</label>
            <input
              type="text"
              value={courseName}
              onChange={(e) => setCourseName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="e.g. Intro to Computer Science"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Department</label>
              <select
                value={departmentId}
                onChange={(e) => setDepartmentId(e.target.value ? Number(e.target.value) : '')}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="">Select Department</option>
                {departments?.map(d => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Credits</label>
              <input
                type="number"
                min="0"
                value={credits}
                onChange={(e) => setCredits(e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Lecture Hrs</label>
              <input
                type="number"
                min="0"
                value={lectureHours}
                onChange={(e) => setLectureHours(e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tutorial Hrs</label>
              <input
                type="number"
                min="0"
                value={tutorialHours}
                onChange={(e) => setTutorialHours(e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Practical Hrs</label>
              <input
                type="number"
                min="0"
                value={practicalHours}
                onChange={(e) => setPracticalHours(e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
          </div>

          <div className="flex items-center gap-2 mt-2">
            <input
              type="checkbox"
              id="requiresLab"
              checked={requiresLab}
              onChange={(e) => setRequiresLab(e.target.checked)}
              className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
            <label htmlFor="requiresLab" className="text-sm font-medium text-gray-700">
              Requires Lab
            </label>
          </div>
          
          <div className="pt-4 flex justify-end gap-3">
            <button
              type="button"
              onClick={closeForm}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending || updateMutation.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50"
            >
              {createMutation.isPending || updateMutation.isPending ? 'Saving...' : 'Save'}
            </button>
          </div>
        </form>
      </FormModal>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Course"
        message={`Are you sure you want to delete ${selectedCourse?.course_code}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedCourse && deleteMutation.mutate(selectedCourse.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
