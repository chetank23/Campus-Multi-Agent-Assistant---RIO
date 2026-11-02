import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Clock, Trash2, CalendarDays } from 'lucide-react';
import { isAxiosError } from 'axios';
import {
  DataTable,
  type Column,
  FormModal,
  ConfirmDialog,
  PageHeader,
  StatusBadge,
} from '@/components/common';
import {
  academicCalendarApi,
  timeSlotsApi,
  type AcademicCalendarItem,
  type TimeSlotItem,
} from '@/api/academicCalendar';
import { academicYearsApi } from '@/api/academicYears';
import { formatTime12h } from '@/utils/timeFormatter';

export function CalendarTimeSlotsPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'calendar' | 'slots'>('calendar');

  // Modals state
  const [isEventModalOpen, setIsEventModalOpen] = useState(false);
  const [isSlotModalOpen, setIsSlotModalOpen] = useState(false);
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ type: 'event' | 'slot'; id: number; label: string } | null>(null);

  // Event Form State
  const [academicYearId, setAcademicYearId] = useState<number | ''>('');
  const [eventDate, setEventDate] = useState('');
  const [eventType, setEventType] = useState('HOLIDAY');
  const [eventDesc, setEventDesc] = useState('');
  const [eventError, setEventError] = useState<string | null>(null);

  // Time Slot Form State
  const [slotDay, setSlotDay] = useState('MONDAY');
  const [slotStartTime, setSlotStartTime] = useState('09:00');
  const [slotEndTime, setSlotEndTime] = useState('10:00');
  const [slotType, setSlotType] = useState('CLASS');
  const [slotError, setSlotError] = useState<string | null>(null);

  // Day filter for time slots
  const [selectedDayFilter, setSelectedDayFilter] = useState<string>('ALL');

  // Queries
  const {
    data: calendarEvents,
    isLoading: isCalendarLoading,
    isError: isCalendarError,
    error: calendarError,
    refetch: refetchCalendar,
  } = useQuery({
    queryKey: ['academicCalendar'],
    queryFn: academicCalendarApi.getAll,
  });

  const {
    data: timeSlots,
    isLoading: isSlotsLoading,
    isError: isSlotsError,
    error: slotsError,
    refetch: refetchSlots,
  } = useQuery({
    queryKey: ['timeSlots'],
    queryFn: timeSlotsApi.getAll,
  });

  const { data: academicYears } = useQuery({
    queryKey: ['academicYears'],
    queryFn: academicYearsApi.getAll,
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
  const createEventMutation = useMutation({
    mutationFn: academicCalendarApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['academicCalendar'] });
      setIsEventModalOpen(false);
      resetEventForm();
    },
    onError: (err) => setEventError(getErrorMsg(err, 'Failed to create calendar event.')),
  });

  const deleteEventMutation = useMutation({
    mutationFn: academicCalendarApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['academicCalendar'] });
      setIsDeleteConfirmOpen(false);
      setDeleteTarget(null);
    },
    onError: (err) => alert(getErrorMsg(err, 'Failed to delete event.')),
  });

  const createSlotMutation = useMutation({
    mutationFn: timeSlotsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timeSlots'] });
      setIsSlotModalOpen(false);
      resetSlotForm();
    },
    onError: (err) => setSlotError(getErrorMsg(err, 'Failed to create time slot.')),
  });

  const deleteSlotMutation = useMutation({
    mutationFn: timeSlotsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timeSlots'] });
      setIsDeleteConfirmOpen(false);
      setDeleteTarget(null);
    },
    onError: (err) => alert(getErrorMsg(err, 'Failed to delete time slot.')),
  });

  const resetEventForm = () => {
    setAcademicYearId('');
    setEventDate('');
    setEventType('HOLIDAY');
    setEventDesc('');
    setEventError(null);
  };

  const resetSlotForm = () => {
    setSlotDay('MONDAY');
    setSlotStartTime('09:00');
    setSlotEndTime('10:00');
    setSlotType('CLASS');
    setSlotError(null);
  };

  const handleCreateEvent = (e: React.FormEvent) => {
    e.preventDefault();
    setEventError(null);
    if (!academicYearId || !eventDate || !eventDesc.trim()) {
      setEventError('Academic year, date, and description are required.');
      return;
    }
    createEventMutation.mutate({
      academic_year_id: Number(academicYearId),
      date: eventDate,
      event_type: eventType,
      description: eventDesc.trim(),
    });
  };

  const handleCreateSlot = (e: React.FormEvent) => {
    e.preventDefault();
    setSlotError(null);
    if (!slotStartTime || !slotEndTime) {
      setSlotError('Start time and end time are required.');
      return;
    }
    createSlotMutation.mutate({
      day: slotDay,
      start_time: slotStartTime,
      end_time: slotEndTime,
      slot_type: slotType,
    });
  };

  const handleDeleteConfirm = () => {
    if (!deleteTarget) return;
    if (deleteTarget.type === 'event') {
      deleteEventMutation.mutate(deleteTarget.id);
    } else {
      deleteSlotMutation.mutate(deleteTarget.id);
    }
  };

  // Calendar Columns
  const calendarColumns: Column<AcademicCalendarItem>[] = [
    {
      header: 'Date',
      accessor: 'date',
      render: (row) => <span className="font-semibold text-slate-900 font-mono">{row.date}</span>,
    },
    {
      header: 'Event Type',
      accessor: 'event_type',
      render: (row) => {
        const variant =
          row.event_type === 'HOLIDAY'
            ? 'danger'
            : row.event_type === 'EXAM'
            ? 'warning'
            : 'neutral';
        return <StatusBadge status={row.event_type} variant={variant} />;
      },
    },
    {
      header: 'Description',
      accessor: 'description',
      render: (row) => <span className="text-sm text-slate-700">{row.description || '—'}</span>,
    },
    {
      header: 'Academic Year',
      render: (row) => {
        const ay = academicYears?.find((y) => y.id === row.academic_year_id);
        return <span className="text-xs text-slate-500 font-mono">{ay ? ay.year_name : `#${row.academic_year_id}`}</span>;
      },
    },
    {
      header: 'Actions',
      align: 'right',
      render: (row) => (
        <button
          onClick={(e) => {
            e.stopPropagation();
            setDeleteTarget({ type: 'event', id: row.id, label: `${row.event_type} on ${row.date}` });
            setIsDeleteConfirmOpen(true);
          }}
          className="p-1 text-slate-400 hover:text-red-700 hover:bg-red-50 rounded-md transition-colors"
          title="Delete Event"
        >
          <Trash2 size={16} />
        </button>
      ),
    },
  ];

  // Time Slot Columns
  const filteredSlots = useMemo(() => {
    if (!timeSlots) return [];
    if (selectedDayFilter === 'ALL') return timeSlots;
    return timeSlots.filter((s) => s.day.toUpperCase() === selectedDayFilter);
  }, [timeSlots, selectedDayFilter]);

  const slotColumns: Column<TimeSlotItem>[] = [
    {
      header: 'Day of Week',
      accessor: 'day',
      render: (row) => <span className="font-semibold text-slate-900">{row.day}</span>,
    },
    {
      header: 'Time Interval',
      accessor: 'start_time',
      render: (row) => (
        <span className="text-xs font-mono font-medium text-slate-700">
          {formatTime12h(row.start_time)} – {formatTime12h(row.end_time)}
        </span>
      ),
    },
    {
      header: 'Slot Type',
      accessor: 'slot_type',
      render: (row) => {
        const variant = row.slot_type === 'LAB' ? 'warning' : 'neutral';
        return <StatusBadge status={row.slot_type} variant={variant} />;
      },
    },
    {
      header: 'Actions',
      align: 'right',
      render: (row) => (
        <button
          onClick={(e) => {
            e.stopPropagation();
            setDeleteTarget({ type: 'slot', id: row.id, label: `${row.day} ${row.start_time}–${row.end_time}` });
            setIsDeleteConfirmOpen(true);
          }}
          className="p-1 text-slate-400 hover:text-red-700 hover:bg-red-50 rounded-md transition-colors"
          title="Delete Slot"
        >
          <Trash2 size={16} />
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Academic Calendar & Time Slots"
        subtitle="Manage institutional dates, holidays, examination weeks, and standard timetable time periods."
        actions={
          activeTab === 'calendar' ? (
            <button
              onClick={() => {
                resetEventForm();
                setIsEventModalOpen(true);
              }}
              className="inline-flex items-center gap-2 px-3.5 py-2 bg-[#2B568F] hover:bg-[#1D3B5C] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors"
            >
              <Plus size={16} />
              Add Calendar Event
            </button>
          ) : (
            <button
              onClick={() => {
                resetSlotForm();
                setIsSlotModalOpen(true);
              }}
              className="inline-flex items-center gap-2 px-3.5 py-2 bg-[#2B568F] hover:bg-[#1D3B5C] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors"
            >
              <Plus size={16} />
              Add Time Slot
            </button>
          )
        }
      />

      {/* Tabs */}
      <div className="flex border-b border-slate-200 gap-4">
        <button
          onClick={() => setActiveTab('calendar')}
          className={`pb-3 text-sm font-semibold border-b-2 transition-colors flex items-center gap-2 ${
            activeTab === 'calendar'
              ? 'border-primary-600 text-primary-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <CalendarDays size={16} />
          Academic Calendar Events ({calendarEvents?.length ?? 0})
        </button>
        <button
          onClick={() => setActiveTab('slots')}
          className={`pb-3 text-sm font-semibold border-b-2 transition-colors flex items-center gap-2 ${
            activeTab === 'slots'
              ? 'border-primary-600 text-primary-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Clock size={16} />
          Timetable Time Slots ({timeSlots?.length ?? 0})
        </button>
      </div>

      {activeTab === 'calendar' ? (
        <DataTable<AcademicCalendarItem>
          columns={calendarColumns}
          data={calendarEvents || []}
          isLoading={isCalendarLoading}
          isError={isCalendarError}
          error={calendarError as Error | null}
          onRefresh={refetchCalendar}
          keyExtractor={(row) => row.id}
          searchPlaceholder="Filter calendar events…"
          emptyMessage="No academic events configured. Add semester holidays, examination periods, or university events."
        />
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between bg-white p-3 rounded-xl border border-slate-200">
            <span className="text-xs font-semibold text-slate-700">Filter by Day:</span>
            <div className="flex flex-wrap gap-1.5">
              {['ALL', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY'].map((day) => (
                <button
                  key={day}
                  onClick={() => setSelectedDayFilter(day)}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-colors ${
                    selectedDayFilter === day
                      ? 'bg-primary-600 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {day}
                </button>
              ))}
            </div>
          </div>

          <DataTable<TimeSlotItem>
            columns={slotColumns}
            data={filteredSlots}
            isLoading={isSlotsLoading}
            isError={isSlotsError}
            error={slotsError as Error | null}
            onRefresh={refetchSlots}
            keyExtractor={(row) => row.id}
            searchPlaceholder="Filter slots…"
            emptyMessage="No time slots defined. Configure standard teaching slots for scheduling and solver execution."
          />
        </div>
      )}

      {/* Add Calendar Event Modal */}
      <FormModal
        isOpen={isEventModalOpen}
        onClose={() => setIsEventModalOpen(false)}
        title="Add Academic Calendar Event"
      >
        <form onSubmit={handleCreateEvent} className="p-6 space-y-4">
          {eventError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 font-medium">
              {eventError}
            </div>
          )}
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Academic Year *
              </label>
              <select
                value={academicYearId}
                onChange={(e) => setAcademicYearId(Number(e.target.value))}
                required
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
              >
                <option value="">Select Academic Year</option>
                {academicYears?.map((y) => (
                  <option key={y.id} value={y.id}>
                    {y.year_name} {y.is_active ? '(Active)' : ''}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Date *
                </label>
                <input
                  type="date"
                  required
                  value={eventDate}
                  onChange={(e) => setEventDate(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Event Type *
                </label>
                <select
                  value={eventType}
                  onChange={(e) => setEventType(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
                >
                  <option value="HOLIDAY">HOLIDAY</option>
                  <option value="EXAM">EXAM</option>
                  <option value="EVENT">EVENT</option>
                  <option value="WORKING_DAY">WORKING_DAY</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Description *
              </label>
              <input
                type="text"
                required
                placeholder="e.g. National Holiday / Mid-term Examinations"
                value={eventDesc}
                onChange={(e) => setEventDesc(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
              />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
            <button
              type="button"
              onClick={() => setIsEventModalOpen(false)}
              className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createEventMutation.isPending}
              className="px-4 py-2 bg-[#2B568F] hover:bg-[#1D3B5C] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
            >
              {createEventMutation.isPending ? 'Saving…' : 'Save Event'}
            </button>
          </div>
        </form>
      </FormModal>

      {/* Add Time Slot Modal */}
      <FormModal
        isOpen={isSlotModalOpen}
        onClose={() => setIsSlotModalOpen(false)}
        title="Add Timetable Time Slot"
      >
        <form onSubmit={handleCreateSlot} className="p-6 space-y-4">
          {slotError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 font-medium">
              {slotError}
            </div>
          )}
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Day of Week *
              </label>
              <select
                value={slotDay}
                onChange={(e) => setSlotDay(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
              >
                {['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY'].map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Start Time *
                </label>
                <input
                  type="time"
                  required
                  value={slotStartTime}
                  onChange={(e) => setSlotStartTime(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  End Time *
                </label>
                <input
                  type="time"
                  required
                  value={slotEndTime}
                  onChange={(e) => setSlotEndTime(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Slot Type *
              </label>
              <select
                value={slotType}
                onChange={(e) => setSlotType(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white"
              >
                <option value="CLASS">CLASS (Theory Lecture)</option>
                <option value="LAB">LAB (Practical Session)</option>
                <option value="RECESS">RECESS (Break Period)</option>
              </select>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
            <button
              type="button"
              onClick={() => setIsSlotModalOpen(false)}
              className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createSlotMutation.isPending}
              className="px-4 py-2 bg-[#2B568F] hover:bg-[#1D3B5C] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
            >
              {createSlotMutation.isPending ? 'Saving…' : 'Save Slot'}
            </button>
          </div>
        </form>
      </FormModal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={isDeleteConfirmOpen}
        onCancel={() => {
          setIsDeleteConfirmOpen(false);
          setDeleteTarget(null);
        }}
        title="Confirm Deletion"
        message={`Are you sure you want to delete ${deleteTarget?.label}? This operation cannot be undone.`}
        confirmLabel="Delete"
        isDestructive
        isProcessing={deleteEventMutation.isPending || deleteSlotMutation.isPending}
        onConfirm={handleDeleteConfirm}
      />
    </div>
  );
}
