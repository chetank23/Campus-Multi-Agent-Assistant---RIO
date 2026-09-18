import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column } from '@/components/common/DataTable';
import { FormModal } from '@/components/common/FormModal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { academicYearsApi, type AcademicYearResponse, type AcademicYearUpdate } from '@/api/academicYears';

export function AcademicYearsPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedYear, setSelectedYear] = useState<AcademicYearResponse | null>(null);
  
  // Form State
  const [yearName, setYearName] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [isActive, setIsActive] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['academic-years'],
    queryFn: academicYearsApi.getAll,
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
    mutationFn: academicYearsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['academic-years'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create academic year.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, year }: { id: number; year: AcademicYearUpdate }) => academicYearsApi.update(id, year),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['academic-years'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update academic year.'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: academicYearsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['academic-years'] });
      setIsConfirmOpen(false);
      setSelectedYear(null);
    },
    onError: (err: unknown) => {
      alert(getErrorMsg(err, 'Failed to delete academic year. It might be in use.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<AcademicYearResponse>[] = [
    { header: 'ID', accessor: 'id' },
    { header: 'Name', accessor: 'year_name' },
    { header: 'Start Date', render: (row) => new Date(row.start_date).toLocaleDateString() },
    { header: 'End Date', render: (row) => new Date(row.end_date).toLocaleDateString() },
    { 
      header: 'Status', 
      render: (row) => (
        <span className={`px-2 py-1 rounded-full text-xs font-semibold ${row.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}`}>
          {row.is_active ? 'Active' : 'Inactive'}
        </span>
      ) 
    },
  ];

  const handleEdit = (year: AcademicYearResponse) => {
    setSelectedYear(year);
    setYearName(year.year_name);
    setStartDate(year.start_date.split('T')[0]);
    setEndDate(year.end_date.split('T')[0]);
    setIsActive(year.is_active);
    setFormError(null);
    setIsFormOpen(true);
  };

  const handleDeleteClick = (year: AcademicYearResponse) => {
    setSelectedYear(year);
    setIsConfirmOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedYear(null);
    setYearName('');
    setStartDate('');
    setEndDate('');
    setIsActive(false);
    setFormError(null);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (!yearName.trim() || !startDate || !endDate) {
      setFormError('Name, start date, and end date are required.');
      return;
    }

    if (new Date(startDate) >= new Date(endDate)) {
      setFormError('End date must be after start date.');
      return;
    }

    const payload = {
      year_name: yearName.trim(),
      start_date: startDate,
      end_date: endDate,
      is_active: isActive,
    };

    if (selectedYear) {
      updateMutation.mutate({ id: selectedYear.id, year: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Academic Years</h2>
          <p className="text-sm text-gray-500 mt-1">Manage academic years.</p>
        </div>
        <button
          onClick={() => setIsFormOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          <Plus size={16} /> Add Year
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
        title={selectedYear ? 'Edit Academic Year' : 'Add Academic Year'}
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-red-50 text-red-700 text-sm rounded-lg border border-red-200">
              {formError}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Year Name</label>
            <input
              type="text"
              value={yearName}
              onChange={(e) => setYearName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="e.g. 2023-2024"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <input
              type="checkbox"
              id="isActive"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
            <label htmlFor="isActive" className="text-sm font-medium text-gray-700">
              Active Year
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
        title="Delete Academic Year"
        message={`Are you sure you want to delete ${selectedYear?.year_name}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedYear && deleteMutation.mutate(selectedYear.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
