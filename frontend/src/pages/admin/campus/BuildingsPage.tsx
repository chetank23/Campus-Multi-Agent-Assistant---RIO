import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Building2 } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column, FormModal, ConfirmDialog, PageHeader } from '@/components/common';
import { buildingsApi, type BuildingResponse, type BuildingUpdate } from '@/api/buildings';

export function BuildingsPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedBuilding, setSelectedBuilding] = useState<BuildingResponse | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Form State
  const [buildingName, setBuildingName] = useState('');
  const [floors, setFloors] = useState<number | ''>('');
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['buildings'],
    queryFn: buildingsApi.getAll,
  });

  const filteredData = useMemo(() => {
    if (!data) return [];
    if (!searchTerm.trim()) return data;
    const term = searchTerm.toLowerCase();
    return data.filter(
      (bldg) =>
        bldg.building_name.toLowerCase().includes(term) ||
        String(bldg.id).includes(term) ||
        String(bldg.floors).includes(term)
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
      alert(getErrorMsg(err, 'Failed to delete building. It might contain active rooms.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<BuildingResponse>[] = [
    {
      header: 'ID',
      accessor: 'id',
      render: (row) => <span className="font-tabular text-slate-500 font-medium">#{row.id}</span>,
    },
    {
      header: 'Building Name',
      accessor: 'building_name',
      render: (row) => (
        <div className="flex items-center gap-2">
          <Building2 size={16} className="text-slate-400" />
          <span className="font-semibold text-slate-900">{row.building_name}</span>
        </div>
      ),
    },
    {
      header: 'Total Floors',
      accessor: 'floors',
      render: (row) => (
        <span className="font-tabular text-slate-700">
          {row.floors} {row.floors === 1 ? 'Floor' : 'Floors'}
        </span>
      ),
    },
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
      setFormError('Building title and floor count are required.');
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
      <PageHeader
        title="Campus Buildings"
        subtitle="Manage physical infrastructure, academic blocks, lecture complexes, and floor configurations."
        icon={<Building2 size={20} />}
        actions={
          <button
            onClick={() => setIsFormOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-xs font-semibold uppercase tracking-wider shadow-xs focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2"
          >
            <Plus size={15} /> Add Building
          </button>
        }
      />

      <DataTable
        title="Physical Infrastructure Registry"
        subtitle="Campus blocks & structures"
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
        searchPlaceholder="Filter buildings…"
        emptyMessage="No buildings found matching your search."
      />

      <FormModal
        isOpen={isFormOpen}
        title={selectedBuilding ? 'Edit Campus Building' : 'Register Campus Building'}
        subtitle="Specify building designation and vertical floor limits"
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-rose-50 text-rose-800 text-xs rounded-lg border border-rose-200 font-medium">
              {formError}
            </div>
          )}
          <div>
            <label className="academic-label">Building Name</label>
            <input
              type="text"
              value={buildingName}
              onChange={(e) => setBuildingName(e.target.value)}
              className="academic-input"
              placeholder="e.g. Sir M. Visvesvaraya Block"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
          </div>
          <div>
            <label className="academic-label">Number of Floors</label>
            <input
              type="number"
              min="1"
              max="50"
              value={floors}
              onChange={(e) => setFloors(e.target.value === '' ? '' : Number(e.target.value))}
              className="academic-input font-tabular"
              placeholder="e.g. 5"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
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
              {createMutation.isPending || updateMutation.isPending ? 'Saving…' : 'Save Building'}
            </button>
          </div>
        </form>
      </FormModal>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Campus Building"
        message={`Are you sure you want to delete ${selectedBuilding?.building_name}? All linked rooms and timetable entries must be relocated first.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedBuilding && deleteMutation.mutate(selectedBuilding.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
