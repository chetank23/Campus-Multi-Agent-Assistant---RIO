import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, CalendarDays } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column, FormModal, ConfirmDialog, PageHeader, StatusBadge } from '@/components/common';
import { academicYearsApi, type AcademicYearResponse, type AcademicYearUpdate } from '@/api/academicYears';

export function AcademicYearsPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedYear, setSelectedYear] = useState<AcademicYearResponse | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  
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

  const filteredData = useMemo(() => {
    if (!data) return [];
    if (!searchTerm.trim()) return data;
    const term = searchTerm.toLowerCase();
    return data.filter(
      (ay) =>
        ay.year_name.toLowerCase().includes(term) ||
        String(ay.id).includes(term)
    );
  }, [data, searchTerm]);

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
      alert(getErrorMsg(err, 'Failed to delete academic year. It might be in use by active semesters or timetables.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<AcademicYearResponse>[] = [
    {
      header: 'ID',
      accessor: 'id',
      render: (row) => <span className="font-tabular text-slate-500 font-medium">#{row.id}</span>,
    },
    {
      header: 'Academic Year',
      accessor: 'year_name',
      render: (row) => <span className="font-semibold text-slate-900">{row.year_name}</span>,
    },
    {
      header: 'Session Start',
      render: (row) => (
        <span className="font-tabular text-slate-700">
          {new Date(row.start_date).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
        </span>
      ),
    },
    {
      header: 'Session Concludes',
      render: (row) => (
        <span className="font-tabular text-slate-700">
          {new Date(row.end_date).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
        </span>
      ),
    },
    {
      header: 'Active State',
      render: (row) => (
        <StatusBadge
          status={row.is_active ? 'ACTIVE' : 'INACTIVE'}
          label={row.is_active ? 'Current Year' : 'Archived'}
        />
      ),
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
      setFormError('Academic year title, start date, and end date are required.');
      return;
    }

    const payload = {
      year_name: yearName.trim(),
      start_date: new Date(startDate).toISOString(),
      end_date: new Date(endDate).toISOString(),
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
      <PageHeader
        title="Academic Years"
        subtitle="Configure institution calendar cycles, operational academic periods, and term date boundaries."
        icon={<CalendarDays size={20} />}
        actions={
          <button
            onClick={() => setIsFormOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-xs font-semibold uppercase tracking-wider shadow-xs focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2"
          >
            <Plus size={15} /> Add Academic Year
          </button>
        }
      />

      <DataTable
        title="Calendar Sessions"
        subtitle="Institutional cycle history"
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
        searchPlaceholder="Filter academic years…"
        emptyMessage="No academic years found matching your search."
      />

      <FormModal
        isOpen={isFormOpen}
        title={selectedYear ? 'Edit Academic Year' : 'Register Academic Year'}
        subtitle="Set term boundaries and active status for scheduling algorithms"
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-rose-50 text-rose-800 text-xs rounded-lg border border-rose-200 font-medium">
              {formError}
            </div>
          )}
          <div>
            <label className="academic-label">Year Name</label>
            <input
              type="text"
              value={yearName}
              onChange={(e) => setYearName(e.target.value)}
              className="academic-input font-tabular"
              placeholder="e.g. 2024-2025"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="academic-label">Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="academic-input font-tabular"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="academic-label">End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="academic-input font-tabular"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
          </div>
          <div className="pt-2">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="w-4 h-4 rounded text-primary-600 border-slate-300 focus:ring-primary-600"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
              <span className="text-xs font-semibold text-slate-700">Set as Current Active Academic Year</span>
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
              {createMutation.isPending || updateMutation.isPending ? 'Saving…' : 'Save Academic Year'}
            </button>
          </div>
        </form>
      </FormModal>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Academic Year"
        message={`Are you sure you want to delete ${selectedYear?.year_name}? This action cannot be undone and will delete linked terms and timetables.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedYear && deleteMutation.mutate(selectedYear.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
