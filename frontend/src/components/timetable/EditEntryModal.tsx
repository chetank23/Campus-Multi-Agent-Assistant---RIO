import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { X, Loader2, Save } from 'lucide-react';
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
  onSuccess
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
    }
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
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
        <div className="fixed inset-0 transition-opacity" aria-hidden="true" onClick={onClose}>
          <div className="absolute inset-0 bg-gray-500 opacity-75"></div>
        </div>

        <span className="hidden sm:inline-block sm:align-middle sm:h-screen" aria-hidden="true">&#8203;</span>

        <div className="inline-block align-bottom bg-white rounded-lg px-4 pt-5 pb-4 text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg sm:w-full sm:p-6 relative">
          <button 
            onClick={onClose}
            className="absolute top-4 right-4 text-gray-400 hover:text-gray-500"
          >
            <X className="h-5 w-5" />
          </button>
          
          <div className="mb-5">
            <h3 className="text-lg leading-6 font-medium text-gray-900">
              Edit Timetable Entry
            </h3>
            <p className="text-sm text-gray-500 mt-1">
              Modifying an entry will change the timetable status to REVIEWED, requiring re-validation.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Room</label>
              <select
                value={roomId}
                onChange={(e) => setRoomId(e.target.value ? Number(e.target.value) : '')}
                className="w-full border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                disabled={updateMutation.isPending}
              >
                <option value="">Unassigned</option>
                {rooms.map(r => (
                  <option key={r.id} value={r.id}>{r.room_number} (Cap: {r.capacity})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Time Slot</label>
              <select
                value={slotId}
                onChange={(e) => setSlotId(e.target.value ? Number(e.target.value) : '')}
                className="w-full border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                disabled={updateMutation.isPending}
              >
                <option value="">Unassigned</option>
                {timeSlots.map(s => (
                  <option key={s.id} value={s.id}>{s.day} {s.start_time.substring(0, 5)} - {s.end_time.substring(0, 5)}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Faculty</label>
              <select
                value={facultyId}
                onChange={(e) => setFacultyId(e.target.value ? Number(e.target.value) : '')}
                className="w-full border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                disabled={updateMutation.isPending}
              >
                <option value="">Unassigned</option>
                {facultyList.map(f => (
                  <option key={f.id} value={f.id}>Faculty {f.id} (User {f.user_id})</option>
                ))}
              </select>
            </div>

            {errorStatus && (
              <div className="mt-2 text-sm text-red-600 bg-red-50 p-2 rounded border border-red-200">
                {errorMessage}
              </div>
            )}

            <div className="mt-5 sm:mt-6 sm:grid sm:grid-cols-2 sm:gap-3 sm:grid-flow-row-dense">
              <button
                type="submit"
                disabled={updateMutation.isPending}
                className="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-indigo-600 text-base font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:col-start-2 sm:text-sm disabled:opacity-50"
              >
                {updateMutation.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin mt-0.5" /> : <Save className="h-4 w-4 mr-2 mt-0.5" />}
                Save Changes
              </button>
              <button
                type="button"
                onClick={onClose}
                disabled={updateMutation.isPending}
                className="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:mt-0 sm:col-start-1 sm:text-sm disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
