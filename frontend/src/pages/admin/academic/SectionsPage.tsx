import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, BookOpen } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column, FormModal, ConfirmDialog, PageHeader } from '@/components/common';
import { sectionsApi, type SectionResponse, type SectionUpdate } from '@/api/sections';
import { departmentsApi } from '@/api/departments';
import { programsApi } from '@/api/programs';
import { semestersApi } from '@/api/semesters';

export function SectionsPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedSection, setSelectedSection] = useState<SectionResponse | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Form State
  const [departmentId, setDepartmentId] = useState<number | ''>('');
  const [programId, setProgramId] = useState<number | ''>('');
  const [semesterId, setSemesterId] = useState<number | ''>('');
  const [sectionName, setSectionName] = useState('');
  const [studentCount, setStudentCount] = useState<number | ''>('');
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['sections'],
    queryFn: sectionsApi.getAll,
  });

  const { data: departments } = useQuery({ queryKey: ['departments'], queryFn: departmentsApi.getAll });
  const { data: programs } = useQuery({ queryKey: ['programs'], queryFn: programsApi.getAll });
  const { data: semesters } = useQuery({ queryKey: ['semesters'], queryFn: semestersApi.getAll });

  const filteredData = useMemo(() => {
    if (!data) return [];
    if (!searchTerm.trim()) return data;
    const term = searchTerm.toLowerCase();
    return data.filter((sec) => {
      const dept = departments?.find((d) => d.id === sec.department_id)?.department_code?.toLowerCase() || '';
      const prog = programs?.find((p) => p.id === sec.program_id)?.program_name?.toLowerCase() || '';
      return (
        sec.section_name.toLowerCase().includes(term) ||
        dept.includes(term) ||
        prog.includes(term) ||
        String(sec.id).includes(term) ||
        String(sec.student_count).includes(term)
      );
    });
  }, [data, departments, programs, searchTerm]);

  const getErrorMsg = (err: unknown, defaultMsg: string) => {
    if (isAxiosError(err)) {
      return err.response?.data?.detail || defaultMsg;
    } else if (err instanceof Error) {
      return err.message;
    }
    return defaultMsg;
  };

  // Mutations
  const createMutation = useMutation({
    mutationFn: sectionsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sections'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create section.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, sec }: { id: number; sec: SectionUpdate }) => sectionsApi.update(id, sec),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sections'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update section.'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: sectionsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sections'] });
      setIsConfirmOpen(false);
      setSelectedSection(null);
    },
    onError: (err: unknown) => {
      alert(getErrorMsg(err, 'Failed to delete section. It might be referenced by timetable schedules.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<SectionResponse>[] = [
    {
      header: 'ID',
      accessor: 'id',
      render: (row) => <span className="font-tabular text-slate-500 font-medium">#{row.id}</span>,
    },
    { 
      header: 'Department', 
      render: (row) => {
        const dept = departments?.find((d) => d.id === row.department_id);
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded font-mono text-xs font-bold bg-slate-100 text-slate-800 border border-slate-200">
            {dept ? dept.department_code : `#${row.department_id}`}
          </span>
        );
      },
    },
    { 
      header: 'Program', 
      render: (row) => {
        const prog = programs?.find((p) => p.id === row.program_id);
        return <span className="text-slate-800 font-medium">{prog ? prog.program_name : `Prog #${row.program_id}`}</span>;
      },
    },
    { 
      header: 'Semester', 
      render: (row) => {
        const sem = semesters?.find((s) => s.id === row.semester_id);
        return (
          <span className="font-tabular text-slate-700">
            {sem ? `${sem.term} Sem ${sem.semester_number}` : `Sem #${row.semester_id}`}
          </span>
        );
      },
    },
    {
      header: 'Section',
      accessor: 'section_name',
      render: (row) => <span className="font-bold text-primary-900">Section {row.section_name}</span>,
    },
    {
      header: 'Capacity',
      accessor: 'student_count',
      render: (row) => (
        <span className="font-tabular font-semibold text-slate-700">
          {row.student_count} Students
        </span>
      ),
    },
  ];

  const handleEdit = (sec: SectionResponse) => {
    setSelectedSection(sec);
    setDepartmentId(sec.department_id);
    setProgramId(sec.program_id);
    setSemesterId(sec.semester_id);
    setSectionName(sec.section_name);
    setStudentCount(sec.student_count);
    setFormError(null);
    setIsFormOpen(true);
  };

  const handleDeleteClick = (sec: SectionResponse) => {
    setSelectedSection(sec);
    setIsConfirmOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedSection(null);
    setDepartmentId('');
    setProgramId('');
    setSemesterId('');
    setSectionName('');
    setStudentCount('');
    setFormError(null);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (
      departmentId === '' ||
      programId === '' ||
      semesterId === '' ||
      !sectionName.trim() ||
      studentCount === ''
    ) {
      setFormError('All section fields are required.');
      return;
    }

    const payload = {
      department_id: Number(departmentId),
      program_id: Number(programId),
      semester_id: Number(semesterId),
      section_name: sectionName.trim(),
      student_count: Number(studentCount),
    };

    if (selectedSection) {
      updateMutation.mutate({ id: selectedSection.id, sec: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Classroom Sections"
        subtitle="Manage student class sections, semester cohort assignments, and lecture hall capacity bounds."
        icon={<BookOpen size={20} />}
        actions={
          <button
            onClick={() => setIsFormOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-xs font-semibold uppercase tracking-wider shadow-xs focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2"
          >
            <Plus size={15} /> Add Section
          </button>
        }
      />

      <DataTable
        title="Class Section Directory"
        subtitle="Active cohort sections by department & program"
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
        searchPlaceholder="Filter sections…"
        emptyMessage="No sections found matching your search."
      />

      <FormModal
        isOpen={isFormOpen}
        title={selectedSection ? 'Edit Classroom Section' : 'Create Classroom Section'}
        subtitle="Assign section to program, semester term, and establish enrollment capacity"
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-rose-50 text-rose-800 text-xs rounded-lg border border-rose-200 font-medium">
              {formError}
            </div>
          )}
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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

            <div>
              <label className="academic-label">Program</label>
              <select
                value={programId}
                onChange={(e) => setProgramId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="">Select degree program…</option>
                {programs
                  ?.filter((p) => (departmentId ? p.department_id === Number(departmentId) : true))
                  .map((p) => (
                    <option key={p.id} value={p.id}>{p.program_name} ({p.degree})</option>
                  ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="academic-label">Semester</label>
              <select
                value={semesterId}
                onChange={(e) => setSemesterId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="">Select term…</option>
                {semesters?.map((s) => (
                  <option key={s.id} value={s.id}>{s.term} Sem {s.semester_number}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="academic-label">Section Identifier</label>
              <input
                type="text"
                value={sectionName}
                onChange={(e) => setSectionName(e.target.value)}
                className="academic-input font-bold"
                placeholder="e.g. A, B, C, Sec-1"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>

            <div>
              <label className="academic-label">Student Capacity</label>
              <input
                type="number"
                min="1"
                value={studentCount}
                onChange={(e) => setStudentCount(e.target.value === '' ? '' : Number(e.target.value))}
                className="academic-input font-tabular"
                placeholder="e.g. 60"
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
              {createMutation.isPending || updateMutation.isPending ? 'Saving…' : 'Save Section'}
            </button>
          </div>
        </form>
      </FormModal>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Classroom Section"
        message={`Are you sure you want to delete Section ${selectedSection?.section_name}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedSection && deleteMutation.mutate(selectedSection.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
