import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, GraduationCap } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column, FormModal, ConfirmDialog, PageHeader, StatusBadge } from '@/components/common';
import { facultyApi, type FacultyResponse, type FacultyUpdate } from '@/api/faculty';
import { departmentsApi } from '@/api/departments';

export function FacultyPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedFaculty, setSelectedFaculty] = useState<FacultyResponse | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  
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

  const filteredData = useMemo(() => {
    if (!data) return [];
    if (!searchTerm.trim()) return data;
    const term = searchTerm.toLowerCase();
    return data.filter((fac) => {
      const deptName = departments?.find((d) => d.id === fac.department_id)?.name?.toLowerCase() || '';
      const facultyName = fac.name?.toLowerCase() || '';
      return (
        facultyName.includes(term) ||
        fac.designation.toLowerCase().includes(term) ||
        deptName.includes(term) ||
        String(fac.id).includes(term) ||
        String(fac.user_id).includes(term) ||
        (fac.contact_number && fac.contact_number.toLowerCase().includes(term))
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
    mutationFn: facultyApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['faculty'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create faculty member.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, fac }: { id: number; fac: FacultyUpdate }) => facultyApi.update(id, fac),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['faculty'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update faculty member.'));
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
      alert(getErrorMsg(err, 'Failed to delete faculty member. They might be assigned to active courses.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<FacultyResponse>[] = [
    {
      header: 'Faculty ID',
      accessor: 'id',
      render: (row) => (
        <div className="font-mono text-xs font-bold text-slate-700 font-tabular">
          FAC-{String(row.id).padStart(3, '0')}
        </div>
      ),
    },
    {
      header: 'Faculty Name',
      render: (row) => (
        <div>
          <div className="font-semibold text-slate-900">{row.name || `Faculty Member #${row.id}`}</div>
          <div className="text-[11px] text-slate-400">User ID: #{row.user_id}</div>
        </div>
      ),
    },
    { 
      header: 'Department', 
      render: (row) => {
        const d = departments?.find((dept) => dept.id === row.department_id);
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-slate-100 text-slate-800 border border-slate-200">
            {d ? `${d.department_code} - ${d.name}` : `Dept #${row.department_id}`}
          </span>
        );
      },
    },
    {
      header: 'Designation',
      accessor: 'designation',
      render: (row) => <span className="font-medium text-slate-800">{row.designation}</span>,
    },
    {
      header: 'Contact Number',
      render: (row) => <span className="text-slate-600 font-tabular text-xs">{row.contact_number || '—'}</span>,
    },
    {
      header: 'Max Weekly Load',
      accessor: 'max_hours_per_week',
      render: (row) => (
        <span className="font-tabular font-semibold text-primary-800">
          {row.max_hours_per_week} hrs/wk
        </span>
      ),
    },
    { 
      header: 'Status', 
      render: (row) => (
        <StatusBadge
          status={row.is_active ? 'ACTIVE' : 'INACTIVE'}
          label={row.is_active ? 'Active' : 'On Leave'}
        />
      ),
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
      setFormError('All faculty fields are required.');
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
      <PageHeader
        title="Faculty Directory"
        subtitle="Manage teaching faculty appointments, academic designations, weekly workload limits, and school affiliations."
        icon={<GraduationCap size={20} />}
        actions={
          <button
            onClick={() => setIsFormOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-xs font-semibold uppercase tracking-wider shadow-xs focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2"
          >
            <Plus size={15} /> Add Faculty
          </button>
        }
      />

      <DataTable
        title="Teaching Faculty Register"
        subtitle="Active faculty workload profiles"
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
        searchPlaceholder="Filter by name, designation, department…"
        emptyMessage="No faculty records found matching your search."
      />

      <FormModal
        isOpen={isFormOpen}
        title={selectedFaculty ? 'Edit Faculty Record' : 'Register Faculty Member'}
        subtitle="Configure department affiliation, academic ranking, and weekly teaching workload caps"
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-rose-50 text-rose-800 text-xs rounded-lg border border-rose-200 font-medium">
              {formError}
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="academic-label">User Account ID</label>
              <input
                type="number"
                value={userId}
                onChange={(e) => setUserId(e.target.value === '' ? '' : Number(e.target.value))}
                className="academic-input font-tabular"
                placeholder="e.g. 5"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="academic-label">Department</label>
              <select
                value={departmentId}
                onChange={(e) => setDepartmentId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="">Select department…</option>
                {departments?.map((d) => (
                  <option key={d.id} value={d.id}>{d.name} ({d.department_code})</option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="academic-label">Designation</label>
              <input
                type="text"
                value={designation}
                onChange={(e) => setDesignation(e.target.value)}
                className="academic-input"
                placeholder="e.g. Associate Professor"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="academic-label">Max Teaching Hours / Week</label>
              <input
                type="number"
                min="1"
                max="50"
                value={maxHours}
                onChange={(e) => setMaxHours(e.target.value === '' ? '' : Number(e.target.value))}
                className="academic-input font-tabular"
                placeholder="e.g. 18"
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
              <span className="text-xs font-semibold text-slate-700">Active Teaching Status (Available for Timetable Scheduling)</span>
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
              {createMutation.isPending || updateMutation.isPending ? 'Saving…' : 'Save Faculty'}
            </button>
          </div>
        </form>
      </FormModal>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Faculty Member"
        message={`Are you sure you want to delete this faculty member? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedFaculty && deleteMutation.mutate(selectedFaculty.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
