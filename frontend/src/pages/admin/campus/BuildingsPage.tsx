import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column } from '@/components/common/DataTable';
import { FormModal } from '@/components/common/FormModal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { buildingsApi, type BuildingResponse, type BuildingUpdate } from '@/api/buildings';

export function BuildingsPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedBuilding, setSelectedBuilding] = useState<BuildingResponse | null>(null);
  
  // Form State
  const [buildingName, setBuildingName] = useState('');
  const [floors, setFloors] = useState<number | ''>('');
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['buildings'],
    queryFn: buildingsApi.getAll,
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
    mutationFn: buildingsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['buildings'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create building.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, bldg }: { id: number; bldg: BuildingUpdate }) => buildingsApi.update(id, bldg),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['buildings'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update building.'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: buildingsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['buildings'] });
      setIsConfirmOpen(false);
      setSelectedBuilding(null);
    },
    onError: (err: unknown) => {
      alert(getErrorMsg(err, 'Failed to delete building. It might be in use.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<BuildingResponse>[] = [
    { header: 'ID', accessor: 'id' },
    { header: 'Building Name', accessor: 'building_name' },
    { header: 'Floors', accessor: 'floors' },
  ];

  const handleEdit = (bldg: BuildingResponse) => {
    setSelectedBuilding(bldg);
    setBuildingName(bldg.building_name);
    setFloors(bldg.floors);
    setFormError(null);
    setIsFormOpen(true);
  };

  const handleDeleteClick = (bldg: BuildingResponse) => {
    setSelectedBuilding(bldg);
    setIsConfirmOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedBuilding(null);
    setBuildingName('');
    setFloors('');
    setFormError(null);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (!buildingName.trim() || floors === '') {
      setFormError('All fields are required.');
      return;
    }

    const payload = {
      building_name: buildingName.trim(),
      floors: Number(floors),
    };

    if (selectedBuilding) {
      updateMutation.mutate({ id: selectedBuilding.id, bldg: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Buildings</h2>
          <p className="text-sm text-gray-500 mt-1">Manage campus buildings.</p>
        </div>
        <button
          onClick={() => setIsFormOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          <Plus size={16} /> Add Building
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
        title={selectedBuilding ? 'Edit Building' : 'Add Building'}
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-red-50 text-red-700 text-sm rounded-lg border border-red-200">
              {formError}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Building Name</label>
            <input
              type="text"
              value={buildingName}
              onChange={(e) => setBuildingName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="e.g. Main Block"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Floors</label>
            <input
              type="number"
              min="1"
              value={floors}
              onChange={(e) => setFloors(e.target.value === '' ? '' : Number(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="e.g. 4"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
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
        title="Delete Building"
        message={`Are you sure you want to delete ${selectedBuilding?.building_name}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedBuilding && deleteMutation.mutate(selectedBuilding.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
