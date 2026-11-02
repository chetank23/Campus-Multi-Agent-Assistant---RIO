/**
 * pages/faculty/FacultyEventsPage.tsx
 * -----------------------------------
 * Club & Activity Coordination Workspace for Faculty Members.
 */

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Sparkles,
  Clock,
  Plus,
  Send,
  Radio,
  Ban,
  ShieldCheck,
  Search,
} from 'lucide-react';
import { isAxiosError } from 'axios';

import {
  PageHeader,
  StatCard,
  DataTable,
  type Column,
  FormModal,
  StatusBadge,
  type StatusVariant,
} from '@/components/common';

import {
  eventsApi,
  type CampusEventItem,
  type ClubItem,
  type VenueCheckResponse,
  type EventCategory,
  type TargetAudience,
} from '@/api/events';
import { roomsApi, type RoomResponse } from '@/api/rooms';
import { useAuth } from '@/auth/AuthProvider';

const STATUS_VARIANT_MAP: Record<string, StatusVariant> = {
  DRAFT: 'neutral',
  PENDING_APPROVAL: 'warning',
  APPROVED: 'info',
  PUBLISHED: 'success',
  ONGOING: 'primary',
  COMPLETED: 'neutral',
  CANCELLED: 'danger',
  REJECTED: 'danger',
  ARCHIVED: 'neutral',
};

