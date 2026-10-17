import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, School } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column, FormModal, ConfirmDialog, PageHeader } from '@/components/common';
import { studentsApi, type StudentResponse, type StudentUpdate } from '@/api/students';
import { departmentsApi } from '@/api/departments';
import { programsApi } from '@/api/programs';
import { batchesApi } from '@/api/batches';
import { sectionsApi } from '@/api/sections';
import { semestersApi } from '@/api/semesters';

export function StudentsPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState<StudentResponse | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Form State
  const [userId, setUserId] = useState<number | ''>('');
  const [studentIdStr, setStudentIdStr] = useState('');
  const [departmentId, setDepartmentId] = useState<number | ''>('');
  const [programId, setProgramId] = useState<number | ''>('');
  const [semesterId, setSemesterId] = useState<number | ''>('');
  const [sectionId, setSectionId] = useState<number | ''>('');
  const [batchId, setBatchId] = useState<number | ''>('');
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['students'],
    queryFn: studentsApi.getAll,
  });

  const { data: departments } = useQuery({ queryKey: ['departments'], queryFn: departmentsApi.getAll });
  const { data: programs } = useQuery({ queryKey: ['programs'], queryFn: programsApi.getAll });
  const { data: batches } = useQuery({ queryKey: ['batches'], queryFn: batchesApi.getAll });
  const { data: sections } = useQuery({ queryKey: ['sections'], queryFn: sectionsApi.getAll });
  const { data: semesters } = useQuery({ queryKey: ['semesters'], queryFn: semestersApi.getAll });

  const filteredData = useMemo(() => {
    if (!data) return [];
    if (!searchTerm.trim()) return data;
    const term = searchTerm.toLowerCase();
    return data.filter((std) => {
      const deptCode = departments?.find((d) => d.id === std.department_id)?.department_code?.toLowerCase() || '';
      const progName = programs?.find((p) => p.id === std.program_id)?.program_name?.toLowerCase() || '';
      const secName = sections?.find((s) => s.id === std.section_id)?.section_name?.toLowerCase() || '';
      const batchName = batches?.find((b) => b.id === std.batch_id)?.batch_name?.toLowerCase() || '';
      return (
        std.student_id.toLowerCase().includes(term) ||
        deptCode.includes(term) ||
        progName.includes(term) ||
        secName.includes(term) ||
        batchName.includes(term) ||
        String(std.id).includes(term) ||
        String(std.user_id).includes(term)
      );
    });
  }, [data, departments, programs, sections, batches, searchTerm]);

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
    mutationFn: studentsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['students'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create student.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, std }: { id: number; std: StudentUpdate }) => studentsApi.update(id, std),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['students'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update student.'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: studentsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['students'] });
      setIsConfirmOpen(false);
      setSelectedStudent(null);
    },
    onError: (err: unknown) => {
      alert(getErrorMsg(err, 'Failed to delete student.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<StudentResponse>[] = [
    {
      header: 'ID',
      accessor: 'id',
      render: (row) => <span className="font-tabular text-slate-500 font-medium">#{row.id}</span>,
    },
    {
      header: 'SRN / USN',
      accessor: 'student_id',
      render: (row) => (
        <span className="font-mono text-xs font-bold text-primary-900 bg-primary-50 px-2 py-0.5 rounded border border-primary-200">
          {row.student_id}
        </span>
      ),
    },
    {
      header: 'User Account',
      accessor: 'user_id',
      render: (row) => <span className="text-xs text-slate-500">User #{row.user_id}</span>,
    },
    { 
      header: 'Department', 
      render: (row) => {
        const d = departments?.find((dept) => dept.id === row.department_id);
        return <span className="text-slate-700 font-medium">{d ? d.department_code : `#${row.department_id}`}</span>;
      },
    },
    { 
      header: 'Program', 
      render: (row) => {
        const p = programs?.find((prog) => prog.id === row.program_id);
        return <span className="text-slate-900 font-semibold">{p ? p.program_name : `#${row.program_id}`}</span>;
      },
    },
    { 
      header: 'Semester', 
      render: (row) => {
        const s = semesters?.find((sem) => sem.id === row.semester_id);
        return <span className="font-tabular text-slate-700">{s ? `Sem ${s.semester_number}` : `#${row.semester_id}`}</span>;
      },
    },
    { 
      header: 'Section', 
      render: (row) => {
        const sec = sections?.find((section) => section.id === row.section_id);
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-slate-100 text-slate-800 border border-slate-200">
            {sec ? `Sec ${sec.section_name}` : `#${row.section_id}`}
          </span>
        );
      },
    },
    { 
      header: 'Batch', 
      render: (row) => {
        const b = batches?.find((batch) => batch.id === row.batch_id);
        return <span className="font-mono text-xs text-slate-600">{b ? b.batch_name : `#${row.batch_id}`}</span>;
      },
    },
  ];

  const handleEdit = (std: StudentResponse) => {
    setSelectedStudent(std);
    setUserId(std.user_id);
    setStudentIdStr(std.student_id);
    setDepartmentId(std.department_id);
    setProgramId(std.program_id);
    setSemesterId(std.semester_id);
    setSectionId(std.section_id);
    setBatchId(std.batch_id);
    setFormError(null);
    setIsFormOpen(true);
  };

  const handleDeleteClick = (std: StudentResponse) => {
    setSelectedStudent(std);
    setIsConfirmOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedStudent(null);
    setUserId('');
    setStudentIdStr('');
    setDepartmentId('');
    setProgramId('');
    setSemesterId('');
    setSectionId('');
    setBatchId('');
    setFormError(null);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (
      userId === '' ||
      !studentIdStr.trim() ||
      departmentId === '' ||
      programId === '' ||
      semesterId === '' ||
      sectionId === '' ||
      batchId === ''
    ) {
      setFormError('All student enrollment fields are required.');
      return;
    }

    const payload = {
      user_id: Number(userId),
      student_id: studentIdStr.trim(),
      department_id: Number(departmentId),
      program_id: Number(programId),
      semester_id: Number(semesterId),
      section_id: Number(sectionId),
      batch_id: Number(batchId),
    };

    if (selectedStudent) {
      updateMutation.mutate({ id: selectedStudent.id, std: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Student Roster"
        subtitle="Manage registered students, institutional SRN/USN identifiers, program enrollments, and section allocations."
        icon={<School size={20} />}
        actions={
          <button
            onClick={() => setIsFormOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-xs font-semibold uppercase tracking-wider shadow-xs focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2"
          >
            <Plus size={15} /> Enroll Student
          </button>
        }
      />

      <DataTable
        title="Student Enrollment Registry"
        subtitle="Active cohort rosters"
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
        searchPlaceholder="Filter by SRN, program, section…"
        emptyMessage="No student records found matching your search."
      />

      <FormModal
        isOpen={isFormOpen}
        title={selectedStudent ? 'Edit Student Record' : 'Enroll Student Record'}
        subtitle="Configure student USN, academic department, semester, section, and laboratory batch"
        maxWidth="xl"
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
                placeholder="e.g. 12"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="academic-label">Student ID (SRN / USN)</label>
              <input
                type="text"
                value={studentIdStr}
                onChange={(e) => setStudentIdStr(e.target.value)}
                className="academic-input font-mono uppercase"
                placeholder="e.g. R21CS101"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
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
                <option value="">Select program…</option>
                {programs
                  ?.filter((p) => (departmentId ? p.department_id === Number(departmentId) : true))
                  .map((p) => (
                    <option key={p.id} value={p.id}>{p.program_name} ({p.degree})</option>
                  ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="academic-label">Semester</label>
              <select
                value={semesterId}
                onChange={(e) => setSemesterId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="">Select semester…</option>
                {semesters?.map((s) => (
                  <option key={s.id} value={s.id}>{s.term} Sem {s.semester_number}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="academic-label">Section</label>
              <select
                value={sectionId}
                onChange={(e) => setSectionId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="">Select section…</option>
                {sections?.map((sec) => (
                  <option key={sec.id} value={sec.id}>Section {sec.section_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="academic-label">Batch</label>
              <select
                value={batchId}
                onChange={(e) => setBatchId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="">Select batch…</option>
                {batches?.map((b) => (
                  <option key={b.id} value={b.id}>{b.batch_name}</option>
                ))}
              </select>
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
              {createMutation.isPending || updateMutation.isPending ? 'Saving…' : 'Save Student'}
            </button>
          </div>
        </form>
      </FormModal>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Student Record"
        message={`Are you sure you want to delete student ${selectedStudent?.student_id}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedStudent && deleteMutation.mutate(selectedStudent.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
