import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column } from '@/components/common/DataTable';
import { FormModal } from '@/components/common/FormModal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { facultyApi, type FacultyResponse, type FacultyUpdate } from '@/api/faculty';
import { departmentsApi } from '@/api/departments';

export function FacultyPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedFaculty, setSelectedFaculty] = useState<FacultyResponse | null>(null);
  
  // Form State
  const [userId, setUserId] = useState<number | ''>('');
  const [departmentId, setDepartmentId] = useState<number | ''>('');
  const [designation, setDesignation] = useState('');
  const [maxHours, setMaxHours] = useState<number | ''>('');
  const [isActive, setIsActive] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['faculty'],
    queryFn: facultyApi.getAll,
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
    mutationFn: facultyApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['faculty'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create faculty.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, fac }: { id: number; fac: FacultyUpdate }) => facultyApi.update(id, fac),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['faculty'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update faculty.'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: facultyApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['faculty'] });
      setIsConfirmOpen(false);
      setSelectedFaculty(null);
    },
    onError: (err: unknown) => {
      alert(getErrorMsg(err, 'Failed to delete faculty.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<FacultyResponse>[] = [
    { header: 'ID', accessor: 'id' },
    { header: 'User ID', accessor: 'user_id' },
    { 
      header: 'Department', 
      render: (row) => departments?.find(d => d.id === row.department_id)?.name || `ID: ${row.department_id}` 
    },
    { header: 'Designation', accessor: 'designation' },
    { header: 'Max Hrs/Wk', accessor: 'max_hours_per_week' },
    { 
      header: 'Status', 
      render: (row) => (
        <span className={`px-2 py-1 rounded-full text-xs font-semibold ${row.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}`}>
          {row.is_active ? 'Active' : 'Inactive'}
        </span>
      ) 
    },
  ];

  const handleEdit = (fac: FacultyResponse) => {
    setSelectedFaculty(fac);
    setUserId(fac.user_id);
    setDepartmentId(fac.department_id);
    setDesignation(fac.designation);
    setMaxHours(fac.max_hours_per_week);
    setIsActive(fac.is_active);
    setFormError(null);
    setIsFormOpen(true);
  };

  const handleDeleteClick = (fac: FacultyResponse) => {
    setSelectedFaculty(fac);
    setIsConfirmOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedFaculty(null);
    setUserId('');
    setDepartmentId('');
    setDesignation('');
    setMaxHours('');
    setIsActive(true);
    setFormError(null);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (userId === '' || departmentId === '' || !designation.trim() || maxHours === '') {
      setFormError('All fields are required.');
      return;
    }

    const payload = {
      user_id: Number(userId),
      department_id: Number(departmentId),
      designation: designation.trim(),
      max_hours_per_week: Number(maxHours),
      is_active: isActive,
    };

    if (selectedFaculty) {
      updateMutation.mutate({ id: selectedFaculty.id, fac: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Faculty</h2>
          <p className="text-sm text-gray-500 mt-1">Manage faculty academic profiles.</p>
        </div>
        <button
          onClick={() => setIsFormOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          <Plus size={16} /> Add Faculty
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
        title={selectedFaculty ? 'Edit Faculty' : 'Add Faculty'}
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
                placeholder="e.g. 2"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
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
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Designation</label>
              <input
                type="text"
                value={designation}
                onChange={(e) => setDesignation(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. Professor"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Max Hours / Week</label>
              <input
                type="number"
                min="1"
                value={maxHours}
                onChange={(e) => setMaxHours(e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. 40"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
          </div>

          <div className="flex items-center gap-2 mt-2">
            <input
              type="checkbox"
              id="isActiveFac"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
            <label htmlFor="isActiveFac" className="text-sm font-medium text-gray-700">
              Active
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
        title="Delete Faculty"
        message={`Are you sure you want to delete faculty record for User ID ${selectedFaculty?.user_id}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedFaculty && deleteMutation.mutate(selectedFaculty.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
