import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, DoorOpen } from 'lucide-react';
import { isAxiosError } from 'axios';
import { DataTable, type Column, FormModal, ConfirmDialog, PageHeader, StatusBadge } from '@/components/common';
import { roomsApi, type RoomResponse, type RoomUpdate } from '@/api/rooms';
import { buildingsApi } from '@/api/buildings';

export function RoomsPage() {
  const queryClient = useQueryClient();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [selectedRoom, setSelectedRoom] = useState<RoomResponse | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  
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

  const filteredData = useMemo(() => {
    if (!data) return [];
    if (!searchTerm.trim()) return data;
    const term = searchTerm.toLowerCase();
    return data.filter((rm) => {
      const b = buildings?.find((bldg) => bldg.id === rm.building_id);
      const bldgName = (b?.building_name || b?.name || rm.building_name || '').toLowerCase();
      return (
        (rm.room_number || '').toLowerCase().includes(term) ||
        (rm.room_type || '').toLowerCase().includes(term) ||
        bldgName.includes(term) ||
        String(rm.id).includes(term) ||
        (rm.capacity ? String(rm.capacity).includes(term) : false)
      );
    });
  }, [data, buildings, searchTerm]);

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
      alert(getErrorMsg(err, 'Failed to delete room. It might be referenced by timetable schedules.'));
      setIsConfirmOpen(false);
    },
  });

  const columns: Column<RoomResponse>[] = [
    {
      header: 'ID',
      accessor: 'id',
      render: (row) => <span className="font-tabular text-slate-500 font-medium">#{row.id}</span>,
    },
    { 
      header: 'Building', 
      render: (row) => {
        const b = buildings?.find((bldg) => bldg.id === row.building_id);
        const bName = b?.building_name || b?.name || row.building_name || (row.building_id ? `Building #${row.building_id}` : 'Unassigned');
        return <span className="font-semibold text-slate-900">{bName}</span>;
      },
    },
    {
      header: 'Room Number',
      accessor: 'room_number',
      render: (row) => (
        <div className="flex items-center gap-1.5 font-mono text-xs font-bold text-slate-800 bg-slate-100 px-2 py-0.5 rounded border border-slate-200 w-fit">
          <DoorOpen size={13} className="text-slate-500" />
          <span>{row.room_number}</span>
        </div>
      ),
    },
    {
      header: 'Facility Type',
      accessor: 'room_type',
      render: (row) => <StatusBadge status={row.room_type || 'CLASSROOM'} />,
    },
    {
      header: 'Seating Capacity',
      accessor: 'capacity',
      render: (row) => (
        <span className="font-tabular font-semibold text-slate-800">
          {row.capacity ? `${row.capacity} Seats` : <span className="text-slate-400 font-normal italic">Not specified</span>}
        </span>
      ),
    },
    { 
      header: 'Status', 
      render: (row) => {
        const isActive = row.is_active || row.status === 'ACTIVE';
        return (
          <StatusBadge
            status={isActive ? 'ACTIVE' : 'INACTIVE'}
            label={isActive ? 'Available' : 'Maintenance'}
          />
        );
      },
    },
  ];

  const handleEdit = (rm: RoomResponse) => {
    setSelectedRoom(rm);
    setBuildingId(rm.building_id);
    setRoomNumber(rm.room_number);
    setRoomType(rm.room_type);
    setCapacity(rm.capacity ?? '');
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
    
    if (buildingId === '' || !roomNumber.trim() || capacity === '') {
      setFormError('Building, room number, and seating capacity are required.');
      return;
    }

    const payload = {
      building_id: Number(buildingId),
      room_number: roomNumber.trim(),
      room_type: roomType,
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
      <PageHeader
        title="Rooms & Lecture Halls"
        subtitle="Manage instructional spaces, auditoriums, department laboratories, and seating capacities."
        icon={<DoorOpen size={20} />}
        actions={
          <button
            onClick={() => setIsFormOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-xs font-semibold uppercase tracking-wider shadow-xs focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2"
          >
            <Plus size={15} /> Add Room
          </button>
        }
      />

      <DataTable
        title="Classroom & Lab Registry"
        subtitle="Physical space inventory"
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
        searchPlaceholder="Filter rooms by number, building, type…"
        emptyMessage="No rooms found matching your search."
      />

      <FormModal
        isOpen={isFormOpen}
        title={selectedRoom ? 'Edit Classroom / Lab' : 'Register New Space'}
        subtitle="Assign space to campus building, define type, and set seating capacity"
        onClose={closeForm}
      >
        <form onSubmit={handleFormSubmit} className="space-y-4">
          {formError && (
            <div className="p-3 bg-rose-50 text-rose-800 text-xs rounded-lg border border-rose-200 font-medium">
              {formError}
            </div>
          )}
          <div>
            <label className="academic-label">Building Location</label>
            <select
              value={buildingId}
              onChange={(e) => setBuildingId(e.target.value ? Number(e.target.value) : '')}
              className="academic-input"
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              <option value="">Select building block…</option>
              {buildings?.map((b) => (
                <option key={b.id} value={b.id}>{b.building_name}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="academic-label">Room Number</label>
              <input
                type="text"
                value={roomNumber}
                onChange={(e) => setRoomNumber(e.target.value)}
                className="academic-input font-mono"
                placeholder="e.g. 101, LH-2, Lab-3"
                disabled={createMutation.isPending || updateMutation.isPending}
              />
            </div>
            <div>
              <label className="academic-label">Space Type</label>
              <select
                value={roomType}
                onChange={(e) => setRoomType(e.target.value)}
                className="academic-input"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                <option value="LECTURE">LECTURE</option>
                <option value="LAB">LAB</option>
                <option value="SEMINAR">SEMINAR</option>
                <option value="AUDITORIUM">AUDITORIUM</option>
              </select>
            </div>
          </div>
          <div>
            <label className="academic-label">Seating Capacity</label>
            <input
              type="number"
              min="1"
              max="1000"
              value={capacity}
              onChange={(e) => setCapacity(e.target.value === '' ? '' : Number(e.target.value))}
              className="academic-input font-tabular"
              placeholder="e.g. 60"
              disabled={createMutation.isPending || updateMutation.isPending}
            />
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
              <span className="text-xs font-semibold text-slate-700">Space Available for Timetable Scheduling</span>
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
              {createMutation.isPending || updateMutation.isPending ? 'Saving…' : 'Save Space'}
            </button>
          </div>
        </form>
      </FormModal>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Space"
        message={`Are you sure you want to delete Room ${selectedRoom?.room_number}? This will unlink any timetable allocations for this hall.`}
        isProcessing={deleteMutation.isPending}
        onConfirm={() => selectedRoom && deleteMutation.mutate(selectedRoom.id)}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </div>
  );
}
