import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column } from '@/components/common/DataTable';
import { FormModal } from '@/components/common/FormModal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { roomsApi, type RoomResponse, type RoomUpdate } from '@/api/rooms';
import { buildingsApi } from '@/api/buildings';

export function RoomsPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedRoom, setSelectedRoom] = useState<RoomResponse | null>(null);
  
  // Form State
  const [buildingId, setBuildingId] = useState<number | ''>('');
  const [roomNumber, setRoomNumber] = useState('');
  const [roomType, setRoomType] = useState('LECTURE');
  const [capacity, setCapacity] = useState<number | ''>('');
  const [isActive, setIsActive] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['rooms'],
    queryFn: roomsApi.getAll,
  });

  const { data: buildings } = useQuery({ queryKey: ['buildings'], queryFn: buildingsApi.getAll });

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
    mutationFn: roomsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to create room.'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, rm }: { id: number; rm: RoomUpdate }) => roomsApi.update(id, rm),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
      closeForm();
    },
    onError: (err: unknown) => {
      setFormError(getErrorMsg(err, 'Failed to update room.'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: roomsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rooms'] });
      setIsConfirmOpen(false);
      setSelectedRoom(null);
    },
    onError: (err: unknown) => {
      alert(getErrorMsg(err, 'Failed to delete room.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<RoomResponse>[] = [
    { header: 'ID', accessor: 'id' },
    { 
      header: 'Building', 
      render: (row) => buildings?.find(b => b.id === row.building_id)?.building_name || `ID: ${row.building_id}` 
    },
    { header: 'Room No.', accessor: 'room_number' },
    { header: 'Type', accessor: 'room_type' },
    { header: 'Capacity', accessor: 'capacity' },
    { 
      header: 'Status', 
      render: (row) => (
        <span className={`px-2 py-1 rounded-full text-xs font-semibold ${row.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}`}>
          {row.is_active ? 'Active' : 'Inactive'}
        </span>
      ) 
    },
  ];

  const handleEdit = (rm: RoomResponse) => {
    setSelectedRoom(rm);
    setBuildingId(rm.building_id);
    setRoomNumber(rm.room_number);
    setRoomType(rm.room_type);
    setCapacity(rm.capacity);
    setIsActive(rm.is_active);
    setFormError(null);
    setIsFormOpen(true);
  };

  const handleDeleteClick = (rm: RoomResponse) => {
    setSelectedRoom(rm);
    setIsConfirmOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
    setSelectedRoom(null);
    setBuildingId('');
    setRoomNumber('');
    setRoomType('LECTURE');
    setCapacity('');
    setIsActive(true);
    setFormError(null);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (buildingId === '' || !roomNumber.trim() || !roomType.trim() || capacity === '') {
      setFormError('All fields are required.');
      return;
    }

    const payload = {
      building_id: Number(buildingId),
      room_number: roomNumber.trim(),
      room_type: roomType.trim(),
      capacity: Number(capacity),
      is_active: isActive,
    };

    if (selectedRoom) {
      updateMutation.mutate({ id: selectedRoom.id, rm: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Rooms</h2>
          <p className="text-sm text-gray-500 mt-1">Manage campus rooms and capacities.</p>
        </div>
        <button
          onClick={() => setIsFormOpen(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          <Plus size={16} /> Add Room
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
        title={selectedRoom ? 'Edit Room' : 'Add Room'}
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-red-50 text-red-700 text-sm rounded-lg border border-red-200">
              {formError}
            </div>
          )}
          
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Building</label>
              <select
                value={buildingId}
                onChange={(e) => setBuildingId(e.target.value ? Number(e.target.value) : '')}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="">Select Building</option>
                {buildings?.map(b => (
                  <option key={b.id} value={b.id}>{b.building_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Room No.</label>
              <input
                type="text"
                value={roomNumber}
                onChange={(e) => setRoomNumber(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. 101"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
              <select
                value={roomType}
                onChange={(e) => setRoomType(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="LECTURE">LECTURE</option>
                <option value="LAB">LAB</option>
                <option value="SEMINAR">SEMINAR</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Capacity</label>
              <input
                type="number"
                min="1"
                value={capacity}
                onChange={(e) => setCapacity(e.target.value === '' ? '' : Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g. 60"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
          </div>

          <div className="flex items-center gap-2 mt-2">
            <input
              type="checkbox"
              id="isActiveRoom"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
            <label htmlFor="isActiveRoom" className="text-sm font-medium text-gray-700">
              Active
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
        title="Delete Room"
        message={`Are you sure you want to delete room ${selectedRoom?.room_number}? This action cannot be undone.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedRoom && deleteMutation.mutate(selectedRoom.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
