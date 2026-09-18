import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column } from '@/components/common/DataTable';
import { FormModal } from '@/components/common/FormModal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { programsApi, type ProgramResponse, type ProgramUpdate } from '@/api/programs';
import { departmentsApi } from '@/api/departments';

export function ProgramsPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedProgram, setSelectedProgram] = useState<ProgramResponse | null>(null);
  
  // Form State
  const [departmentId, setDepartmentId] = useState<number | ''>('');
  const [programName, setProgramName] = useState('');
  const [degree, setDegree] = useState('');
  const [duration, setDuration] = useState<number | ''>('');
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['programs'],
    queryFn: programsApi.getAll,
  });

  const { data: departments } = useQuery({
    queryKey: ['departments'],
    queryFn: departmentsApi.getAll,
  });

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
    mutationFn: programsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['programs'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create program.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, prog }: { id: number; prog: ProgramUpdate }) => programsApi.update(id, prog),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['programs'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update program.'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: programsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['programs'] });
      setIsConfirmOpen(false);
      setSelectedProgram(null);
    },
    onError: (err: unknown) => {
      alert(getErrorMsg(err, 'Failed to delete program. It might be in use.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<ProgramResponse>[] = [
    { header: 'ID', accessor: 'id' },
    { 
      header: 'Department', 
      render: (row) => departments?.find(d => d.id === row.department_id)?.name || `ID: ${row.department_id}` 
    },
    { header: 'Program Name', accessor: 'program_name' },
    { header: 'Degree', accessor: 'degree' },
    { header: 'Duration (Years)', accessor: 'duration' },
  ];

  const handleEdit = (prog: ProgramResponse) => {
    setSelectedProgram(prog);
    setDepartmentId(prog.department_id);
    setProgramName(prog.program_name);
    setDegree(prog.degree);
    setDuration(prog.duration);
    setFormError(null);
    setIsFormOpen(true);
  };

  const handleDeleteClick = (prog: ProgramResponse) => {
    setSelectedProgram(prog);
    setIsConfirmOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedProgram(null);
    setDepartmentId('');
    setProgramName('');
    setDegree('');
    setDuration('');
    setFormError(null);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (departmentId === '' || !programName.trim() || !degree.trim() || duration === '') {
      setFormError('All fields are required.');
      return;
    }

    const payload = {
      department_id: Number(departmentId),
      program_name: programName.trim(),
      degree: degree.trim(),
      duration: Number(duration),
    };

    if (selectedProgram) {
      updateMutation.mutate({ id: selectedProgram.id, prog: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Programs</h2>
          <p className="text-sm text-gray-500 mt-1">Manage academic programs and degrees.</p>
        </div>
        <button
          onClick={() => setIsFormOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          <Plus size={16} /> Add Program
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
        title={selectedProgram ? 'Edit Program' : 'Add Program'}
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
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Program Name</label>
            <input
              type="text"
              value={programName}
              onChange={(e) => setProgramName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="e.g. B.Tech Computer Science"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Degree</label>
              <input
                type="text"
                value={degree}
                onChange={(e) => setDegree(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. B.Tech"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Duration (Years)</label>
              <input
                type="number"
                min="1"
                max="10"
                value={duration}
                onChange={(e) => setDuration(e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. 4"
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
        title="Delete Program"
        message={`Are you sure you want to delete ${selectedProgram?.program_name}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedProgram && deleteMutation.mutate(selectedProgram.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
