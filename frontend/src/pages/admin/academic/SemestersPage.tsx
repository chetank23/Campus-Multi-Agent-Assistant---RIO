import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column } from '@/components/common/DataTable';
import { FormModal } from '@/components/common/FormModal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { semestersApi, type SemesterResponse, type SemesterUpdate } from '@/api/semesters';
import { academicYearsApi } from '@/api/academicYears';

export function SemestersPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedSemester, setSelectedSemester] = useState<SemesterResponse | null>(null);
  
  // Form State
  const [academicYearId, setAcademicYearId] = useState<number | ''>('');
  const [term, setTerm] = useState('FALL');
  const [semesterNumber, setSemesterNumber] = useState<number | ''>('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [isActive, setIsActive] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['semesters'],
    queryFn: semestersApi.getAll,
  });

  const { data: years } = useQuery({
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
    mutationFn: semestersApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['semesters'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create semester.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, sem }: { id: number; sem: SemesterUpdate }) => semestersApi.update(id, sem),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['semesters'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update semester.'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: semestersApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['semesters'] });
      setIsConfirmOpen(false);
      setSelectedSemester(null);
    },
    onError: (err: unknown) => {
      alert(getErrorMsg(err, 'Failed to delete semester. It might be in use.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<SemesterResponse>[] = [
    { header: 'ID', accessor: 'id' },
    { 
      header: 'Academic Year', 
      render: (row) => years?.find(y => y.id === row.academic_year_id)?.year_name || `ID: ${row.academic_year_id}` 
    },
    { header: 'Term', accessor: 'term' },
    { header: 'Number', accessor: 'semester_number' },
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

  const handleEdit = (sem: SemesterResponse) => {
    setSelectedSemester(sem);
    setAcademicYearId(sem.academic_year_id);
    setTerm(sem.term);
    setSemesterNumber(sem.semester_number);
    setStartDate(sem.start_date.split('T')[0]);
    setEndDate(sem.end_date.split('T')[0]);
    setIsActive(sem.is_active);
    setFormError(null);
    setIsFormOpen(true);
  };

  const handleDeleteClick = (sem: SemesterResponse) => {
    setSelectedSemester(sem);
    setIsConfirmOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedSemester(null);
    setAcademicYearId('');
    setTerm('FALL');
    setSemesterNumber('');
    setStartDate('');
    setEndDate('');
    setIsActive(false);
    setFormError(null);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (academicYearId === '' || semesterNumber === '' || !startDate || !endDate) {
      setFormError('All fields are required.');
      return;
    }

    if (new Date(startDate) >= new Date(endDate)) {
      setFormError('End date must be after start date.');
      return;
    }

    const payload = {
      academic_year_id: Number(academicYearId),
      term,
      semester_number: Number(semesterNumber),
      start_date: startDate,
      end_date: endDate,
      is_active: isActive,
    };

    if (selectedSemester) {
      updateMutation.mutate({ id: selectedSemester.id, sem: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Semesters</h2>
          <p className="text-sm text-gray-500 mt-1">Manage academic semesters.</p>
        </div>
        <button
          onClick={() => setIsFormOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          <Plus size={16} /> Add Semester
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
        title={selectedSemester ? 'Edit Semester' : 'Add Semester'}
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-red-50 text-red-700 text-sm rounded-lg border border-red-200">
              {formError}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Academic Year</label>
            <select
              value={academicYearId}
              onChange={(e) => setAcademicYearId(e.target.value ? Number(e.target.value) : '')}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              <option value="">Select Year</option>
              {years?.map(y => (
                <option key={y.id} value={y.id}>{y.year_name}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Term</label>
              <select
                value={term}
                onChange={(e) => setTerm(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="FALL">FALL</option>
                <option value="SPRING">SPRING</option>
                <option value="SUMMER">SUMMER</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Semester Number</label>
              <input
                type="number"
                min="1"
                max="10"
                value={semesterNumber}
                onChange={(e) => setSemesterNumber(e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. 1"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
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
              id="isActiveSem"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
            <label htmlFor="isActiveSem" className="text-sm font-medium text-gray-700">
              Active Semester
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
        title="Delete Semester"
        message={`Are you sure you want to delete ${selectedSemester?.term} - ${selectedSemester?.semester_number}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedSemester && deleteMutation.mutate(selectedSemester.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
