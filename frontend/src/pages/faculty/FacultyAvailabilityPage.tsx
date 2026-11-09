import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Clock, Plus, Trash2, Info, Star } from 'lucide-react';
import { isAxiosError } from 'axios';
import {
  DataTable,
  type Column,
  FormModal,
  ConfirmDialog,
  StatusBadge,
  RefreshButton,
} from '@/components/common';
import { useToast } from '@/context/useToast';
import {
  facultyAvailabilityApi,
  type FacultyAvailabilityItem,
} from '@/api/facultyAvailability';
import { timeSlotsApi } from '@/api/academicCalendar';
import { formatTime12h } from '@/utils/timeFormatter';
import { useAuth } from '@/auth/useAuth';

export function FacultyAvailabilityPage() {
  const queryClient = useQueryClient();
  const { user: me } = useAuth();
  const { toast } = useToast();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [deleteTargetId, setDeleteTargetId] = useState<number | null>(null);

  // Form state
  const [slotId, setSlotId] = useState<number | ''>('');
  const [availability, setAvailability] = useState<'AVAILABLE' | 'UNAVAILABLE' | 'PREFERRED'>('PREFERRED');
  const [preference, setPreference] = useState<number>(5);
  const [formError, setFormError] = useState<string | null>(null);

  // Queries
  const {
    data: availabilityList,
    isLoading: isAvailLoading,
    isError: isAvailError,
    error: availError,
    refetch,
  } = useQuery({
    queryKey: ['my-availability'],
    queryFn: facultyAvailabilityApi.getAll,
  });

  const { data: timeSlots } = useQuery({
    queryKey: ['timeSlots'],
    queryFn: timeSlotsApi.getAll,
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
    mutationFn: facultyAvailabilityApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-availability'] });
      toast.success('Teaching availability preference saved successfully!');
      setIsModalOpen(false);
      resetForm();
    },
    onError: (err) => {
      const msg = getErrorMsg(err, 'Failed to save availability preference.');
      setFormError(msg);
      toast.error(msg);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: facultyAvailabilityApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-availability'] });
      toast.success('Availability preference removed.');
      setIsDeleteOpen(false);
      setDeleteTargetId(null);
    },
    onError: (err) => {
      const msg = getErrorMsg(err, 'Failed to remove preference.');
      toast.error(msg);
    },
  });

  const resetForm = () => {
    setSlotId('');
    setAvailability('PREFERRED');
    setPreference(5);
    setFormError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!slotId) {
      setFormError('Please select a timetable time slot.');
      return;
    }
    createMutation.mutate({
      faculty_id: me?.id || 1,
      slot_id: Number(slotId),
      availability,
      preference: Number(preference),
    });
  };

  const columns: Column<FacultyAvailabilityItem>[] = [
    {
      header: 'Time Slot',
      accessor: 'slot_id',
      render: (row) => {
        const slot = timeSlots?.find((s) => s.id === row.slot_id);
        if (!slot) return <span className="text-slate-400 font-mono text-xs">Slot #{row.slot_id}</span>;
        return (
          <div>
            <div className="font-semibold text-slate-900">{slot.day}</div>
            <div className="text-xs text-slate-500 font-mono">
              {formatTime12h(slot.start_time)} – {formatTime12h(slot.end_time)} ({slot.slot_type})
            </div>
          </div>
        );
      },
    },
    {
      header: 'Availability Status',
      accessor: 'availability',
      render: (row) => {
        const variant =
          row.availability === 'AVAILABLE'
            ? 'success'
            : row.availability === 'UNAVAILABLE'
            ? 'danger'
            : 'neutral';
        return <StatusBadge status={row.availability} variant={variant} />;
      },
    },
    {
      header: 'Preference Score',
      accessor: 'preference',
      render: (row) => (
        <div className="flex items-center gap-1 text-xs font-bold text-amber-600">
          <Star size={14} className="fill-amber-400 text-amber-400" />
          <span>Priority {row.preference}/5</span>
        </div>
      ),
    },
    {
      header: 'Actions',
      align: 'right',
      render: (row) => (
        <button
          onClick={(e) => {
            e.stopPropagation();
            setDeleteTargetId(row.id);
            setIsDeleteOpen(true);
          }}
          className="p-1 text-slate-400 hover:text-red-700 hover:bg-red-50 rounded-md transition-colors"
          title="Remove Preference"
        >
          <Trash2 size={16} />
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto pb-10">
      {/* Top Banner */}
      <div className="bg-[#142542] text-white p-6 rounded-2xl shadow-sm border border-[#1D3152] flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Clock size={20} className="text-[#38BDF8]" />
            <h1 className="text-xl font-black tracking-tight">Teaching Availability & Preferences</h1>
          </div>
          <p className="text-xs text-[#94A3B8] mt-1">
            Indicate your preferred time slots, restricted research windows, and teaching constraints.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <RefreshButton
            entityName="Availability"
            queryKeys={[['my-availability'], ['time-slots-active']]}
            variant="outline"
            label="Refresh"
            className="bg-white/10 text-white border-white/20 hover:bg-white/20 hover:text-white"
          />
          <button
            onClick={() => {
              resetForm();
              setIsModalOpen(true);
            }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-[#2B568F] hover:bg-[#1D3B5C] text-white text-xs font-bold rounded-xl shadow-xs transition-colors"
          >
            <Plus size={16} />
            Set Slot Preference
          </button>
        </div>
      </div>

      {/* Info Callout */}
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-xl text-blue-900 flex items-start gap-3">
        <Info size={20} className="text-blue-600 shrink-0 mt-0.5" />
        <div className="text-xs space-y-1">
          <p className="font-bold">Automated Scheduling Engine Integration</p>
          <p className="text-blue-700 leading-relaxed">
            The CP-SAT timetable optimizer prioritizes PREFERRED slots and guarantees hard constraint protection for
            UNAVAILABLE periods during timetable generation. Existing published sessions require an approved Change Request to alter.
          </p>
        </div>
      </div>

      {/* Availability Table */}
      <DataTable<FacultyAvailabilityItem>
        columns={columns}
        data={availabilityList || []}
        isLoading={isAvailLoading}
        isError={isAvailError}
        error={availError as Error | null}
        onRefresh={refetch}
        keyExtractor={(row) => row.id}
        searchPlaceholder="Filter availability records…"
        emptyMessage="No Availability Records Set. Click 'Set Slot Preference' to declare your preferred or restricted teaching periods."
      />

      {/* Set Availability Modal */}
      <FormModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Set Slot Availability Preference"
      >
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {formError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 font-medium">
              {formError}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Timetable Slot *
              </label>
              <select
                value={slotId}
                onChange={(e) => setSlotId(Number(e.target.value))}
                required
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
              >
                <option value="">Select Time Slot</option>
                {timeSlots?.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.day} · {formatTime12h(s.start_time)} – {formatTime12h(s.end_time)} ({s.slot_type})
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Preference Type *
                </label>
                <select
                  value={availability}
                  onChange={(e) =>
                    setAvailability(e.target.value as 'AVAILABLE' | 'UNAVAILABLE' | 'PREFERRED')
                  }
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                >
                  <option value="PREFERRED">PREFERRED (High Priority)</option>
                  <option value="AVAILABLE">AVAILABLE (Standard)</option>
                  <option value="UNAVAILABLE">UNAVAILABLE (Blocked)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Priority Rank (1-5) *
                </label>
                <input
                  type="number"
                  min={1}
                  max={5}
                  required
                  value={preference}
                  onChange={(e) => setPreference(Number(e.target.value))}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
                />
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
            <button
              type="button"
              onClick={() => setIsModalOpen(false)}
              className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="px-4 py-2 bg-[#2B568F] hover:bg-[#1D3B5C] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
            >
              {createMutation.isPending ? 'Saving…' : 'Save Preference'}
            </button>
          </div>
        </form>
      </FormModal>

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={isDeleteOpen}
        onCancel={() => setIsDeleteOpen(false)}
        title="Remove Preference"
        message="Are you sure you want to remove this availability record? The scheduler will revert to standard availability for this slot."
        confirmLabel="Remove"
        isDestructive
        isProcessing={deleteMutation.isPending}
        onConfirm={() => {
          if (deleteTargetId) deleteMutation.mutate(deleteTargetId);
        }}
      />
    </div>
  );
}
