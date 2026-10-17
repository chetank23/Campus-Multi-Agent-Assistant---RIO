import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { X, Loader2, Save, Calendar, AlertCircle } from 'lucide-react';
import type { TimetableEntryResponse, TimetableEntryUpdate } from '@/api/timetable';
import { updateTimetableEntry } from '@/api/timetable';
import type { TimeSlotResponse } from '@/api/timeSlots';
import type { FacultyResponse } from '@/api/faculty';
import type { RoomResponse } from '@/api/rooms';

interface EditEntryModalProps {
  entry: TimetableEntryResponse;
  timeSlots: TimeSlotResponse[];
  facultyList: FacultyResponse[];
  rooms: RoomResponse[];
  onClose: () => void;
  onSuccess: () => void;
}

export const EditEntryModal: React.FC<EditEntryModalProps> = ({
  entry,
  timeSlots,
  facultyList,
  rooms,
  onClose,
  onSuccess,
}) => {
  const [roomId, setRoomId] = useState<number | ''>(entry.room_id || '');
  const [slotId, setSlotId] = useState<number | ''>(entry.slot_id || '');
  const [facultyId, setFacultyId] = useState<number | ''>(entry.faculty_id || '');

  const [errorStatus, setErrorStatus] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string>('');

  const updateMutation = useMutation({
    mutationFn: (updates: TimetableEntryUpdate) => updateTimetableEntry(entry.id, updates),
    onSuccess: () => {
      onSuccess();
    },
    onError: (err: unknown) => {
      if (isAxiosError(err) && err.response) {
        setErrorStatus('UPDATE_ERROR');
        setErrorMessage(err.response.data?.detail || 'Failed to update entry.');
      } else {
        setErrorStatus('ERROR');
        setErrorMessage('An unexpected error occurred while updating the entry.');
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateMutation.mutate({
      room_id: roomId ? Number(roomId) : null,
      slot_id: slotId ? Number(slotId) : null,
      faculty_id: facultyId ? Number(facultyId) : null,
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-slate-200/80 overflow-hidden animate-in fade-in-0 zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50/50">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-primary-50 text-primary-700">
              <Calendar size={18} />
            </div>
            <div>
              <h3 id="modal-title" className="text-base font-semibold text-slate-900">
                Edit Timetable Entry
              </h3>
              <p className="text-xs text-slate-500">Slot ID #{entry.id} • Manual override</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-3 bg-amber-50/70 border-b border-amber-200/60 text-xs text-amber-800">
          Modifying an entry will flag the timetable status as <strong>REVIEWED</strong>, requiring subsequent re-validation.
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit}>
          <div className="px-6 py-5 space-y-4">
            <div>
              <label className="academic-label">Room Allocation</label>
              <select
                value={roomId}
                onChange={(e) => setRoomId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={updateMutation.isPending}
              >
                <option value="">Unassigned Space</option>
                {rooms.map((r) => (
                  <option key={r.id} value={r.id}>
                    Room {r.room_number} (Capacity: {r.capacity} • {r.room_type})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="academic-label">Time Slot</label>
              <select
                value={slotId}
                onChange={(e) => setSlotId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={updateMutation.isPending}
              >
                <option value="">Unassigned Slot</option>
                {timeSlots.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.day} • {s.start_time.substring(0, 5)} - {s.end_time.substring(0, 5)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="academic-label">Faculty Member</label>
              <select
                value={facultyId}
                onChange={(e) => setFacultyId(e.target.value ? Number(e.target.value) : '')}
                className="academic-input"
                disabled={updateMutation.isPending}
              >
                <option value="">Unassigned Faculty</option>
                {facultyList.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name || `Faculty Member #${f.id}`} (User ID: {f.user_id})
                  </option>
                ))}
              </select>
            </div>

            {errorStatus && (
              <div className="flex items-start gap-2 text-xs text-rose-800 bg-rose-50 border border-rose-200 rounded-lg p-3">
                <AlertCircle size={16} className="text-rose-600 shrink-0 mt-0.5" />
                <span>{errorMessage}</span>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-200 bg-slate-50/50">
            <button
              type="button"
              onClick={onClose}
              disabled={updateMutation.isPending}
              className="academic-btn-secondary text-xs"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={updateMutation.isPending}
              className="academic-btn-primary text-xs inline-flex items-center gap-2"
            >
              {updateMutation.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Saving Changes…</span>
                </>
              ) : (
                <>
                  <Save size={14} />
                  <span>Save Changes</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
