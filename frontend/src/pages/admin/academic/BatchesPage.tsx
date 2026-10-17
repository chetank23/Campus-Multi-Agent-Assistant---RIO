import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Users } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column, FormModal, ConfirmDialog, PageHeader } from '@/components/common';
import { batchesApi, type BatchResponse, type BatchUpdate } from '@/api/batches';
import { sectionsApi } from '@/api/sections';

export function BatchesPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedBatch, setSelectedBatch] = useState<BatchResponse | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Form State
  const [sectionId, setSectionId] = useState<number | ''>('');
  const [batchName, setBatchName] = useState('');
  const [studentCount, setStudentCount] = useState<number | ''>('');
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['batches'],
    queryFn: batchesApi.getAll,
  });

  const { data: sections } = useQuery({
    queryKey: ['sections'],
    queryFn: sectionsApi.getAll,
  });

  const filteredData = useMemo(() => {
    if (!data) return [];
    if (!searchTerm.trim()) return data;
    const term = searchTerm.toLowerCase();
    return data.filter((b) => {
      const secName = sections?.find((s) => s.id === b.section_id)?.section_name?.toLowerCase() || '';
      return (
        b.batch_name.toLowerCase().includes(term) ||
        secName.includes(term) ||
        String(b.id).includes(term) ||
        String(b.student_count).includes(term)
      );
    });
  }, [data, sections, searchTerm]);

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
    mutationFn: batchesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['batches'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create batch.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, batch }: { id: number; batch: BatchUpdate }) => batchesApi.update(id, batch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['batches'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update batch.'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: batchesApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['batches'] });
      setIsConfirmOpen(false);
      setSelectedBatch(null);
    },
    onError: (err: unknown) => {
      alert(getErrorMsg(err, 'Failed to delete batch. It might be referenced by enrolled students.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<BatchResponse>[] = [
    {
      header: 'ID',
      accessor: 'id',
      render: (row) => <span className="font-tabular text-slate-500 font-medium">#{row.id}</span>,
    },
    {
      header: 'Assigned Section',
      render: (row) => {
        const sec = sections?.find((s) => s.id === row.section_id);
        return <span className="font-semibold text-slate-900">{sec ? `Section ${sec.section_name}` : `Section #${row.section_id}`}</span>;
      },
    },
    {
      header: 'Batch Identifier',
      accessor: 'batch_name',
      render: (row) => (
        <span className="inline-flex items-center px-2 py-0.5 rounded font-mono text-xs font-bold bg-slate-100 text-slate-800 border border-slate-200">
          {row.batch_name}
        </span>
      ),
    },
    {
      header: 'Student Count',
      accessor: 'student_count',
      render: (row) => (
        <span className="font-tabular font-semibold text-slate-700">
          {row.student_count} Students
        </span>
      ),
    },
  ];

  const handleEdit = (batch: BatchResponse) => {
    setSelectedBatch(batch);
    setSectionId(batch.section_id);
    setBatchName(batch.batch_name);
    setStudentCount(batch.student_count);
    setFormError(null);
    setIsFormOpen(true);
  };

  const handleDeleteClick = (batch: BatchResponse) => {
    setSelectedBatch(batch);
    setIsConfirmOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedBatch(null);
    setSectionId('');
    setBatchName('');
    setStudentCount('');
    setFormError(null);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (sectionId === '' || !batchName.trim() || studentCount === '') {
      setFormError('All batch fields are required.');
      return;
    }

    const payload = {
      section_id: Number(sectionId),
      batch_name: batchName.trim(),
      student_count: Number(studentCount),
    };

    if (selectedBatch) {
      updateMutation.mutate({ id: selectedBatch.id, batch: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Student Batches"
        subtitle="Manage student lab subgroups, tutorial cohorts, and batch divisions within academic sections."
        icon={<Users size={20} />}
        actions={
          <button
            onClick={() => setIsFormOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-xs font-semibold uppercase tracking-wider shadow-xs focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2"
          >
            <Plus size={15} /> Add Batch
          </button>
        }
      />

      <DataTable
        title="Batch Subgroups"
        subtitle="Cohort divisions per section"
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
        searchPlaceholder="Filter batches…"
        emptyMessage="No batches found matching your search."
      />

      <FormModal
        isOpen={isFormOpen}
        title={selectedBatch ? 'Edit Student Batch' : 'Create Student Batch'}
        subtitle="Associate batch with classroom section and define expected student enrollment"
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-rose-50 text-rose-800 text-xs rounded-lg border border-rose-200 font-medium">
              {formError}
            </div>
          )}
          <div>
            <label className="academic-label">Parent Section</label>
            <select
              value={sectionId}
              onChange={(e) => setSectionId(e.target.value ? Number(e.target.value) : '')}
              className="academic-input"
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              <option value="">Select parent classroom section…</option>
              {sections?.map((s) => (
                <option key={s.id} value={s.id}>
                  Section {s.section_name} (Capacity: {s.student_count})
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="academic-label">Batch Name</label>
              <input
                type="text"
                value={batchName}
                onChange={(e) => setBatchName(e.target.value)}
                className="academic-input font-mono"
                placeholder="e.g. B1, B2, Batch-A"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="academic-label">Student Count</label>
              <input
                type="number"
                min="1"
                value={studentCount}
                onChange={(e) => setStudentCount(e.target.value === '' ? '' : Number(e.target.value))}
                className="academic-input font-tabular"
                placeholder="e.g. 30"
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
              {createMutation.isPending || updateMutation.isPending ? 'Saving…' : 'Save Batch'}
            </button>
          </div>
        </form>
      </FormModal>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Student Batch"
        message={`Are you sure you want to delete ${selectedBatch?.batch_name}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedBatch && deleteMutation.mutate(selectedBatch.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
