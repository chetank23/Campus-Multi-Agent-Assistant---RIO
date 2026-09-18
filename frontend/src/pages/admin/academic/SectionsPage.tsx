import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column } from '@/components/common/DataTable';
import { FormModal } from '@/components/common/FormModal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { sectionsApi, type SectionResponse, type SectionUpdate } from '@/api/sections';
import { departmentsApi } from '@/api/departments';
import { programsApi } from '@/api/programs';
import { semestersApi } from '@/api/semesters';

export function SectionsPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedSection, setSelectedSection] = useState<SectionResponse | null>(null);
  
  // Form State
  const [departmentId, setDepartmentId] = useState<number | ''>('');
  const [programId, setProgramId] = useState<number | ''>('');
  const [semesterId, setSemesterId] = useState<number | ''>('');
  const [sectionName, setSectionName] = useState('');
  const [studentCount, setStudentCount] = useState<number | ''>('');
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['sections'],
    queryFn: sectionsApi.getAll,
  });

  const { data: departments } = useQuery({ queryKey: ['departments'], queryFn: departmentsApi.getAll });
  const { data: programs } = useQuery({ queryKey: ['programs'], queryFn: programsApi.getAll });
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
    mutationFn: sectionsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sections'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create section.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, sec }: { id: number; sec: SectionUpdate }) => sectionsApi.update(id, sec),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sections'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update section.'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: sectionsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sections'] });
      setIsConfirmOpen(false);
      setSelectedSection(null);
    },
    onError: (err: unknown) => {
      alert(getErrorMsg(err, 'Failed to delete section. It might be in use.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<SectionResponse>[] = [
    { header: 'ID', accessor: 'id' },
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
    { header: 'Section Name', accessor: 'section_name' },
    { header: 'Student Count', accessor: 'student_count' },
  ];

  const handleEdit = (sec: SectionResponse) => {
    setSelectedSection(sec);
    setDepartmentId(sec.department_id);
    setProgramId(sec.program_id);
    setSemesterId(sec.semester_id);
    setSectionName(sec.section_name);
    setStudentCount(sec.student_count);
    setFormError(null);
    setIsFormOpen(true);
  };

  const handleDeleteClick = (sec: SectionResponse) => {
    setSelectedSection(sec);
    setIsConfirmOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedSection(null);
    setDepartmentId('');
    setProgramId('');
    setSemesterId('');
    setSectionName('');
    setStudentCount('');
    setFormError(null);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (departmentId === '' || programId === '' || semesterId === '' || !sectionName.trim() || studentCount === '') {
      setFormError('All fields are required.');
      return;
    }

    const payload = {
      department_id: Number(departmentId),
      program_id: Number(programId),
      semester_id: Number(semesterId),
      section_name: sectionName.trim(),
      student_count: Number(studentCount),
    };

    if (selectedSection) {
      updateMutation.mutate({ id: selectedSection.id, sec: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Sections</h2>
          <p className="text-sm text-gray-500 mt-1">Manage class sections.</p>
        </div>
        <button
          onClick={() => setIsFormOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          <Plus size={16} /> Add Section
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
        title={selectedSection ? 'Edit Section' : 'Add Section'}
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-red-50 text-red-700 text-sm rounded-lg border border-red-200">
              {formError}
            </div>
          )}
          
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

          <div className="grid grid-cols-2 gap-4">
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
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Section Name</label>
              <input
                type="text"
                value={sectionName}
                onChange={(e) => setSectionName(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. A"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Student Count</label>
              <input
                type="number"
                min="1"
                value={studentCount}
                onChange={(e) => setStudentCount(e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. 60"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
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
        title="Delete Section"
        message={`Are you sure you want to delete section ${selectedSection?.section_name}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedSection && deleteMutation.mutate(selectedSection.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
