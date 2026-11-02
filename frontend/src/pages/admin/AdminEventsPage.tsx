/**
 * pages/admin/AdminEventsPage.tsx
 * --------------------------------
 * Campus Events, Club Management & Coordinator Capabilities Command Center (Admin).
 */

import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Sparkles,
  Calendar,
  CheckCircle2,
  AlertTriangle,
  Search,
  Plus,
  Shield,
  Building2,
  Radio,
  UserCheck,
  Ban,
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
  type CoordinatorCapabilityItem,
  type VenueCheckResponse,
} from '@/api/events';
import { roomsApi, type RoomResponse } from '@/api/rooms';
import { usersApi, type UserAdminItem } from '@/api/users';

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

export function AdminEventsPage() {
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<
    'events' | 'approvals' | 'clubs' | 'capabilities' | 'venue_check'
  >('events');

  // Search & Filters
  const [eventSearch, setEventSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [timeFilter, setTimeFilter] = useState('');

  // Modals state
  const [reviewModalEvent, setReviewModalEvent] = useState<CampusEventItem | null>(null);
  const [reviewAction, setReviewAction] = useState<'APPROVE' | 'REJECT'>('APPROVE');
  const [reviewNote, setReviewNote] = useState('');
  const [cancelModalEvent, setCancelModalEvent] = useState<CampusEventItem | null>(null);
  const [cancelReason, setCancelReason] = useState('');

  // Club modal state
  const [clubModalOpen, setClubModalOpen] = useState(false);
  const [editingClub, setEditingClub] = useState<ClubItem | null>(null);
  const [clubForm, setClubForm] = useState({
    name: '',
    code: '',
    category: 'TECHNICAL',
    description: '',
  });

  // Capability modal state
  const [capabilityModalOpen, setCapabilityModalOpen] = useState(false);
  const [revokeModalCap, setRevokeModalCap] = useState<CoordinatorCapabilityItem | null>(null);
  const [revokeReason, setRevokeReason] = useState('');
  const [capForm, setCapForm] = useState({
    user_id: 0,
    capability: 'EVENT_COORDINATOR',
    scope_type: 'GLOBAL' as 'GLOBAL' | 'CLUB' | 'DEPARTMENT',
    scope_id: undefined as number | undefined,
    expires_at: '',
  });

  // Venue check state
  const [venueCheckRoomId, setVenueCheckRoomId] = useState<number>(0);
  const [venueCheckStart, setVenueCheckStart] = useState<string>('');
  const [venueCheckEnd, setVenueCheckEnd] = useState<string>('');
  const [venueCheckResult, setVenueCheckResult] = useState<VenueCheckResponse | null>(null);
  const [venueChecking, setVenueChecking] = useState(false);
  const [venueCheckError, setVenueCheckError] = useState<string | null>(null);

  // Queries
  const { data: allEvents = [], isLoading: eventsLoading, isError: eventsError } = useQuery<CampusEventItem[]>({
    queryKey: ['admin', 'events', categoryFilter, timeFilter, eventSearch],
    queryFn: () =>
      eventsApi.listEvents({
        category: categoryFilter || undefined,
        time_filter: timeFilter || undefined,
        search: eventSearch || undefined,
      }),
  });

  const { data: liveEvents = [] } = useQuery<CampusEventItem[]>({
    queryKey: ['admin', 'events', 'live'],
    queryFn: () => eventsApi.getLiveEvents(),
    refetchInterval: 30_000,
  });

  const { data: clubs = [] } = useQuery<ClubItem[]>({
    queryKey: ['admin', 'clubs'],
    queryFn: () => eventsApi.listClubs(),
  });

  const { data: capabilities = [], isLoading: capsLoading, isError: capsError } = useQuery<CoordinatorCapabilityItem[]>({
    queryKey: ['admin', 'capabilities'],
    queryFn: () => eventsApi.listCapabilities(),
  });

  const { data: rooms = [] } = useQuery<RoomResponse[]>({
    queryKey: ['admin', 'rooms'],
    queryFn: () => roomsApi.getAll(),
  });

  const { data: users = [] } = useQuery<UserAdminItem[]>({
    queryKey: ['admin', 'users'],
    queryFn: () => usersApi.getAll(),
  });

  // Pending approval events
  const pendingEvents = useMemo(
    () => allEvents.filter((e) => e.status === 'PENDING_APPROVAL'),
    [allEvents]
  );

  // Mutations
  const reviewMutation = useMutation({
    mutationFn: ({
      id,
      action,
      reason,
      notes,
    }: {
      id: number;
      action: 'APPROVE' | 'REJECT';
      reason?: string;
      notes?: string;
    }) => eventsApi.reviewEvent(id, { action, reason, notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'events'] });
      setReviewModalEvent(null);
      setReviewNote('');
    },
  });

  const cancelMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      eventsApi.cancelEvent(id, { reason }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'events'] });
      setCancelModalEvent(null);
      setCancelReason('');
    },
  });

  const clubSaveMutation = useMutation({
    mutationFn: async (payload: typeof clubForm) => {
      if (editingClub) {
        return eventsApi.updateClub(editingClub.id, payload);
      }
      return eventsApi.createClub(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'clubs'] });
      setClubModalOpen(false);
      setEditingClub(null);
      setClubForm({ name: '', code: '', category: 'TECHNICAL', description: '' });
    },
  });

  const assignCapMutation = useMutation({
    mutationFn: (payload: typeof capForm) =>
      eventsApi.assignCapability({
        user_id: payload.user_id,
        capability: payload.capability,
        scope_type: payload.scope_type,
        scope_id: payload.scope_id || null,
        expires_at: payload.expires_at || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'capabilities'] });
      setCapabilityModalOpen(false);
      setCapForm({
        user_id: 0,
        capability: 'EVENT_COORDINATOR',
        scope_type: 'GLOBAL',
        scope_id: undefined,
        expires_at: '',
      });
    },
  });

  const revokeCapMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) =>
      eventsApi.revokeCapability(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'capabilities'] });
      setRevokeModalCap(null);
      setRevokeReason('');
    },
  });

  // Venue check handler
  const handleCheckVenue = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!venueCheckRoomId || !venueCheckStart || !venueCheckEnd) return;
    setVenueChecking(true);
    setVenueCheckError(null);
    try {
      const res = await eventsApi.checkVenueAvailability({
        room_id: venueCheckRoomId,
        start_time: new Date(venueCheckStart).toISOString(),
        end_time: new Date(venueCheckEnd).toISOString(),
      });
      setVenueCheckResult(res);
    } catch (err: unknown) {
      if (isAxiosError(err)) {
        setVenueCheckError(err.response?.data?.detail || 'Venue check failed');
      } else {
        setVenueCheckError('Venue check failed');
      }
    } finally {
      setVenueChecking(false);
    }
  };

  // Event Table Columns
  const eventColumns: Column<CampusEventItem>[] = [
    {
      header: 'Event',
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
      header: 'Schedule & Venue',
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
      header: 'Audience',
      render: (row) => (
        <span className="inline-block px-2 py-0.5 text-xs font-medium rounded-md bg-slate-100 text-slate-700">
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
      render: (row) => (
        <div className="flex items-center gap-1.5 justify-end">
          {row.status === 'PENDING_APPROVAL' && (
            <button
              onClick={() => {
                setReviewModalEvent(row);
                setReviewAction('APPROVE');
              }}
              className="px-2 py-1 text-xs font-semibold rounded bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100"
            >
              Review
            </button>
          )}
          {!['CANCELLED', 'REJECTED', 'COMPLETED'].includes(row.status) && (
            <button
              onClick={() => setCancelModalEvent(row)}
              className="p-1 text-slate-400 hover:text-red-600 rounded"
              title="Cancel Event"
            >
              <Ban size={15} />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Campus Events & Club Coordination"
        subtitle="Oversee university events, validate facility reservations, approve club activities, and manage coordinator capabilities."
        breadcrumbs={[
          { label: 'Dashboard', href: '/admin' },
          { label: 'Events & Clubs' },
        ]}
      />

      {/* KPI Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Total Events"
          value={allEvents.length}
          icon={<Calendar size={20} className="text-primary-600" />}
          sub={`${allEvents.filter((e) => e.status === 'PUBLISHED').length} published`}
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
          label="Pending Approvals"
          value={pendingEvents.length}
          icon={<AlertTriangle size={20} className="text-amber-500" />}
          sub={pendingEvents.length > 0 ? 'Requires action' : 'All clear'}
          variant={pendingEvents.length > 0 ? 'warning' : 'default'}
        />
        <StatCard
          label="Active Clubs"
          value={clubs.filter((c) => c.status === 'ACTIVE').length}
          icon={<Sparkles size={20} className="text-purple-600" />}
          sub={`${clubs.length} total registered`}
          variant="default"
        />
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-200 overflow-x-auto">
        <button
          onClick={() => setActiveTab('events')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap ${
            activeTab === 'events'
              ? 'border-primary-600 text-primary-700 font-semibold'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <Calendar size={16} /> All Events ({allEvents.length})
        </button>
        <button
          onClick={() => setActiveTab('approvals')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap relative ${
            activeTab === 'approvals'
              ? 'border-primary-600 text-primary-700 font-semibold'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <CheckCircle2 size={16} /> Approvals Queue
          {pendingEvents.length > 0 && (
            <span className="ml-1.5 px-2 py-0.5 text-xs font-bold rounded-full bg-amber-500 text-white">
              {pendingEvents.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('clubs')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap ${
            activeTab === 'clubs'
              ? 'border-primary-600 text-primary-700 font-semibold'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <Sparkles size={16} /> Clubs & Organizations ({clubs.length})
        </button>
        <button
          onClick={() => setActiveTab('capabilities')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap ${
            activeTab === 'capabilities'
              ? 'border-primary-600 text-primary-700 font-semibold'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <Shield size={16} /> Coordinator Capabilities ({capabilities.length})
        </button>
        <button
          onClick={() => setActiveTab('venue_check')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap ${
            activeTab === 'venue_check'
              ? 'border-primary-600 text-primary-700 font-semibold'
              : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <Building2 size={16} /> Venue Availability Inspector
        </button>
      </div>

      {/* Tab: All Events */}
      {activeTab === 'events' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3 justify-between items-center bg-white p-3 rounded-xl border border-slate-200">
            <div className="relative w-full sm:w-72">
              <Search
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                type="text"
                placeholder="Search events, workshops..."
                value={eventSearch}
                onChange={(e) => setEventSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div className="flex flex-wrap gap-2 w-full sm:w-auto">
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                className="text-xs px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white text-slate-700"
              >
                <option value="">All Categories</option>
                <option value="ACADEMIC">Academic</option>
                <option value="WORKSHOP">Workshop</option>
                <option value="SEMINAR">Seminar</option>
                <option value="HACKATHON">Hackathon</option>
                <option value="CULTURAL">Cultural</option>
                <option value="SPORTS">Sports</option>
                <option value="CLUB_ACTIVITY">Club Activity</option>
              </select>
              <select
                value={timeFilter}
                onChange={(e) => setTimeFilter(e.target.value)}
                className="text-xs px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white text-slate-700"
              >
                <option value="">All Times</option>
                <option value="TODAY">Today</option>
                <option value="ONGOING">Live / Ongoing</option>
                <option value="UPCOMING">Upcoming</option>
                <option value="PAST">Past</option>
              </select>
            </div>
          </div>

          <DataTable<CampusEventItem>
            columns={eventColumns}
            data={allEvents}
            isLoading={eventsLoading}
            isError={eventsError}
            keyExtractor={(row) => row.id}
            emptyMessage="No campus events found. Events created by faculty coordinators or admins will appear here."
          />
        </div>
      )}

      {/* Tab: Approvals Queue */}
      {activeTab === 'approvals' && (
        <div className="space-y-4">
          {pendingEvents.length === 0 ? (
            <div className="bg-white p-12 rounded-xl border border-slate-200 text-center">
              <CheckCircle2 size={36} className="mx-auto text-emerald-500 mb-2" />
              <h3 className="text-base font-semibold text-slate-900">Approvals Queue Clean</h3>
              <p className="text-sm text-slate-500 mt-1">
                All submitted campus events and club activities have been reviewed.
              </p>
            </div>
          ) : (
            <div className="grid gap-4">
              {pendingEvents.map((ev) => (
                <div
                  key={ev.id}
                  className="bg-white p-5 rounded-xl border border-amber-200 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 text-xs font-semibold rounded bg-amber-100 text-amber-800">
                        {ev.category}
                      </span>
                      {ev.club_name && (
                        <span className="text-xs text-slate-500">Club: {ev.club_name}</span>
                      )}
                      <span className="text-xs text-slate-400">• Version #{ev.version}</span>
                    </div>
                    <h4 className="text-base font-bold text-slate-900">{ev.title}</h4>
                    {ev.description && (
                      <p className="text-sm text-slate-600 line-clamp-2">{ev.description}</p>
                    )}
                    <div className="text-xs text-slate-500 flex flex-wrap gap-x-4 gap-y-1 pt-1">
                      <span>
                        Time:{' '}
                        <strong>
                          {new Date(ev.start_time).toLocaleString()} –{' '}
                          {new Date(ev.end_time).toLocaleTimeString()}
                        </strong>
                      </span>
                      <span>
                        Venue:{' '}
                        <strong>
                          {ev.room_number ? `Room ${ev.room_number}` : ev.venue_name || 'TBA'}
                        </strong>
                      </span>
                      <span>
                        Coordinator: <strong>{ev.coordinator_name || `User #${ev.coordinator_id}`}</strong>
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => {
                        setReviewModalEvent(ev);
                        setReviewAction('REJECT');
                      }}
                      className="px-3 py-2 text-xs font-semibold rounded-lg border border-red-200 text-red-700 bg-red-50 hover:bg-red-100"
                    >
                      Reject
                    </button>
                    <button
                      onClick={() => {
                        setReviewModalEvent(ev);
                        setReviewAction('APPROVE');
                      }}
                      className="px-4 py-2 text-xs font-semibold rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 shadow-xs"
                    >
                      Approve & Publish
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab: Clubs Management */}
      {activeTab === 'clubs' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center bg-white p-3 rounded-xl border border-slate-200">
            <p className="text-xs text-slate-500">
              Manage campus clubs, student chapters, and technical societies.
            </p>
            <button
              onClick={() => {
                setEditingClub(null);
                setClubForm({ name: '', code: '', category: 'TECHNICAL', description: '' });
                setClubModalOpen(true);
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-primary-600 text-white hover:bg-primary-700 shadow-xs"
            >
              <Plus size={14} /> Add Club
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {clubs.map((club) => (
              <div
                key={club.id}
                className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs space-y-3 flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="px-2 py-0.5 text-xs font-semibold rounded bg-purple-50 text-purple-700 border border-purple-200">
                      {club.category}
                    </span>
                    <span
                      className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        club.status === 'ACTIVE'
                          ? 'bg-emerald-50 text-emerald-700'
                          : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      {club.status}
                    </span>
                  </div>
                  <h4 className="text-base font-bold text-slate-900 mt-2">{club.name}</h4>
                  <p className="text-xs font-mono text-slate-400">Code: {club.code}</p>
                  <p className="text-sm text-slate-600 mt-2 line-clamp-3">
                    {club.description || 'No description provided.'}
                  </p>
                </div>
                <div className="flex justify-end pt-2 border-t border-slate-100">
                  <button
                    onClick={() => {
                      setEditingClub(club);
                      setClubForm({
                        name: club.name,
                        code: club.code,
                        category: club.category,
                        description: club.description || '',
                      });
                      setClubModalOpen(true);
                    }}
                    className="text-xs font-semibold text-primary-600 hover:text-primary-800"
                  >
                    Edit Club
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab: Coordinator Capabilities */}
      {activeTab === 'capabilities' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center bg-white p-3 rounded-xl border border-slate-200">
            <p className="text-xs text-slate-500">
              Grant scoped coordinator capabilities to faculty members without modifying global system roles.
            </p>
            <button
              onClick={() => setCapabilityModalOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-primary-600 text-white hover:bg-primary-700 shadow-xs"
            >
              <UserCheck size={14} /> Assign Capability
            </button>
          </div>

          <DataTable<CoordinatorCapabilityItem>
            columns={[
              {
                header: 'User & Role',
                render: (row) => (
                  <div>
                    <div className="font-semibold text-slate-900">
                      {row.user_name || `User #${row.user_id}`}
                    </div>
                    <div className="text-xs text-slate-400">
                      {row.user_email} • {row.user_role}
                    </div>
                  </div>
                ),
              },
              {
                header: 'Capability',
                render: (row) => (
                  <span className="inline-block px-2.5 py-1 text-xs font-bold rounded-md bg-blue-50 text-blue-800 border border-blue-200">
                    {row.capability}
                  </span>
                ),
              },
              {
                header: 'Scope',
                render: (row) => (
                  <div className="text-xs">
                    <span className="font-semibold text-slate-700">{row.scope_type}</span>
                    {row.scope_name && (
                      <span className="text-slate-500"> ({row.scope_name})</span>
                    )}
                  </div>
                ),
              },
              {
                header: 'Status',
                render: (row) => (
                  <span
                    className={`inline-block px-2 py-0.5 text-xs font-semibold rounded-full ${
                      row.is_active
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {row.is_active ? 'ACTIVE' : 'REVOKED'}
                  </span>
                ),
              },
              {
                header: 'Actions',
                align: 'right',
                render: (row) =>
                  row.is_active ? (
                    <button
                      onClick={() => setRevokeModalCap(row)}
                      className="text-xs font-semibold text-red-600 hover:text-red-800"
                    >
                      Revoke
                    </button>
                  ) : (
                    <span className="text-xs text-slate-400">Revoked</span>
                  ),
              },
            ]}
            data={capabilities}
            isLoading={capsLoading}
            isError={capsError}
            keyExtractor={(row) => row.id}
            emptyMessage="No coordinator capabilities assigned yet."
          />
        </div>
      )}

      {/* Tab: Venue Check Inspector */}
      {activeTab === 'venue_check' && (
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-xs space-y-6 max-w-3xl">
          <div>
            <h3 className="text-base font-bold text-slate-900">
              Facility & Venue Availability Inspector
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              Checks 3 authoritative conflict sources: Timetable entries, Resource bookings, and scheduled Campus Events.
            </p>
          </div>

          <form onSubmit={handleCheckVenue} className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Room / Lab</label>
              <select
                required
                value={venueCheckRoomId}
                onChange={(e) => setVenueCheckRoomId(Number(e.target.value))}
                className="w-full text-xs p-2 border border-slate-200 rounded-lg bg-white"
              >
                <option value={0}>Select a room...</option>
                {rooms.map((r: RoomResponse) => (
                  <option key={r.id} value={r.id}>
                    Room {r.room_number} ({r.room_type}, Cap: {r.capacity})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Start Date & Time</label>
              <input
                required
                type="datetime-local"
                value={venueCheckStart}
                onChange={(e) => setVenueCheckStart(e.target.value)}
                className="w-full text-xs p-2 border border-slate-200 rounded-lg"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">End Date & Time</label>
              <input
                required
                type="datetime-local"
                value={venueCheckEnd}
                onChange={(e) => setVenueCheckEnd(e.target.value)}
                className="w-full text-xs p-2 border border-slate-200 rounded-lg"
              />
            </div>

            <div className="md:col-span-3">
              <button
                type="submit"
                disabled={venueChecking || !venueCheckRoomId}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 shadow-xs"
              >
                {venueChecking ? 'Validating Conflicts…' : 'Inspect Availability'}
              </button>
            </div>
          </form>

          {venueCheckError && (
            <div className="p-3 text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg">
              {venueCheckError}
            </div>
          )}

          {venueCheckResult && (
            <div
              className={`p-4 rounded-xl border ${
                venueCheckResult.is_available
                  ? 'bg-emerald-50 border-emerald-200'
                  : 'bg-amber-50 border-amber-200'
              }`}
            >
              <div className="flex items-center gap-2">
                {venueCheckResult.is_available ? (
                  <>
                    <CheckCircle2 size={18} className="text-emerald-600" />
                    <span className="text-sm font-bold text-emerald-900">
                      Venue is Available! No conflicts detected.
                    </span>
                  </>
                ) : (
                  <>
                    <AlertTriangle size={18} className="text-amber-600" />
                    <span className="text-sm font-bold text-amber-900">
                      Venue Conflict Detected ({venueCheckResult.conflicts.length} overlapping schedules)
                    </span>
                  </>
                )}
              </div>

              {!venueCheckResult.is_available && (
                <ul className="mt-3 space-y-2 text-xs text-amber-800">
                  {venueCheckResult.conflicts.map((c, idx) => (
                    <li key={idx} className="bg-white/80 p-2.5 rounded-lg border border-amber-300">
                      <strong>[{c.type}]</strong> {c.reason} ({c.time_window})
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {/* Review Modal */}
      {reviewModalEvent && (
        <FormModal
          isOpen={!!reviewModalEvent}
          title={`${reviewAction === 'APPROVE' ? 'Approve & Publish' : 'Reject'} Event`}
          onClose={() => setReviewModalEvent(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              reviewMutation.mutate({
                id: reviewModalEvent.id,
                action: reviewAction,
                notes: reviewAction === 'APPROVE' ? reviewNote : undefined,
                reason: reviewAction === 'REJECT' ? reviewNote : undefined,
              });
            }}
            className="space-y-4 text-xs"
          >
            <p className="text-slate-600">
              Event: <strong>{reviewModalEvent.title}</strong>
            </p>
            <div>
              <label className="block font-medium text-slate-700 mb-1">
                {reviewAction === 'APPROVE' ? 'Approval Notes (Optional)' : 'Rejection Reason (Required)'}
              </label>
              <textarea
                required={reviewAction === 'REJECT'}
                value={reviewNote}
                onChange={(e) => setReviewNote(e.target.value)}
                placeholder={
                  reviewAction === 'APPROVE'
                    ? 'e.g. Venue verified, approved for all departments'
                    : 'e.g. Incomplete details, venue conflict'
                }
                rows={3}
                className="w-full p-2.5 border border-slate-200 rounded-lg text-xs"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setReviewModalEvent(null)}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={reviewMutation.isPending}
                className="px-4 py-1.5 rounded-lg bg-primary-600 text-white font-semibold"
              >
                {reviewAction === 'APPROVE' ? 'Confirm Approval' : 'Confirm Rejection'}
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
              Are you sure you want to cancel <strong>{cancelModalEvent.title}</strong>? Registered students and faculty will be notified.
            </p>
            <div>
              <label className="block font-medium text-slate-700 mb-1">Reason for Cancellation</label>
              <textarea
                required
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="Reason for cancellation..."
                rows={3}
                className="w-full p-2.5 border border-slate-200 rounded-lg text-xs"
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

      {/* Club Create/Edit Modal */}
      {clubModalOpen && (
        <FormModal
          isOpen={clubModalOpen}
          title={editingClub ? 'Edit Club' : 'Create New Club'}
          onClose={() => setClubModalOpen(false)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              clubSaveMutation.mutate(clubForm);
            }}
            className="space-y-3 text-xs"
          >
            <div>
              <label className="block font-medium text-slate-700 mb-1">Club Name</label>
              <input
                required
                type="text"
                value={clubForm.name}
                onChange={(e) => setClubForm({ ...clubForm, name: e.target.value })}
                placeholder="e.g. Robotics Club"
                className="w-full p-2 border border-slate-200 rounded-lg"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-700 mb-1">Code / Abbreviation</label>
              <input
                required
                type="text"
                value={clubForm.code}
                onChange={(e) => setClubForm({ ...clubForm, code: e.target.value.toUpperCase() })}
                placeholder="e.g. ROBO"
                className="w-full p-2 border border-slate-200 rounded-lg font-mono uppercase"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-700 mb-1">Category</label>
              <select
                value={clubForm.category}
                onChange={(e) => setClubForm({ ...clubForm, category: e.target.value })}
                className="w-full p-2 border border-slate-200 rounded-lg bg-white"
              >
                <option value="TECHNICAL">Technical</option>
                <option value="CULTURAL">Cultural</option>
                <option value="SPORTS">Sports</option>
                <option value="LITERARY">Literary</option>
                <option value="SOCIAL">Social Service</option>
                <option value="SPECIAL_INTEREST">Special Interest</option>
              </select>
            </div>
            <div>
              <label className="block font-medium text-slate-700 mb-1">Description</label>
              <textarea
                value={clubForm.description}
                onChange={(e) => setClubForm({ ...clubForm, description: e.target.value })}
                placeholder="Mission, activities, and membership details..."
                rows={3}
                className="w-full p-2 border border-slate-200 rounded-lg"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setClubModalOpen(false)}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={clubSaveMutation.isPending}
                className="px-4 py-1.5 rounded-lg bg-primary-600 text-white font-semibold"
              >
                {editingClub ? 'Save Changes' : 'Create Club'}
              </button>
            </div>
          </form>
        </FormModal>
      )}

      {/* Assign Capability Modal */}
      {capabilityModalOpen && (
        <FormModal
          isOpen={capabilityModalOpen}
          title="Assign Coordinator Capability"
          onClose={() => setCapabilityModalOpen(false)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              assignCapMutation.mutate(capForm);
            }}
            className="space-y-3 text-xs"
          >
            <div>
              <label className="block font-medium text-slate-700 mb-1">Faculty User</label>
              <select
                required
                value={capForm.user_id}
                onChange={(e) => setCapForm({ ...capForm, user_id: Number(e.target.value) })}
                className="w-full p-2 border border-slate-200 rounded-lg bg-white"
              >
                <option value={0}>Select faculty user...</option>
                {users
                  .filter((u) => u.role === 'FACULTY' || u.role === 'ADMIN')
                  .map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name} ({u.email}) - {u.role}
                    </option>
                  ))}
              </select>
            </div>
            <div>
              <label className="block font-medium text-slate-700 mb-1">Capability</label>
              <select
                value={capForm.capability}
                onChange={(e) => setCapForm({ ...capForm, capability: e.target.value })}
                className="w-full p-2 border border-slate-200 rounded-lg bg-white"
              >
                <option value="EVENT_COORDINATOR">EVENT_COORDINATOR (Create & Manage Events)</option>
                <option value="CLUB_COORDINATOR">CLUB_COORDINATOR (Coordinate Assigned Club)</option>
                <option value="EVENT_DIRECT_PUBLISH">EVENT_DIRECT_PUBLISH (Publish without Admin approval)</option>
              </select>
            </div>
            <div>
              <label className="block font-medium text-slate-700 mb-1">Scope Type</label>
              <select
                value={capForm.scope_type}
                onChange={(e) =>
                  setCapForm({
                    ...capForm,
                    scope_type: e.target.value as 'GLOBAL' | 'CLUB' | 'DEPARTMENT',
                    scope_id: undefined,
                  })
                }
                className="w-full p-2 border border-slate-200 rounded-lg bg-white"
              >
                <option value="GLOBAL">Global (Campus-wide)</option>
                <option value="CLUB">Club Specific</option>
                <option value="DEPARTMENT">Department Specific</option>
              </select>
            </div>
            {capForm.scope_type === 'CLUB' && (
              <div>
                <label className="block font-medium text-slate-700 mb-1">Target Club</label>
                <select
                  required
                  value={capForm.scope_id || 0}
                  onChange={(e) => setCapForm({ ...capForm, scope_id: Number(e.target.value) })}
                  className="w-full p-2 border border-slate-200 rounded-lg bg-white"
                >
                  <option value={0}>Select Club...</option>
                  {clubs.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.code})
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div>
              <label className="block font-medium text-slate-700 mb-1">Expires At (Optional)</label>
              <input
                type="datetime-local"
                value={capForm.expires_at}
                onChange={(e) => setCapForm({ ...capForm, expires_at: e.target.value })}
                className="w-full p-2 border border-slate-200 rounded-lg"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setCapabilityModalOpen(false)}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={assignCapMutation.isPending || !capForm.user_id}
                className="px-4 py-1.5 rounded-lg bg-primary-600 text-white font-semibold disabled:opacity-50"
              >
                Assign Capability
              </button>
            </div>
          </form>
        </FormModal>
      )}

      {/* Revoke Capability Confirm */}
      {revokeModalCap && (
        <FormModal
          isOpen={!!revokeModalCap}
          title="Revoke Coordinator Capability"
          onClose={() => setRevokeModalCap(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              revokeCapMutation.mutate({ id: revokeModalCap.id, reason: revokeReason });
            }}
            className="space-y-3 text-xs"
          >
            <p className="text-slate-600">
              Revoke <strong>{revokeModalCap.capability}</strong> from{' '}
              <strong>{revokeModalCap.user_name || `User #${revokeModalCap.user_id}`}</strong>?
            </p>
            <div>
              <label className="block font-medium text-slate-700 mb-1">Revocation Reason</label>
              <textarea
                value={revokeReason}
                onChange={(e) => setRevokeReason(e.target.value)}
                placeholder="Reason for revoking capability..."
                rows={2}
                className="w-full p-2 border border-slate-200 rounded-lg text-xs"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setRevokeModalCap(null)}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600"
              >
                Back
              </button>
              <button
                type="submit"
                disabled={revokeCapMutation.isPending}
                className="px-4 py-1.5 rounded-lg bg-red-600 text-white font-semibold"
              >
                Revoke Capability
              </button>
            </div>
          </form>
        </FormModal>
      )}
    </div>
  );
}
