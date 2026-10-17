import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, GraduationCap } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column, FormModal, ConfirmDialog, PageHeader } from '@/components/common';
import { programsApi, type ProgramResponse, type ProgramUpdate } from '@/api/programs';
import { departmentsApi } from '@/api/departments';

export function ProgramsPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedProgram, setSelectedProgram] = useState<ProgramResponse | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  
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

  const filteredData = useMemo(() => {
    if (!data) return [];
    if (!searchTerm.trim()) return data;
    const term = searchTerm.toLowerCase();
    return data.filter((prog) => {
      const deptName = departments?.find((d) => d.id === prog.department_id)?.name?.toLowerCase() || '';
      return (
        prog.program_name.toLowerCase().includes(term) ||
        prog.degree.toLowerCase().includes(term) ||
        deptName.includes(term) ||
        String(prog.id).includes(term)
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
      alert(getErrorMsg(err, 'Failed to delete program. It might be referenced by batches or courses.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<ProgramResponse>[] = [
    {
      header: 'ID',
      accessor: 'id',
      render: (row) => <span className="font-tabular text-slate-500 font-medium">#{row.id}</span>,
    },
    {
      header: 'Program Title',
      accessor: 'program_name',
      render: (row) => <span className="font-semibold text-slate-900">{row.program_name}</span>,
    },
    {
      header: 'Degree',
      accessor: 'degree',
      render: (row) => (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-primary-50 text-primary-800 border border-primary-200">
          {row.degree}
        </span>
      ),
    },
    {
      header: 'Parent Department',
      render: (row) => {
        const dept = departments?.find((d) => d.id === row.department_id);
        return (
          <span className="text-slate-700">
            {dept ? `${dept.name} (${dept.department_code})` : `Dept ID: ${row.department_id}`}
          </span>
        );
      },
    },
    {
      header: 'Duration',
      accessor: 'duration',
      render: (row) => (
        <span className="font-tabular text-slate-700">
          {row.duration} {row.duration === 1 ? 'Year' : 'Years'}
        </span>
      ),
    },
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
      setFormError('All program fields are required.');
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
      <PageHeader
        title="Degree Programs"
        subtitle="Manage undergraduate, graduate, and doctoral academic programs and curriculum structures."
        icon={<GraduationCap size={20} />}
        actions={
          <button
            onClick={() => setIsFormOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-xs font-semibold uppercase tracking-wider shadow-xs focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2"
          >
            <Plus size={15} /> Add Program
          </button>
        }
      />

      <DataTable
        title="Degree Program Registry"
        subtitle="Accredited degree courses"
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
        searchPlaceholder="Filter programs…"
        emptyMessage="No programs found matching your search."
      />

      <FormModal
        isOpen={isFormOpen}
        title={selectedProgram ? 'Edit Degree Program' : 'Register Degree Program'}
        subtitle="Define degree designation, department affiliation, and standard course duration"
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-rose-50 text-rose-800 text-xs rounded-lg border border-rose-200 font-medium">
              {formError}
            </div>
          )}
          <div>
            <label className="academic-label">Academic Department</label>
            <select
              value={departmentId}
              onChange={(e) => setDepartmentId(e.target.value ? Number(e.target.value) : '')}
              className="academic-input"
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              <option value="">Select affiliated department…</option>
              {departments?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.department_code})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="academic-label">Program Name</label>
            <input
              type="text"
              value={programName}
              onChange={(e) => setProgramName(e.target.value)}
              className="academic-input"
              placeholder="e.g. Computer Science & Engineering"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="academic-label">Degree Designation</label>
              <input
                type="text"
                value={degree}
                onChange={(e) => setDegree(e.target.value)}
                className="academic-input"
                placeholder="e.g. B.Tech, M.Tech, Ph.D"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="academic-label">Duration (Years)</label>
              <input
                type="number"
                min="1"
                max="10"
                value={duration}
                onChange={(e) => setDuration(e.target.value === '' ? '' : Number(e.target.value))}
                className="academic-input font-tabular"
                placeholder="e.g. 4"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
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
              {createMutation.isPending || updateMutation.isPending ? 'Saving…' : 'Save Program'}
            </button>
          </div>
        </form>
      </FormModal>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Degree Program"
        message={`Are you sure you want to delete ${selectedProgram?.program_name}? This will affect all associated batches, sections, and historical timetable records.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedProgram && deleteMutation.mutate(selectedProgram.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
