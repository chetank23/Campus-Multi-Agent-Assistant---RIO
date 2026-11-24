/**
 * pages/student/StudentEventsPage.tsx
 * -----------------------------------
 * Live & Ongoing Campus Events & Extracurricular Dashboard for Students.
 * Shows only verified, published, or ongoing events matching student audience.
 */

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Sparkles,
  Calendar,
  Clock,
  Radio,
  Search,
  Users,
  MapPin,
  ChevronRight,
  CheckCircle2,
  UserPlus,
  UserMinus,
} from 'lucide-react';

import {
  PageHeader,
  StatCard,
  StatusBadge,
  type StatusVariant,
  LoadingState,
  FormModal,
} from '@/components/common';
import { useToast } from '@/context/useToast';

import {
  eventsApi,
  type CampusEventItem,
  type EventRegistrationItem,
  type ClubMembershipItem,
  type ClubItem,
} from '@/api/events';

const STATUS_VARIANT_MAP: Record<string, StatusVariant> = {
  PUBLISHED: 'success',
  ONGOING: 'primary',
  COMPLETED: 'neutral',
};

export function StudentEventsPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [activeTab, setActiveTab] = useState<'ongoing' | 'today' | 'upcoming' | 'clubs' | 'my_events' | 'all'>('ongoing');
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedEvent, setSelectedEvent] = useState<CampusEventItem | null>(null);

  // Queries
  const { data: events = [], isLoading } = useQuery<CampusEventItem[]>({
    queryKey: ['student', 'events', categoryFilter, searchQuery],
    queryFn: () =>
      eventsApi.listEvents({
        category: categoryFilter || undefined,
        search: searchQuery || undefined,
      }),
  });

  const { data: liveEvents = [] } = useQuery<CampusEventItem[]>({
    queryKey: ['student', 'events', 'live'],
    queryFn: () => eventsApi.getLiveEvents(),
    refetchInterval: 30_000,
  });

  const { data: myRegistrations = [] } = useQuery<EventRegistrationItem[]>({
    queryKey: ['student', 'event-registrations'],
    queryFn: () => eventsApi.getMyEventRegistrations(),
    refetchInterval: 60_000,
  });

  const { data: myClubs = [] } = useQuery<ClubMembershipItem[]>({
    queryKey: ['student', 'club-memberships'],
    queryFn: () => eventsApi.getMyClubMemberships(),
    refetchInterval: 60_000,
  });

  const { data: allClubs = [], isLoading: isLoadingClubs } = useQuery<ClubItem[]>({
    queryKey: ['student', 'all-clubs'],
    queryFn: () => eventsApi.listClubs('ACTIVE'),
  });

  const registeredEventIds = useMemo(
    () => new Set(myRegistrations.map((r) => r.event_id)),
    [myRegistrations]
  );

  const joinedClubIds = useMemo(
    () => new Set(myClubs.map((c) => c.club_id)),
    [myClubs]
  );

  // Mutations
  const registerEventMutation = useMutation({
    mutationFn: (eventId: number) => eventsApi.registerForEvent(eventId),
    onSuccess: () => {
      toast.success('Successfully registered for the event!');
      queryClient.invalidateQueries({ queryKey: ['student', 'event-registrations'] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Failed to register for event.');
    },
  });

  const cancelEventMutation = useMutation({
    mutationFn: (eventId: number) => eventsApi.cancelEventRegistration(eventId),
    onSuccess: () => {
      toast.success('Event registration cancelled.');
      queryClient.invalidateQueries({ queryKey: ['student', 'event-registrations'] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Failed to cancel registration.');
    },
  });

  const joinClubMutation = useMutation({
    mutationFn: (clubId: number) => eventsApi.joinClub(clubId),
    onSuccess: () => {
      toast.success('Joined club successfully!');
      queryClient.invalidateQueries({ queryKey: ['student', 'club-memberships'] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Failed to join club.');
    },
  });

  const leaveClubMutation = useMutation({
    mutationFn: (clubId: number) => eventsApi.leaveClub(clubId),
    onSuccess: () => {
      toast.success('Left club.');
      queryClient.invalidateQueries({ queryKey: ['student', 'club-memberships'] });
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Failed to leave club.');
    },
  });

  // Filtered views
  const filteredEvents: CampusEventItem[] = useMemo((): CampusEventItem[] => {
    const now = new Date();
    const todayStr = now.toISOString().slice(0, 10);
    const eventList: CampusEventItem[] = Array.isArray(events) ? events : [];
    const liveList: CampusEventItem[] = Array.isArray(liveEvents) ? liveEvents : (((liveEvents as any)?.ongoing_events as CampusEventItem[]) || []);

    switch (activeTab) {
      case 'ongoing':
        return liveList;
      case 'today':
        return eventList.filter((e) => e.start_time?.startsWith(todayStr));
      case 'upcoming':
        return eventList.filter((e) => new Date(e.start_time) > now);
      case 'my_events':
        return eventList.filter((e) => registeredEventIds.has(e.id));
      case 'clubs':
        return eventList.filter((e) => e.category === 'CLUB_ACTIVITY' || e.club_id != null);
      default:
        return eventList;
    }
  }, [events, liveEvents, activeTab, registeredEventIds]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Live & Ongoing Campus Events"
        subtitle="Discover hackathons, technical workshops, club meetups, and campus festivals happening across the university."
        breadcrumbs={[
          { label: 'Dashboard', href: '/student' },
          { label: 'Events & Activities' },
        ]}
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Live Now"
          value={liveEvents.length}
          icon={<Radio size={20} className="text-emerald-600 animate-pulse" />}
          sub={liveEvents.length > 0 ? 'Happening on campus' : 'No events in progress'}
          variant={liveEvents.length > 0 ? 'success' : 'default'}
        />
        <StatCard
          label="Today's Events"
          value={events.filter((e) => e.start_time.startsWith(new Date().toISOString().slice(0, 10))).length}
          icon={<Calendar size={20} className="text-primary-600" />}
          sub="Scheduled today"
          variant="primary"
        />
        <StatCard
          label="Upcoming Workshops"
          value={events.filter((e) => e.category === 'WORKSHOP' || e.category === 'HACKATHON').length}
          icon={<Sparkles size={20} className="text-purple-600" />}
          sub="Skill & Tech"
          variant="default"
        />
        <StatCard
          label="Club Activities"
          value={events.filter((e) => e.category === 'CLUB_ACTIVITY' || e.club_id != null).length}
          icon={<Users size={20} className="text-blue-600" />}
          sub="Student chapters"
          variant="default"
        />
      </div>

      {/* Navigation Tabs & Controls */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row gap-3 justify-between items-center bg-white p-3 rounded-xl border border-slate-200">
          <div className="flex border-b border-slate-200 sm:border-0 w-full sm:w-auto overflow-x-auto">
            <button
              onClick={() => setActiveTab('ongoing')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg whitespace-nowrap ${
                activeTab === 'ongoing'
                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              Live / Ongoing ({liveEvents.length})
            </button>
            <button
              onClick={() => setActiveTab('today')}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap ${
                activeTab === 'today'
                  ? 'bg-primary-50 text-primary-700 font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Today
            </button>
            <button
              onClick={() => setActiveTab('upcoming')}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap ${
                activeTab === 'upcoming'
                  ? 'bg-primary-50 text-primary-700 font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Upcoming
            </button>
            <button
              onClick={() => setActiveTab('clubs')}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap ${
                activeTab === 'clubs'
                  ? 'bg-primary-50 text-primary-700 font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Club Activities
            </button>
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
              onClick={() => setActiveTab('my_events')}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap ${
                activeTab === 'my_events'
                  ? 'bg-purple-50 text-purple-700 font-bold border border-purple-200'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              My Registered ({myRegistrations.length})
            </button>
          </div>

          <div className="flex gap-2 w-full sm:w-auto">
            <div className="relative w-full sm:w-56">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search events..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1 text-xs border border-slate-200 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="text-xs px-2.5 py-1 border border-slate-200 rounded-lg bg-white text-slate-700"
            >
              <option value="">All Categories</option>
              <option value="WORKSHOP">Workshops</option>
              <option value="HACKATHON">Hackathons</option>
              <option value="SEMINAR">Seminars</option>
              <option value="CLUB_ACTIVITY">Club Activities</option>
              <option value="CULTURAL">Cultural</option>
              <option value="SPORTS">Sports</option>
              <option value="ACADEMIC">Academic</option>
            </select>
          </div>
        </div>

        {/* Campus Clubs Directory when Clubs tab is active */}
        {activeTab === 'clubs' && (
          <div className="mb-6 space-y-3">
            <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
              <Users size={16} className="text-purple-600" />
              Campus Clubs & Student Organizations
            </h3>
            {isLoadingClubs ? (
              <LoadingState message="Loading clubs..." />
            ) : allClubs.length === 0 ? (
              <p className="text-xs text-slate-400">No active clubs registered.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {allClubs.map((club) => {
                  const isMember = joinedClubIds.has(club.id);
                  return (
                    <div
                      key={club.id}
                      className="p-4 bg-purple-50/50 border border-purple-100 rounded-xl flex flex-col justify-between gap-3 shadow-xs"
                    >
                      <div>
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[11px] font-bold text-purple-700 bg-purple-100 px-1.5 py-0.5 rounded">
                            {club.code}
                          </span>
                          {isMember && (
                            <span className="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 flex items-center gap-1">
                              <CheckCircle2 size={11} /> Joined
                            </span>
                          )}
                        </div>
                        <h4 className="font-bold text-slate-900 text-sm mt-1">{club.name}</h4>
                        {club.description && (
                          <p className="text-xs text-slate-600 mt-1 line-clamp-2">{club.description}</p>
                        )}
                      </div>

                      <div className="pt-2 border-t border-purple-100 flex justify-end">
                        {isMember ? (
                          <button
                            type="button"
                            disabled={leaveClubMutation.isPending}
                            onClick={(e) => {
                              e.stopPropagation();
                              leaveClubMutation.mutate(club.id);
                            }}
                            className="px-3 py-1 bg-white hover:bg-rose-50 text-rose-600 border border-rose-200 rounded-lg text-xs font-semibold inline-flex items-center gap-1"
                          >
                            <UserMinus size={12} />
                            Leave Club
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={joinClubMutation.isPending}
                            onClick={(e) => {
                              e.stopPropagation();
                              joinClubMutation.mutate(club.id);
                            }}
                            className="px-3 py-1 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1 shadow-xs"
                          >
                            <UserPlus size={12} />
                            Join Club
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Events Cards Grid */}
        {isLoading ? (
          <div className="py-12 bg-white rounded-xl border border-slate-200">
            <LoadingState message="Fetching campus events & club schedule…" />
          </div>
        ) : filteredEvents.length === 0 ? (
          <div className="bg-white p-12 rounded-xl border border-slate-200 text-center">
            <Calendar size={36} className="mx-auto text-slate-300 mb-2" />
            <h3 className="text-base font-semibold text-slate-900">No events found</h3>
            <p className="text-xs text-slate-500 mt-1">
              {activeTab === 'ongoing'
                ? 'There are no live campus events currently in session. Check Upcoming for scheduled activities!'
                : activeTab === 'my_events'
                ? 'You have not registered for any upcoming events yet.'
                : 'No published events match your filter criteria.'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredEvents.map((ev) => {
              const isLive = ev.status === 'ONGOING';
              return (
                <div
                  key={ev.id}
                  className={`bg-white rounded-xl border p-5 shadow-xs flex flex-col justify-between transition-all hover:shadow-md cursor-pointer ${
                    isLive ? 'border-emerald-300 ring-2 ring-emerald-100' : 'border-slate-200'
                  }`}
                  onClick={() => setSelectedEvent(ev)}
                >
                  <div className="space-y-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="px-2 py-0.5 text-xs font-semibold rounded bg-primary-50 text-primary-700 border border-primary-200">
                        {ev.category}
                      </span>
                      <div className="flex items-center gap-1.5">
                        {registeredEventIds.has(ev.id) && (
                          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                            <CheckCircle2 size={11} className="text-emerald-600" /> Registered
                          </span>
                        )}
                        {isLive ? (
                          <span className="flex items-center gap-1 px-2 py-0.5 text-xs font-bold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 animate-pulse">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            LIVE NOW
                          </span>
                        ) : (
                          <span className="text-xs font-medium text-slate-500">
                            {new Date(ev.start_time).toLocaleDateString(undefined, {
                              month: 'short',
                              day: 'numeric',
                            })}
                          </span>
                        )}
                      </div>
                    </div>

                    <h4 className="text-base font-bold text-slate-900 leading-snug hover:text-primary-600">
                      {ev.title}
                    </h4>

                    {ev.description && (
                      <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                        {ev.description}
                      </p>
                    )}

                    <div className="pt-2 border-t border-slate-100 space-y-1.5 text-xs text-slate-500">
                      <div className="flex items-center gap-2">
                        <Clock size={13} className="text-slate-400 shrink-0" />
                        <span>
                          {new Date(ev.start_time).toLocaleTimeString(undefined, {
                            timeStyle: 'short',
                          })}{' '}
                          –{' '}
                          {new Date(ev.end_time).toLocaleTimeString(undefined, {
                            timeStyle: 'short',
                          })}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <MapPin size={13} className="text-slate-400 shrink-0" />
                        <span className="font-medium text-slate-700">
                          {ev.room_number ? `Room ${ev.room_number}` : ev.venue_name || 'Campus Venue'}
                        </span>
                      </div>
                      {ev.club_name && (
                        <div className="flex items-center gap-2 text-purple-700 font-medium">
                          <Users size={13} className="shrink-0" />
                          <span>Organized by {ev.club_name}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs font-semibold text-primary-600">
                    <span>View Details</span>
                    <ChevronRight size={14} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Event Details Modal */}
      {selectedEvent && (
        <FormModal
          isOpen={!!selectedEvent}
          title={selectedEvent.title}
          onClose={() => setSelectedEvent(null)}
        >
          <div className="space-y-4 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-2 py-0.5 text-xs font-semibold rounded bg-primary-50 text-primary-700 border border-primary-200">
                {selectedEvent.category}
              </span>
              <StatusBadge
                status={selectedEvent.status}
                variant={STATUS_VARIANT_MAP[selectedEvent.status] || 'neutral'}
              />
              <span className="px-2 py-0.5 text-xs rounded bg-slate-100 text-slate-700">
                Audience: {selectedEvent.target_audience}
              </span>
            </div>

            {selectedEvent.description && (
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-slate-700 whitespace-pre-wrap leading-relaxed">
                {selectedEvent.description}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 p-3 bg-white border border-slate-200 rounded-lg">
              <div>
                <span className="text-slate-400 block">Date</span>
                <span className="font-semibold text-slate-800">
                  {new Date(selectedEvent.start_time).toLocaleDateString(undefined, {
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block">Time</span>
                <span className="font-semibold text-slate-800">
                  {new Date(selectedEvent.start_time).toLocaleTimeString(undefined, {
                    timeStyle: 'short',
                  })}{' '}
                  –{' '}
                  {new Date(selectedEvent.end_time).toLocaleTimeString(undefined, {
                    timeStyle: 'short',
                  })}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block">Venue</span>
                <span className="font-semibold text-slate-800">
                  {selectedEvent.room_number ? `Room ${selectedEvent.room_number}` : selectedEvent.venue_name || 'TBA'}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block">Organized By</span>
                <span className="font-semibold text-slate-800">
                  {selectedEvent.club_name || selectedEvent.coordinator_name || 'University'}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-slate-100">
              <div>
                {registeredEventIds.has(selectedEvent.id) ? (
                  <button
                    type="button"
                    disabled={cancelEventMutation.isPending}
                    onClick={() => cancelEventMutation.mutate(selectedEvent.id)}
                    className="px-4 py-1.5 rounded-lg bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-200 font-semibold inline-flex items-center gap-1.5 text-xs"
                  >
                    <UserMinus size={13} />
                    {cancelEventMutation.isPending ? 'Cancelling...' : 'Cancel Registration'}
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={registerEventMutation.isPending}
                    onClick={() => registerEventMutation.mutate(selectedEvent.id)}
                    className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold inline-flex items-center gap-1.5 shadow-xs text-xs"
                  >
                    <UserPlus size={13} />
                    {registerEventMutation.isPending ? 'Registering...' : 'Register for Event'}
                  </button>
                )}
              </div>
              <button
                type="button"
                onClick={() => setSelectedEvent(null)}
                className="px-4 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </FormModal>
      )}
    </div>
  );
}