export function FacultyEventsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<'all' | 'drafts' | 'pending' | 'published' | 'live'>('all');
  const [searchQuery, setSearchQuery] = useState('');

  // Create / Edit modal state
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editingEvent, setEditingEvent] = useState<CampusEventItem | null>(null);
  const [cancelModalEvent, setCancelModalEvent] = useState<CampusEventItem | null>(null);
  const [cancelReason, setCancelReason] = useState('');

  const [eventForm, setEventForm] = useState<{
    title: string;
    description: string;
    category: EventCategory;
    club_id: number | null;
    start_time: string;
    end_time: string;
    room_id: number | null;
    venue_name: string;
    target_audience: TargetAudience;
    requires_approval: boolean;
  }>({
    title: '',
    description: '',
    category: 'WORKSHOP',
    club_id: null,
    start_time: '',
    end_time: '',
    room_id: null,
    venue_name: '',
    target_audience: 'ALL',
    requires_approval: true,
  });

  // Venue check inline state
  const [venueChecking, setVenueChecking] = useState(false);
  const [venueCheckResult, setVenueCheckResult] = useState<VenueCheckResponse | null>(null);
  const [venueCheckError, setVenueCheckError] = useState<string | null>(null);

  // Queries
  const { data: myClubs = [] } = useQuery<ClubItem[]>({
    queryKey: ['faculty', 'my-clubs'],
    queryFn: () => eventsApi.listFacultyMyClubs(),
  });

  const { data: events = [], isLoading: eventsLoading, isError: eventsError } = useQuery<CampusEventItem[]>({
    queryKey: ['faculty', 'events', searchQuery],
    queryFn: () => eventsApi.listEvents({ search: searchQuery || undefined }),
  });

  const { data: liveEvents = [] } = useQuery<CampusEventItem[]>({
    queryKey: ['faculty', 'events', 'live'],
    queryFn: () => eventsApi.getLiveEvents(),
    refetchInterval: 30_000,
  });

  const { data: rooms = [] } = useQuery<RoomResponse[]>({
    queryKey: ['faculty', 'rooms'],
    queryFn: () => roomsApi.getAll(),
  });

  // Filtered views
  const filteredEvents = useMemo(() => {
    switch (activeTab) {
      case 'drafts':
        return events.filter((e) => e.status === 'DRAFT');
      case 'pending':
        return events.filter((e) => e.status === 'PENDING_APPROVAL');
      case 'published':
        return events.filter((e) => ['APPROVED', 'PUBLISHED'].includes(e.status));
      case 'live':
        return events.filter((e) => e.status === 'ONGOING');
      default:
        return events;
    }
  }, [events, activeTab]);

  // Mutations
  const createMutation = useMutation({
    mutationFn: async (payload: typeof eventForm) => {
      const formatted = {
        ...payload,
        start_time: new Date(payload.start_time).toISOString(),
        end_time: new Date(payload.end_time).toISOString(),
        room_id: payload.room_id || null,
        club_id: payload.club_id || null,
      };
      if (editingEvent) {
        return eventsApi.updateEvent(editingEvent.id, formatted);
      }
      return eventsApi.createEvent(formatted);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['faculty', 'events'] });
      setCreateModalOpen(false);
      setEditingEvent(null);
      setVenueCheckResult(null);
    },
  });

  const submitMutation = useMutation({
    mutationFn: (id: number) => eventsApi.submitEvent(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['faculty', 'events'] });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      eventsApi.cancelEvent(id, { reason }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['faculty', 'events'] });
      setCancelModalEvent(null);
      setCancelReason('');
    },
  });

  // Venue inline validator
  const handleValidateVenue = async () => {
    if (!eventForm.room_id || !eventForm.start_time || !eventForm.end_time) {
      setVenueCheckError('Please select a room, start time, and end time first.');
      return;
    }
    setVenueChecking(true);
    setVenueCheckError(null);
    try {
      const res = await eventsApi.checkVenueAvailability({
        room_id: eventForm.room_id,
        start_time: new Date(eventForm.start_time).toISOString(),
        end_time: new Date(eventForm.end_time).toISOString(),
        exclude_event_id: editingEvent?.id,
      });
      setVenueCheckResult(res);
    } catch (err: unknown) {
      if (isAxiosError(err)) {
        setVenueCheckError(err.response?.data?.detail || 'Conflict check failed');
      } else {
        setVenueCheckError('Conflict check failed');
      }
    } finally {
      setVenueChecking(false);
    }
  };

  const columns: Column<CampusEventItem>[] = [
    {
      header: 'Event / Activity',
      render: (row) => (
        <div>
          <div className="font-semibold text-slate-900">{row.title}</div>
          <div className="text-xs text-slate-500">
            {row.category} {row.club_name ? `• ${row.club_name}` : ''}
          </div>
        </div>
      ),
    },
    {
      header: 'Schedule & Location',
      render: (row) => (
        <div className="text-xs space-y-0.5">
          <div className="font-medium text-slate-800">
            {new Date(row.start_time).toLocaleString(undefined, {
              dateStyle: 'short',
              timeStyle: 'short',
            })}{' '}
            –{' '}
            {new Date(row.end_time).toLocaleTimeString(undefined, {
              timeStyle: 'short',
            })}
          </div>
          <div className="text-slate-500">
            {row.room_number ? `Room ${row.room_number}` : row.venue_name || 'TBA'}
          </div>
        </div>
      ),
    },
    {
      header: 'Target Audience',
      render: (row) => (
        <span className="inline-block px-2 py-0.5 text-xs font-medium rounded bg-slate-100 text-slate-700">
          {row.target_audience}
        </span>
      ),
    },
    {
      header: 'Status',
      render: (row) => (
        <StatusBadge
          status={row.status}
          variant={STATUS_VARIANT_MAP[row.status] || 'neutral'}
        />
      ),
    },
    {
      header: 'Actions',
      align: 'right',
      render: (row) => {
        const isOwner = row.coordinator_id === user?.id;
        return (
          <div className="flex items-center gap-1.5 justify-end">
            {isOwner && row.status === 'DRAFT' && (
              <>
                <button
                  onClick={() => {
                    setEditingEvent(row);
                    setEventForm({
                      title: row.title,
                      description: row.description || '',
                      category: row.category,
                      club_id: row.club_id || null,
                      start_time: row.start_time.slice(0, 16),
                      end_time: row.end_time.slice(0, 16),
                      room_id: row.room_id || null,
                      venue_name: row.venue_name || '',
                      target_audience: row.target_audience,
                      requires_approval: row.requires_approval,
                    });
                    setCreateModalOpen(true);
                  }}
                  className="px-2 py-1 text-xs font-semibold rounded bg-slate-100 text-slate-700 hover:bg-slate-200"
                >
                  Edit
                </button>
                <button
                  onClick={() => submitMutation.mutate(row.id)}
                  disabled={submitMutation.isPending}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded bg-primary-50 text-primary-700 border border-primary-200 hover:bg-primary-100"
                >
                  <Send size={12} /> Submit
                </button>
              </>
            )}
            {isOwner && !['CANCELLED', 'REJECTED', 'COMPLETED'].includes(row.status) && (
              <button
                onClick={() => setCancelModalEvent(row)}
                className="p-1 text-slate-400 hover:text-red-600 rounded"
                title="Cancel Event"
              >
                <Ban size={15} />
              </button>
            )}
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Club & Activity Coordination"
        subtitle="Plan workshops, organize club events, check facility availability, and manage extracurricular campus activities."
        breadcrumbs={[
          { label: 'Dashboard', href: '/faculty' },
          { label: 'Clubs & Events' },
        ]}
      />

      {/* Coordinator Status Banner */}
      {myClubs.length > 0 ? (
        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-xs">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-600 text-white flex items-center justify-center shrink-0">
              <ShieldCheck size={22} />
            </div>
            <div>
              <h4 className="text-sm font-bold text-blue-950">Active Club Coordinator</h4>
              <p className="text-xs text-blue-800">
                You are assigned coordinator for{' '}
                <strong>{myClubs.map((c) => c.name).join(', ')}</strong>. You can create activities and reserve campus facilities.
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              setEditingEvent(null);
              setEventForm({
                title: '',
                description: '',
                category: 'CLUB_ACTIVITY',
                club_id: myClubs[0]?.id || null,
                start_time: '',
                end_time: '',
                room_id: null,
                venue_name: '',
                target_audience: 'ALL',
                requires_approval: true,
              });
              setCreateModalOpen(true);
            }}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-bold rounded-lg bg-blue-600 text-white hover:bg-blue-700 shadow-xs shrink-0"
          >
            <Plus size={14} /> Create Activity / Event
          </button>
        </div>
      ) : (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-slate-200 text-slate-700 flex items-center justify-center shrink-0">
              <Sparkles size={20} />
            </div>
            <div>
              <h4 className="text-sm font-bold text-slate-800">Campus Events View</h4>
              <p className="text-xs text-slate-600">
                You can browse all published campus events. To coordinate club activities or departmental workshops, an Administrator can assign Coordinator capabilities.
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              setEditingEvent(null);
              setEventForm({
                title: '',
                description: '',
                category: 'WORKSHOP',
                club_id: null,
                start_time: '',
                end_time: '',
                room_id: null,
                venue_name: '',
                target_audience: 'ALL',
                requires_approval: true,
              });
              setCreateModalOpen(true);
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-primary-600 text-white hover:bg-primary-700 shrink-0"
          >
            <Plus size={14} /> Propose Event Draft
          </button>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="My Clubs"
          value={myClubs.length}
          icon={<Sparkles size={20} className="text-primary-600" />}
          sub={myClubs.length > 0 ? 'Assigned' : 'None'}
          variant="primary"
        />
        <StatCard
          label="Live Now"
          value={liveEvents.length}
          icon={<Radio size={20} className="text-emerald-600 animate-pulse" />}
          sub="Real-time ongoing"
          variant="success"
        />
        <StatCard
          label="My Drafts"
          value={events.filter((e) => e.status === 'DRAFT' && e.coordinator_id === user?.id).length}
          icon={<Clock size={20} className="text-amber-500" />}
          sub="Unsubmitted"
          variant="warning"
        />
        <StatCard
          label="Pending Review"
          value={events.filter((e) => e.status === 'PENDING_APPROVAL').length}
          icon={<Send size={20} className="text-blue-500" />}
          sub="With administration"
          variant="default"
        />
      </div>

      {/* "My Clubs" Cards Section */}
      {myClubs.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <Sparkles size={16} className="text-blue-600" /> My Assigned Clubs & Chapters
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {myClubs.map((club) => (
              <div
                key={club.id}
                className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="px-2 py-0.5 text-xs font-semibold rounded bg-blue-50 text-blue-700">
                    {club.category}
                  </span>
                  <span className="text-xs font-mono text-slate-400">{club.code}</span>
                </div>
                <h4 className="text-base font-bold text-slate-900">{club.name}</h4>
                <p className="text-xs text-slate-600 line-clamp-2">
                  {club.description || 'No description provided.'}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filter Tabs & Search */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row gap-3 justify-between items-center bg-white p-3 rounded-xl border border-slate-200">
          <div className="flex border-b border-slate-200 sm:border-0 w-full sm:w-auto overflow-x-auto">
            <button
              onClick={() => setActiveTab('all')}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap ${
                activeTab === 'all'
                  ? 'bg-primary-50 text-primary-700 font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              All Events ({events.length})
            </button>
            <button
              onClick={() => setActiveTab('drafts')}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap ${
                activeTab === 'drafts'
                  ? 'bg-primary-50 text-primary-700 font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Drafts ({events.filter((e) => e.status === 'DRAFT').length})
            </button>
            <button
              onClick={() => setActiveTab('pending')}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap ${
                activeTab === 'pending'
                  ? 'bg-primary-50 text-primary-700 font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Pending ({events.filter((e) => e.status === 'PENDING_APPROVAL').length})
            </button>
            <button
              onClick={() => setActiveTab('published')}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap ${
                activeTab === 'published'
                  ? 'bg-primary-50 text-primary-700 font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Published
            </button>
            <button
              onClick={() => setActiveTab('live')}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap ${
                activeTab === 'live'
                  ? 'bg-primary-50 text-primary-700 font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Live Now
            </button>
          </div>

          <div className="relative w-full sm:w-64">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search events..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1 text-xs border border-slate-200 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-primary-500"
            />
          </div>
        </div>

        <DataTable<CampusEventItem>
          columns={columns}
          data={filteredEvents}
          isLoading={eventsLoading}
          isError={eventsError}
          keyExtractor={(row) => row.id}
          emptyMessage="No events found. Create an event or activity draft to get started."
        />
      </div>

      {/* Create / Edit Event Modal */}
      {createModalOpen && (
        <FormModal
          isOpen={createModalOpen}
          title={editingEvent ? 'Edit Event Draft' : 'Create Campus Event / Club Activity'}
          onClose={() => setCreateModalOpen(false)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              createMutation.mutate(eventForm);
            }}
            className="space-y-3 text-xs max-h-[70vh] overflow-y-auto pr-1"
          >
            <div>
              <label className="block font-medium text-slate-700 mb-1">Event Title</label>
              <input
                required
                type="text"
                value={eventForm.title}
                onChange={(e) => setEventForm({ ...eventForm, title: e.target.value })}
                placeholder="e.g. AI & Robotics Hands-on Workshop"
                className="w-full p-2 border border-slate-200 rounded-lg"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block font-medium text-slate-700 mb-1">Category</label>
                <select
                  value={eventForm.category}
                  onChange={(e) =>
                    setEventForm({ ...eventForm, category: e.target.value as EventCategory })
                  }
                  className="w-full p-2 border border-slate-200 rounded-lg bg-white"
                >
                  <option value="WORKSHOP">Workshop</option>
                  <option value="SEMINAR">Seminar</option>
                  <option value="HACKATHON">Hackathon</option>
                  <option value="CLUB_ACTIVITY">Club Activity</option>
                  <option value="CULTURAL">Cultural</option>
                  <option value="SPORTS">Sports</option>
                  <option value="ACADEMIC">Academic</option>
                  <option value="GENERAL">General</option>
                </select>
              </div>

              <div>
                <label className="block font-medium text-slate-700 mb-1">Organizing Club (Optional)</label>
                <select
                  value={eventForm.club_id || ''}
                  onChange={(e) =>
                    setEventForm({
                      ...eventForm,
                      club_id: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                  className="w-full p-2 border border-slate-200 rounded-lg bg-white"
                >
                  <option value="">None (General Event)</option>
                  {myClubs.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.code})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block font-medium text-slate-700 mb-1">Start Date & Time</label>
                <input
                  required
                  type="datetime-local"
                  value={eventForm.start_time}
                  onChange={(e) => setEventForm({ ...eventForm, start_time: e.target.value })}
                  className="w-full p-2 border border-slate-200 rounded-lg"
                />
              </div>

              <div>
                <label className="block font-medium text-slate-700 mb-1">End Date & Time</label>
                <input
                  required
                  type="datetime-local"
                  value={eventForm.end_time}
                  onChange={(e) => setEventForm({ ...eventForm, end_time: e.target.value })}
                  className="w-full p-2 border border-slate-200 rounded-lg"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block font-medium text-slate-700 mb-1">Campus Room / Facility</label>
                <select
                  value={eventForm.room_id || ''}
                  onChange={(e) =>
                    setEventForm({
                      ...eventForm,
                      room_id: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                  className="w-full p-2 border border-slate-200 rounded-lg bg-white"
                >
                  <option value="">Select Room (or enter Venue name)</option>
                  {rooms.map((r: RoomResponse) => (
                    <option key={r.id} value={r.id}>
                      Room {r.room_number} ({r.room_type}, Cap: {r.capacity})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block font-medium text-slate-700 mb-1">Venue Name / Location</label>
                <input
                  type="text"
                  value={eventForm.venue_name}
                  onChange={(e) => setEventForm({ ...eventForm, venue_name: e.target.value })}
                  placeholder="e.g. Main Auditorium Lawn"
                  className="w-full p-2 border border-slate-200 rounded-lg"
                />
              </div>
            </div>

            {/* Inline Venue Availability Check Button */}
            {eventForm.room_id && (
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-700">Conflict Checker:</span>
                  <button
                    type="button"
                    onClick={handleValidateVenue}
                    disabled={venueChecking}
                    className="px-2.5 py-1 text-xs font-semibold rounded bg-slate-200 text-slate-800 hover:bg-slate-300 disabled:opacity-50"
                  >
                    {venueChecking ? 'Checking...' : 'Check Venue Conflicts'}
                  </button>
                </div>
                {venueCheckError && (
                  <p className="text-red-600 text-xs">{venueCheckError}</p>
                )}
                {venueCheckResult && (
                  <div
                    className={`p-2 rounded text-xs ${
                      venueCheckResult.is_available
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {venueCheckResult.is_available
                      ? '✓ Venue available with no timetable or booking conflicts!'
                      : `⚠ ${venueCheckResult.conflicts.length} conflict(s) found! Please choose another time or room.`}
                  </div>
                )}
              </div>
            )}

            <div>
              <label className="block font-medium text-slate-700 mb-1">Target Audience</label>
              <select
                value={eventForm.target_audience}
                onChange={(e) =>
                  setEventForm({
                    ...eventForm,
                    target_audience: e.target.value as TargetAudience,
                  })
                }
                className="w-full p-2 border border-slate-200 rounded-lg bg-white"
              >
                <option value="ALL">All Campus (Students & Faculty)</option>
                <option value="STUDENT">Students Only</option>
                <option value="FACULTY">Faculty Only</option>
                <option value="DEPARTMENT_ONLY">Department Only</option>
                <option value="MEMBERS_ONLY">Club Members Only</option>
              </select>
            </div>

            <div>
              <label className="block font-medium text-slate-700 mb-1">Description</label>
              <textarea
                value={eventForm.description}
                onChange={(e) => setEventForm({ ...eventForm, description: e.target.value })}
                placeholder="Overview, requirements, agenda..."
                rows={3}
                className="w-full p-2 border border-slate-200 rounded-lg"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setCreateModalOpen(false)}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="px-4 py-1.5 rounded-lg bg-primary-600 text-white font-semibold"
              >
                {editingEvent ? 'Save Changes' : 'Create Draft'}
              </button>
            </div>
          </form>
        </FormModal>
      )}

      {/* Cancel Event Modal */}
      {cancelModalEvent && (
        <FormModal
          isOpen={!!cancelModalEvent}
          title="Cancel Scheduled Event"
          onClose={() => setCancelModalEvent(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              cancelMutation.mutate({ id: cancelModalEvent.id, reason: cancelReason });
            }}
            className="space-y-3 text-xs"
          >
            <p className="text-slate-600">
              Are you sure you want to cancel <strong>{cancelModalEvent.title}</strong>?
            </p>
            <div>
              <label className="block font-medium text-slate-700 mb-1">Reason for Cancellation</label>
              <textarea
                required
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="Cancellation reason..."
                rows={2}
                className="w-full p-2 border border-slate-200 rounded-lg text-xs"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setCancelModalEvent(null)}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600"
              >
                Back
              </button>
              <button
                type="submit"
                disabled={cancelMutation.isPending}
                className="px-4 py-1.5 rounded-lg bg-red-600 text-white font-semibold"
              >
                Cancel Event
              </button>
            </div>
          </form>
        </FormModal>
      )}
    </div>
  );
}
