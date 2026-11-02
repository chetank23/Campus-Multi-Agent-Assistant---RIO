import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Boxes,
  Calendar,
  MapPin,
  Users,
} from 'lucide-react';
import { isAxiosError } from 'axios';
import {
  DataTable,
  type Column,
  FormModal,
  ConfirmDialog,
  StatusBadge,
} from '@/components/common';
import {
  resourcesApi,
  type ResourceResponse,
  type ResourceBookingResponse,
  type ResourceBookingCreate,
} from '@/api/resources';
import { formatTime12h } from '@/utils/timeFormatter';

export function FacultyResourcesPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'browse' | 'my-bookings'>('browse');

  // Booking Modal
  const [isBookModalOpen, setIsBookModalOpen] = useState(false);
  const [selectedResource, setSelectedResource] = useState<ResourceResponse | null>(null);
  const [bookingDate, setBookingDate] = useState('');
  const [startTime, setStartTime] = useState('10:00');
  const [endTime, setEndTime] = useState('11:00');
  const [purpose, setPurpose] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  // Cancel Modal
  const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);
  const [bookingToCancel, setBookingToCancel] = useState<ResourceBookingResponse | null>(null);
  const [cancelReason] = useState('Cancelled by faculty request');

  // Queries
  const { data: resources } = useQuery({
    queryKey: ['faculty-resources'],
    queryFn: () => resourcesApi.getAll(),
  });

  const {
    data: bookings,
    isLoading: isBookingsLoading,
    isError: isBookingsError,
    error: bookingsError,
    refetch: refetchBookings,
  } = useQuery({
    queryKey: ['faculty-bookings'],
    queryFn: () => resourcesApi.getBookings(),
  });

  const getErrorMsg = (err: unknown, defaultMsg: string) => {
    if (isAxiosError(err)) {
      return err.response?.data?.detail || defaultMsg;
    } else if (err instanceof Error) {
      return err.message;
    }
    return defaultMsg;
  };

  const createBookingMutation = useMutation({
    mutationFn: (payload: ResourceBookingCreate) => resourcesApi.createBooking(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['faculty-bookings'] });
      setIsBookModalOpen(false);
      resetBookingForm();
      setActiveTab('my-bookings');
    },
    onError: (err) => setFormError(getErrorMsg(err, 'Booking request failed.')),
  });

  const cancelBookingMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      resourcesApi.cancelBooking(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['faculty-bookings'] });
      setIsCancelModalOpen(false);
      setBookingToCancel(null);
    },
  });

  const resetBookingForm = () => {
    setBookingDate('');
    setStartTime('10:00');
    setEndTime('11:00');
    setPurpose('');
    setFormError(null);
  };

  const handleOpenBookModal = (res: ResourceResponse) => {
    setSelectedResource(res);
    resetBookingForm();
    setIsBookModalOpen(true);
  };

  const handleSubmitBooking = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedResource || !bookingDate || !purpose.trim()) {
      setFormError('All fields including date and purpose are required.');
      return;
    }
    if (startTime >= endTime) {
      setFormError('End time must be strictly after start time.');
      return;
    }
    createBookingMutation.mutate({
      resource_id: selectedResource.id,
      date: bookingDate,
      start_time: startTime.length === 5 ? `${startTime}:00` : startTime,
      end_time: endTime.length === 5 ? `${endTime}:00` : endTime,
      purpose: purpose.trim(),
    });
  };

  const bookingColumns: Column<ResourceBookingResponse>[] = [
    {
      header: 'Booking ID & Resource',
      accessor: 'resource_name',
      render: (row) => (
        <div>
          <div className="font-bold text-slate-900">{row.resource_name || `Resource #${row.resource_id}`}</div>
          <div className="text-xs text-slate-500 font-mono">Booking #{row.id} · {row.resource_location || 'Campus'}</div>
        </div>
      ),
    },
    {
      header: 'Reservation Interval',
      accessor: 'date',
      render: (row) => (
        <div>
          <div className="font-medium text-slate-800 text-xs">{row.date}</div>
          <div className="text-xs text-slate-500 font-mono">
            {formatTime12h(row.start_time)} – {formatTime12h(row.end_time)}
          </div>
        </div>
      ),
    },
    {
      header: 'Purpose',
      accessor: 'purpose',
      render: (row) => (
        <span className="text-xs text-slate-700 line-clamp-2">{row.purpose}</span>
      ),
    },
    {
      header: 'Status',
      accessor: 'status',
      render: (row) => {
        const variant =
          row.status === 'APPROVED'
            ? 'success'
            : row.status === 'PENDING'
            ? 'warning'
            : 'danger';
        return <StatusBadge status={row.status} variant={variant} />;
      },
    },
    {
      header: 'Actions',
      align: 'right',
      render: (row) =>
        row.status === 'PENDING' || row.status === 'APPROVED' ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setBookingToCancel(row);
              setIsCancelModalOpen(true);
            }}
            className="px-2.5 py-1 text-xs font-semibold text-red-600 hover:text-red-800 hover:bg-red-50 rounded-md transition-colors"
          >
            Cancel
          </button>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        ),
    },
  ];

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto pb-10">
      {/* Top Banner */}
      <div className="bg-[#142542] text-white p-6 rounded-2xl shadow-sm border border-[#1D3152] flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Boxes size={20} className="text-[#38BDF8]" />
            <h1 className="text-xl font-black tracking-tight">Campus Resource Reservations</h1>
          </div>
          <p className="text-xs text-[#94A3B8] mt-1">
            Browse and reserve institutional auditoriums, seminar halls, high-performance computing labs, and project suites.
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200 gap-4">
        <button
          onClick={() => setActiveTab('browse')}
          className={`pb-3 text-sm font-semibold border-b-2 transition-colors flex items-center gap-2 ${
            activeTab === 'browse'
              ? 'border-primary-600 text-primary-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Boxes size={16} />
          Available Campus Spaces ({resources?.length || 0})
        </button>
        <button
          onClick={() => setActiveTab('my-bookings')}
          className={`pb-3 text-sm font-semibold border-b-2 transition-colors flex items-center gap-2 ${
            activeTab === 'my-bookings'
              ? 'border-primary-600 text-primary-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Calendar size={16} />
          My Reservations ({bookings?.length || 0})
        </button>
      </div>

      {activeTab === 'browse' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {resources?.map((res) => (
            <div
              key={res.id}
              className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs flex flex-col justify-between space-y-4 hover:shadow-card transition-shadow"
            >
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="text-sm font-bold text-slate-900">{res.name}</h3>
                  <StatusBadge status={res.status} />
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <MapPin size={14} className="text-slate-400" />
                  <span>{res.location || 'Central Campus'}</span>
                </div>
                {res.capacity && (
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <Users size={14} className="text-slate-400" />
                    <span>Capacity: {res.capacity} Seats</span>
                  </div>
                )}
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center justify-between">
                <span className="text-[11px] font-mono text-slate-400 font-semibold uppercase">
                  {res.resource_type}
                </span>
                <button
                  onClick={() => handleOpenBookModal(res)}
                  disabled={res.status !== 'ACTIVE'}
                  className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-bold rounded-xl shadow-xs transition-colors disabled:opacity-50"
                >
                  Reserve Space
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <DataTable<ResourceBookingResponse>
          columns={bookingColumns}
          data={bookings || []}
          isLoading={isBookingsLoading}
          isError={isBookingsError}
          error={bookingsError as Error | null}
          onRefresh={refetchBookings}
          keyExtractor={(row) => row.id}
          searchPlaceholder="Search reservation requests…"
          emptyMessage="You have not submitted any room or auditorium booking requests yet."
        />
      )}

      {/* Book Resource Modal */}
      <FormModal
        isOpen={isBookModalOpen}
        onClose={() => setIsBookModalOpen(false)}
        title={`Request Reservation: ${selectedResource?.name}`}
      >
        <form onSubmit={handleSubmitBooking} className="p-6 space-y-4">
          {formError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 font-medium">
              {formError}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Reservation Date *
              </label>
              <input
                type="date"
                required
                min={new Date().toISOString().split('T')[0]}
                value={bookingDate}
                onChange={(e) => setBookingDate(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Start Time *
                </label>
                <input
                  type="time"
                  required
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
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
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Purpose / Event Description *
              </label>
              <textarea
                rows={3}
                required
                placeholder="e.g. Guest lecture on Distributed Systems for CS 6th Semester"
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm"
              />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
            <button
              type="button"
              onClick={() => setIsBookModalOpen(false)}
              className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createBookingMutation.isPending}
              className="px-4 py-2 bg-[#2B568F] hover:bg-[#1D3B5C] text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
            >
              {createBookingMutation.isPending ? 'Requesting…' : 'Submit Reservation'}
            </button>
          </div>
        </form>
      </FormModal>

      {/* Cancel Booking Confirmation Dialog */}
      <ConfirmDialog
        isOpen={isCancelModalOpen}
        onCancel={() => {
          setIsCancelModalOpen(false);
          setBookingToCancel(null);
        }}
        title="Cancel Resource Reservation"
        message={`Are you sure you want to cancel reservation #${bookingToCancel?.id} for ${bookingToCancel?.resource_name}? Any global space lock will be released.`}
        confirmLabel="Confirm Cancellation"
        isDestructive
        isProcessing={cancelBookingMutation.isPending}
        onConfirm={() => {
          if (bookingToCancel) {
            cancelBookingMutation.mutate({ id: bookingToCancel.id, reason: cancelReason });
          }
        }}
      />
    </div>
  );
}
