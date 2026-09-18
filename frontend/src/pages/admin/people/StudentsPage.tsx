import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column } from '@/components/common/DataTable';
import { FormModal } from '@/components/common/FormModal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { studentsApi, type StudentResponse, type StudentUpdate } from '@/api/students';
import { departmentsApi } from '@/api/departments';
import { programsApi } from '@/api/programs';
import { batchesApi } from '@/api/batches';
import { sectionsApi } from '@/api/sections';
import { semestersApi } from '@/api/semesters';

export function StudentsPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState<StudentResponse | null>(null);
  
  // Form State
  const [userId, setUserId] = useState<number | ''>('');
  const [studentIdStr, setStudentIdStr] = useState('');
  const [departmentId, setDepartmentId] = useState<number | ''>('');
  const [programId, setProgramId] = useState<number | ''>('');
  const [semesterId, setSemesterId] = useState<number | ''>('');
  const [sectionId, setSectionId] = useState<number | ''>('');
  const [batchId, setBatchId] = useState<number | ''>('');
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['students'],
    queryFn: studentsApi.getAll,
  });

  const { data: departments } = useQuery({ queryKey: ['departments'], queryFn: departmentsApi.getAll });
  const { data: programs } = useQuery({ queryKey: ['programs'], queryFn: programsApi.getAll });
  const { data: batches } = useQuery({ queryKey: ['batches'], queryFn: batchesApi.getAll });
  const { data: sections } = useQuery({ queryKey: ['sections'], queryFn: sectionsApi.getAll });
  const { data: semesters } = useQuery({ queryKey: ['semesters'], queryFn: semestersApi.getAll });

  const getErrorMsg = (err: unknown, defaultMsg: string) => {
    if (isAxiosError(err)) {
      return err.response?.data?.detail || defaultMsg;
    } else if (err instanceof Error) {
      return err.message;
    }
    return defaultMsg;
  };

  // Mutations
  const createMutation = useMutation({
    mutationFn: studentsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['students'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create student.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, std }: { id: number; std: StudentUpdate }) => studentsApi.update(id, std),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['students'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update student.'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: studentsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['students'] });
      setIsConfirmOpen(false);
      setSelectedStudent(null);
    },
    onError: (err: unknown) => {
      alert(getErrorMsg(err, 'Failed to delete student.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<StudentResponse>[] = [
    { header: 'ID', accessor: 'id' },
    { header: 'Student ID', accessor: 'student_id' },
    { header: 'User ID', accessor: 'user_id' },
    { 
      header: 'Department', 
      render: (row) => departments?.find(d => d.id === row.department_id)?.department_code || `ID: ${row.department_id}` 
    },
    { 
      header: 'Program', 
      render: (row) => programs?.find(p => p.id === row.program_id)?.program_name || `ID: ${row.program_id}` 
    },
    { 
      header: 'Semester', 
      render: (row) => {
        const sem = semesters?.find(s => s.id === row.semester_id);
        return sem ? `${sem.term} ${sem.semester_number}` : `ID: ${row.semester_id}`;
      }
    },
    { 
      header: 'Section', 
      render: (row) => sections?.find(s => s.id === row.section_id)?.section_name || `ID: ${row.section_id}` 
    },
    { 
      header: 'Batch', 
      render: (row) => batches?.find(b => b.id === row.batch_id)?.batch_name || `ID: ${row.batch_id}` 
    },
  ];

  const handleEdit = (std: StudentResponse) => {
    setSelectedStudent(std);
    setUserId(std.user_id);
    setStudentIdStr(std.student_id);
    setDepartmentId(std.department_id);
    setProgramId(std.program_id);
    setSemesterId(std.semester_id);
    setSectionId(std.section_id);
    setBatchId(std.batch_id);
    setFormError(null);
    setIsFormOpen(true);
  };

  const handleDeleteClick = (std: StudentResponse) => {
    setSelectedStudent(std);
    setIsConfirmOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedStudent(null);
    setUserId('');
    setStudentIdStr('');
    setDepartmentId('');
    setProgramId('');
    setSemesterId('');
    setSectionId('');
    setBatchId('');
    setFormError(null);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (
      userId === '' || 
      !studentIdStr.trim() || 
      departmentId === '' || 
      programId === '' || 
      semesterId === '' || 
      sectionId === '' || 
      batchId === ''
    ) {
      setFormError('All fields are required.');
      return;
    }

    const payload = {
      user_id: Number(userId),
      student_id: studentIdStr.trim(),
      department_id: Number(departmentId),
      program_id: Number(programId),
      semester_id: Number(semesterId),
      section_id: Number(sectionId),
      batch_id: Number(batchId),
    };

    if (selectedStudent) {
      updateMutation.mutate({ id: selectedStudent.id, std: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Students</h2>
          <p className="text-sm text-gray-500 mt-1">Manage student academic records.</p>
        </div>
        <button
          onClick={() => setIsFormOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          <Plus size={16} /> Add Student
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
        title={selectedStudent ? 'Edit Student' : 'Add Student'}
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
              <label className="block text-sm font-medium text-gray-700 mb-1">User ID</label>
              <input
                type="number"
                value={userId}
                onChange={(e) => setUserId(e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. 1"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Student ID</label>
              <input
                type="text"
                value={studentIdStr}
                onChange={(e) => setStudentIdStr(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. STU001"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
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
                  <option key={d.id} value={d.id}>{d.name} ({d.department_code})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Program</label>
              <select
                value={programId}
                onChange={(e) => setProgramId(e.target.value ? Number(e.target.value) : '')}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="">Select Program</option>
                {programs?.map(p => (
                  <option key={p.id} value={p.id}>{p.program_name}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Semester</label>
              <select
                value={semesterId}
                onChange={(e) => setSemesterId(e.target.value ? Number(e.target.value) : '')}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="">Select Semester</option>
                {semesters?.map(s => (
                  <option key={s.id} value={s.id}>{s.term} {s.semester_number}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Section</label>
              <select
                value={sectionId}
                onChange={(e) => setSectionId(e.target.value ? Number(e.target.value) : '')}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="">Select Section</option>
                {sections?.map(s => (
                  <option key={s.id} value={s.id}>{s.section_name}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Batch</label>
            <select
              value={batchId}
              onChange={(e) => setBatchId(e.target.value ? Number(e.target.value) : '')}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              <option value="">Select Batch</option>
              {batches?.map(b => (
                <option key={b.id} value={b.id}>{b.batch_name}</option>
              ))}
            </select>
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
        title="Delete Student"
        message={`Are you sure you want to delete student ${selectedStudent?.student_id}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedStudent && deleteMutation.mutate(selectedStudent.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
