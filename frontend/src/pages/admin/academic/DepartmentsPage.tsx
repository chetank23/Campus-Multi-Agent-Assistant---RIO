import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column } from '@/components/common/DataTable';
import { FormModal } from '@/components/common/FormModal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { departmentsApi, type DepartmentResponse, type DepartmentUpdate } from '@/api/departments';

export function DepartmentsPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedDept, setSelectedDept] = useState<DepartmentResponse | null>(null);
  
  // Form State
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  // Queries & Mutations
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['departments'],
    queryFn: departmentsApi.getAll,
  });

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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['departments'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create department.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, dept }: { id: number; dept: DepartmentUpdate }) => departmentsApi.update(id, dept),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['departments'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update department.'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: departmentsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['departments'] });
      setIsConfirmOpen(false);
      setSelectedDept(null);
    },
    onError: (err: unknown) => {
      alert(getErrorMsg(err, 'Failed to delete department. It might be in use.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<DepartmentResponse>[] = [
    { header: 'ID', accessor: 'id' },
    { header: 'Code', accessor: 'department_code' },
    { header: 'Name', accessor: 'name' },
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
      setFormError('Code and Name are required.');
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
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Departments</h2>
          <p className="text-sm text-gray-500 mt-1">Manage academic departments.</p>
        </div>
        <button
          onClick={() => setIsFormOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          <Plus size={16} /> Add Department
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
        title={selectedDept ? 'Edit Department' : 'Add Department'}
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-red-50 text-red-700 text-sm rounded-lg border border-red-200">
              {formError}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Code</label>
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="e.g. CS"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="e.g. Computer Science"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
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
        title="Delete Department"
        message={`Are you sure you want to delete ${selectedDept?.name}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedDept && deleteMutation.mutate(selectedDept.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
