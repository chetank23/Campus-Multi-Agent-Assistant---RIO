import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column } from '@/components/common/DataTable';
import { FormModal } from '@/components/common/FormModal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { batchesApi, type BatchResponse, type BatchUpdate } from '@/api/batches';
import { sectionsApi } from '@/api/sections';

export function BatchesPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedBatch, setSelectedBatch] = useState<BatchResponse | null>(null);
  
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
      alert(getErrorMsg(err, 'Failed to delete batch. It might be in use.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<BatchResponse>[] = [
    { header: 'ID', accessor: 'id' },
    { 
      header: 'Section', 
      render: (row) => sections?.find(s => s.id === row.section_id)?.section_name || `ID: ${row.section_id}` 
    },
    { header: 'Batch Name', accessor: 'batch_name' },
    { header: 'Student Count', accessor: 'student_count' },
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
      setFormError('All fields are required.');
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
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Batches</h2>
          <p className="text-sm text-gray-500 mt-1">Manage student batches.</p>
        </div>
        <button
          onClick={() => setIsFormOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          <Plus size={16} /> Add Batch
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
        title={selectedBatch ? 'Edit Batch' : 'Add Batch'}
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-red-50 text-red-700 text-sm rounded-lg border border-red-200">
              {formError}
            </div>
          )}
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Section</label>
            <select
              value={sectionId}
              onChange={(e) => setSectionId(e.target.value ? Number(e.target.value) : '')}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              <option value="">Select Section</option>
              {sections?.map(s => (
                <option key={s.id} value={s.id}>{s.section_name}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Batch Name</label>
              <input
                type="text"
                value={batchName}
                onChange={(e) => setBatchName(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. B1"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Student Count</label>
              <input
                type="number"
                min="1"
                value={studentCount}
                onChange={(e) => setStudentCount(e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. 30"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
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
        title="Delete Batch"
        message={`Are you sure you want to delete ${selectedBatch?.batch_name}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedBatch && deleteMutation.mutate(selectedBatch.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
