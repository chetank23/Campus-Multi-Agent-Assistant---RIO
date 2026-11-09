import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Building2 } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column, FormModal, ConfirmDialog, PageHeader } from '@/components/common';
import { useToast } from '@/context/useToast';
import { departmentsApi, type DepartmentResponse, type DepartmentUpdate } from '@/api/departments';

export function DepartmentsPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedDept, setSelectedDept] = useState<DepartmentResponse | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Form State
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  // Queries & Mutations
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['departments'],
    queryFn: departmentsApi.getAll,
  });

  const filteredData = useMemo(() => {
    if (!data) return [];
    if (!searchTerm.trim()) return data;
    const term = searchTerm.toLowerCase();
    return data.filter(
      (dept) =>
        dept.department_code.toLowerCase().includes(term) ||
        dept.name.toLowerCase().includes(term) ||
        String(dept.id).includes(term)
    );
  }, [data, searchTerm]);

  const getErrorMsg = (err: unknown, defaultMsg: string) => {
    if (isAxiosError(err)) {
      return err.response?.data?.detail || defaultMsg;
    } else if (err instanceof Error) {
      return err.message;
    }
    return defaultMsg;
  };

  const createMutation = useMutation({
    mutationFn: departmentsApi.create,
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['departments'] });
      toast.success(`Department "${res?.name || ''}" created successfully!`);
      closeForm();
    },
    onError: (err: unknown) => {
      const msg = getErrorMsg(err, 'Failed to create department.');
      setFormError(msg);
      toast.error(msg);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, dept }: { id: number; dept: DepartmentUpdate }) => departmentsApi.update(id, dept),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['departments'] });
      toast.success('Department updated successfully!');
      closeForm();
    },
    onError: (err: unknown) => {
      const msg = getErrorMsg(err, 'Failed to update department.');
      setFormError(msg);
      toast.error(msg);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: departmentsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['departments'] });
      toast.success('Department deleted successfully.');
      setIsConfirmOpen(false);
      setSelectedDept(null);
    },
    onError: (err: unknown) => {
      const msg = getErrorMsg(err, 'Failed to delete department. It might be in use by programs or faculty.');
      toast.error(msg);
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<DepartmentResponse>[] = [
    {
      header: 'ID',
      accessor: 'id',
      render: (row) => <span className="font-tabular text-slate-500 font-medium">#{row.id}</span>,
    },
    {
      header: 'Code',
      accessor: 'department_code',
      render: (row) => (
        <span className="inline-flex items-center px-2 py-0.5 rounded font-mono text-xs font-bold bg-slate-100 text-slate-800 border border-slate-200">
          {row.department_code}
        </span>
      ),
    },
    {
      header: 'Department Name',
      accessor: 'name',
      render: (row) => <span className="font-semibold text-slate-900">{row.name}</span>,
    },
  ];

  const handleEdit = (dept: DepartmentResponse) => {
    setSelectedDept(dept);
    setCode(dept.department_code);
    setName(dept.name);
    setFormError(null);
    setIsFormOpen(true);
  };

  const handleDeleteClick = (dept: DepartmentResponse) => {
    setSelectedDept(dept);
    setIsConfirmOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedDept(null);
    setCode('');
    setName('');
    setFormError(null);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (!code.trim() || !name.trim()) {
      setFormError('Department code and name are required.');
      return;
    }

    if (selectedDept) {
      updateMutation.mutate({ id: selectedDept.id, dept: { department_code: code.trim(), name: name.trim() } });
    } else {
      createMutation.mutate({ department_code: code.trim(), name: name.trim() });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Departments"
        subtitle="Manage academic divisions, schools, and institutional faculty units."
        icon={<Building2 size={20} />}
        actions={
          <button
            onClick={() => setIsFormOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-xs font-semibold uppercase tracking-wider shadow-xs focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2"
          >
            <Plus size={15} /> Add Department
          </button>
        }
      />

      <DataTable
        title="Department Registry"
        subtitle="Active faculties and divisions"
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
        searchPlaceholder="Filter departments…"
        emptyMessage="No departments found matching your criteria."
      />

      <FormModal
        isOpen={isFormOpen}
        title={selectedDept ? 'Edit Academic Department' : 'Register New Department'}
        subtitle="Establish department identifiers used across timetables and courses"
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-rose-50 text-rose-800 text-xs rounded-lg border border-rose-200 font-medium">
              {formError}
            </div>
          )}
          <div>
            <label className="academic-label">Department Code</label>
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="academic-input font-mono uppercase"
              placeholder="e.g. CSE"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
            <p className="text-[11px] text-slate-400 mt-1">Short uppercase abbreviation (e.g. CSE, ECE, MECH)</p>
          </div>
          <div>
            <label className="academic-label">Department Full Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="academic-input"
              placeholder="e.g. School of Computer Science & Engineering"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
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
              {createMutation.isPending || updateMutation.isPending ? 'Saving…' : 'Save Department'}
            </button>
          </div>
        </form>
      </FormModal>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Department"
        message={`Are you sure you want to delete ${selectedDept?.name} (${selectedDept?.department_code})? This action cannot be undone and will affect linked programs.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedDept && deleteMutation.mutate(selectedDept.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
