import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Layers } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column, FormModal, ConfirmDialog, PageHeader, StatusBadge } from '@/components/common';
import { semestersApi, type SemesterResponse, type SemesterUpdate } from '@/api/semesters';
import { academicYearsApi } from '@/api/academicYears';

export function SemestersPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedSemester, setSelectedSemester] = useState<SemesterResponse | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  
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

  const filteredData = useMemo(() => {
    if (!data) return [];
    if (!searchTerm.trim()) return data;
    const s = searchTerm.toLowerCase();
    return data.filter((sem) => {
      const yearName = years?.find((y) => y.id === sem.academic_year_id)?.year_name?.toLowerCase() || '';
      return (
        sem.term.toLowerCase().includes(s) ||
        String(sem.semester_number).includes(s) ||
        yearName.includes(s) ||
        String(sem.id).includes(s)
      );
    });
  }, [data, years, searchTerm]);

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
      alert(getErrorMsg(err, 'Failed to delete semester. It might be referenced by sections or course assignments.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<SemesterResponse>[] = [
    {
      header: 'ID',
      accessor: 'id',
      render: (row) => <span className="font-tabular text-slate-500 font-medium">#{row.id}</span>,
    },
    { 
      header: 'Academic Year', 
      render: (row) => {
        const y = years?.find((year) => year.id === row.academic_year_id);
        return <span className="font-semibold text-slate-900">{y ? y.year_name : `Year #${row.academic_year_id}`}</span>;
      },
    },
    {
      header: 'Term',
      accessor: 'term',
      render: (row) => (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
          {row.term}
        </span>
      ),
    },
    {
      header: 'Semester',
      accessor: 'semester_number',
      render: (row) => (
        <span className="font-tabular font-semibold text-primary-800">
          Semester {row.semester_number}
        </span>
      ),
    },
    {
      header: 'Start Date',
      render: (row) => (
        <span className="font-tabular text-slate-700">
          {new Date(row.start_date).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
        </span>
      ),
    },
    {
      header: 'End Date',
      render: (row) => (
        <span className="font-tabular text-slate-700">
          {new Date(row.end_date).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
        </span>
      ),
    },
    { 
      header: 'Status', 
      render: (row) => (
        <StatusBadge
          status={row.is_active ? 'ACTIVE' : 'INACTIVE'}
          label={row.is_active ? 'Active Term' : 'Concluded'}
        />
      ),
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
      setFormError('All semester fields are required.');
      return;
    }

    const payload = {
      academic_year_id: Number(academicYearId),
      term,
      semester_number: Number(semesterNumber),
      start_date: new Date(startDate).toISOString(),
      end_date: new Date(endDate).toISOString(),
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
      <PageHeader
        title="Academic Semesters"
        subtitle="Configure semester terms (Fall, Spring, Summer) and academic sequencing for class schedules."
        icon={<Layers size={20} />}
        actions={
          <button
            onClick={() => setIsFormOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-xs font-semibold uppercase tracking-wider shadow-xs focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2"
          >
            <Plus size={15} /> Add Semester
          </button>
        }
      />

      <DataTable
        title="Semester Term Registry"
        subtitle="Term sequencing across academic years"
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
        searchPlaceholder="Filter semesters…"
        emptyMessage="No semesters found matching your search."
      />

      <FormModal
        isOpen={isFormOpen}
        title={selectedSemester ? 'Edit Academic Semester' : 'Register Academic Semester'}
        subtitle="Set term designation, semester number, and date range"
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-rose-50 text-rose-800 text-xs rounded-lg border border-rose-200 font-medium">
              {formError}
            </div>
          )}
          <div>
            <label className="academic-label">Academic Year</label>
            <select
              value={academicYearId}
              onChange={(e) => setAcademicYearId(e.target.value ? Number(e.target.value) : '')}
              className="academic-input"
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              <option value="">Select calendar year…</option>
              {years?.map((y) => (
                <option key={y.id} value={y.id}>{y.year_name}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="academic-label">Term</label>
              <select
                value={term}
                onChange={(e) => setTerm(e.target.value)}
                className="academic-input"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="FALL">FALL</option>
                <option value="SPRING">SPRING</option>
                <option value="SUMMER">SUMMER</option>
                <option value="WINTER">WINTER</option>
              </select>
            </div>
            <div>
              <label className="academic-label">Semester Number</label>
              <input
                type="number"
                min="1"
                max="12"
                value={semesterNumber}
                onChange={(e) => setSemesterNumber(e.target.value === '' ? '' : Number(e.target.value))}
                className="academic-input font-tabular"
                placeholder="e.g. 1, 2, 3..."
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
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
              <span className="text-xs font-semibold text-slate-700">Currently Active Semester Term</span>
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
              {createMutation.isPending || updateMutation.isPending ? 'Saving…' : 'Save Semester'}
            </button>
          </div>
        </form>
      </FormModal>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Semester"
        message={`Are you sure you want to delete ${selectedSemester?.term} Semester ${selectedSemester?.semester_number}? This will unlink related sections and timetable assignments.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedSemester && deleteMutation.mutate(selectedSemester.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
