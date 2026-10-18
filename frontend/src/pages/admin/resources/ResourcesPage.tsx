/**
 * pages/admin/resources/ResourcesPage.tsx
 * -----------------------------------------
 * Resource Allocation Engine & Administration Page.
 *
 * Capabilities:
 *  1. Inventory: Full CRUD, search, type/status filter, capacity checks.
 *  2. Booking Management: Pending request review, conflict alerts, approve/reject/cancel.
 *  3. Live Availability & Conflict Inspector with alternative resource recommendations.
 */

import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Boxes,
  CalendarCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Search,
  Filter,
  Plus,
  Edit2,
  Trash2,
  Calendar,
  Building,
  Users,
  Tv,
  Microscope,
  Info,
  RefreshCw,
  ArrowRight,
} from 'lucide-react';
import { isAxiosError } from 'axios';

import {
  PageHeader,
  StatCard,
  DataTable,
  type Column,
  FormModal,
  ConfirmDialog,
  StatusBadge,
  type StatusVariant,
} from '@/components/common';

import {
  resourcesApi,
  type ResourceResponse,
  type ResourceBookingResponse,
  type ResourceType,
  type ResourceStatus,
  type AlternativeResource,
  type ConflictDetail,
} from '@/api/resources';

const RESOURCE_TYPES: { label: string; value: ResourceType; icon: React.ElementType }[] = [
  { label: 'Laboratory', value: 'LAB', icon: Microscope },
  { label: 'Seminar Hall', value: 'SEMINAR_HALL', icon: Users },
  { label: 'Auditorium', value: 'AUDITORIUM', icon: Building },
  { label: 'Projector', value: 'PROJECTOR', icon: Tv },
  { label: 'Shared Equipment', value: 'EQUIPMENT', icon: Boxes },
];

export function ResourcesPage() {
  const queryClient = useQueryClient();

  // Active View Tab
  const [activeTab, setActiveTab] = useState<'inventory' | 'bookings' | 'availability'>('inventory');

  // Inventory State
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [isResourceModalOpen, setIsResourceModalOpen] = useState(false);
  const [selectedResource, setSelectedResource] = useState<ResourceResponse | null>(null);
  const [resourceToDelete, setResourceToDelete] = useState<ResourceResponse | null>(null);

  // Resource Form Fields
  const [formName, setFormName] = useState('');
  const [formType, setFormType] = useState<ResourceType>('LAB');
  const [formLocation, setFormLocation] = useState('');
  const [formCapacity, setFormCapacity] = useState<number | ''>('');
  const [formStatus, setFormStatus] = useState<ResourceStatus>('ACTIVE');
  const [formError, setFormError] = useState<string | null>(null);

  // Bookings State
  const [bookingStatusFilter, setBookingStatusFilter] = useState<string>('ALL');
  const [rejectionModalBooking, setRejectionModalBooking] = useState<ResourceBookingResponse | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [cancelModalBooking, setCancelModalBooking] = useState<ResourceBookingResponse | null>(null);
  const [cancelReason, setCancelReason] = useState('');
  const [conflictModalData, setConflictModalData] = useState<{
    message: string;
    conflicts: ConflictDetail[];
    alternatives: AlternativeResource[];
  } | null>(null);

  // Availability Inspector State
  const [inspectResourceId, setInspectResourceId] = useState<number | ''>('');
  const [inspectDate, setInspectDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [inspectStartTime, setInspectStartTime] = useState<string>('10:00:00');
  const [inspectEndTime, setInspectEndTime] = useState<string>('12:00:00');
  const [availabilityResult, setAvailabilityResult] = useState<{
    available: boolean;
    conflicts: ConflictDetail[];
    alternatives: AlternativeResource[];
  } | null>(null);
  const [isCheckingAvailability, setIsCheckingAvailability] = useState(false);
  const [inspectError, setInspectError] = useState<string | null>(null);

  // ── Queries ─────────────────────────────────────────────────────────────────

  const {
    data: resources = [],
    isLoading: isLoadingResources,
    isError: isErrorResources,
    error: resourcesError,
    refetch: refetchResources,
  } = useQuery({
    queryKey: ['resources'],
    queryFn: () => resourcesApi.getAll(),
  });

  const {
    data: bookings = [],
    isLoading: isLoadingBookings,
    isError: isErrorBookings,
    error: bookingsError,
    refetch: refetchBookings,
  } = useQuery({
    queryKey: ['resources-bookings'],
    queryFn: () => resourcesApi.getBookings(),
  });

  // ── Mutations ───────────────────────────────────────────────────────────────

  const createResourceMutation = useMutation({
    mutationFn: resourcesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resources'] });
      closeResourceModal();
    },
    onError: (err: unknown) => {
      if (isAxiosError(err)) {
        setFormError(err.response?.data?.detail || 'Failed to create resource.');
      } else {
        setFormError('Failed to create resource.');
      }
    },
  });

  const updateResourceMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ResourceResponse> }) =>
      resourcesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resources'] });
      closeResourceModal();
    },
    onError: (err: unknown) => {
      if (isAxiosError(err)) {
        setFormError(err.response?.data?.detail || 'Failed to update resource.');
      } else {
        setFormError('Failed to update resource.');
      }
    },
  });

  const deleteResourceMutation = useMutation({
    mutationFn: (id: number) => resourcesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resources'] });
      setResourceToDelete(null);
    },
    onError: (err: unknown) => {
      if (isAxiosError(err)) {
        alert(err.response?.data?.detail || 'Failed to deactivate or delete resource.');
      } else {
        alert('Failed to delete resource.');
      }
      setResourceToDelete(null);
    },
  });

  const approveBookingMutation = useMutation({
    mutationFn: (id: number) => resourcesApi.approveBooking(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resources-bookings'] });
    },
    onError: (err: unknown) => {
      if (isAxiosError(err) && err.response?.status === 409) {
        const detail = err.response.data?.detail;
        if (typeof detail === 'object' && detail !== null) {
          setConflictModalData({
            message: detail.message || 'Booking conflict detected.',
            conflicts: detail.conflicts || [],
            alternatives: detail.alternatives || [],
          });
        } else {
          alert(detail || 'Cannot approve: booking conflict exists.');
        }
      } else if (isAxiosError(err)) {
        alert(err.response?.data?.detail || 'Failed to approve booking.');
      } else {
        alert('Failed to approve booking.');
      }
    },
  });

  const rejectBookingMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      resourcesApi.rejectBooking(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resources-bookings'] });
      setRejectionModalBooking(null);
      setRejectionReason('');
    },
    onError: (err: unknown) => {
      alert(isAxiosError(err) ? err.response?.data?.detail || 'Rejection failed.' : 'Rejection failed.');
    },
  });

  const cancelBookingMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      resourcesApi.cancelBooking(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resources-bookings'] });
      setCancelModalBooking(null);
      setCancelReason('');
    },
    onError: (err: unknown) => {
      alert(isAxiosError(err) ? err.response?.data?.detail || 'Cancellation failed.' : 'Cancellation failed.');
    },
  });

  // ── Helper Handlers ─────────────────────────────────────────────────────────

  const openCreateModal = () => {
    setSelectedResource(null);
    setFormName('');
    setFormType('LAB');
    setFormLocation('');
    setFormCapacity('');
    setFormStatus('ACTIVE');
    setFormError(null);
    setIsResourceModalOpen(true);
  };

  const openEditModal = (resource: ResourceResponse) => {
    setSelectedResource(resource);
    setFormName(resource.name);
    setFormType(resource.resource_type);
    setFormLocation(resource.location || '');
    setFormCapacity(resource.capacity ?? '');
    setFormStatus(resource.status);
    setFormError(null);
    setIsResourceModalOpen(true);
  };

  const closeResourceModal = () => {
    setIsResourceModalOpen(false);
    setSelectedResource(null);
    setFormError(null);
  };

  const handleSaveResource = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName.trim()) {
      setFormError('Resource name is required.');
      return;
    }

    const payload = {
      name: formName.trim(),
      resource_type: formType,
      location: formLocation.trim() || null,
      capacity: formCapacity !== '' ? Number(formCapacity) : null,
      status: formStatus,
    };

    if (selectedResource) {
      updateResourceMutation.mutate({ id: selectedResource.id, data: payload });
    } else {
      createResourceMutation.mutate(payload);
    }
  };

  const handleRunAvailabilityCheck = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inspectResourceId) {
      setInspectError('Please select a resource to inspect.');
      return;
    }

    setInspectError(null);
    setIsCheckingAvailability(true);
    setAvailabilityResult(null);

    try {
      const res = await resourcesApi.checkAvailability({
        resource_id: Number(inspectResourceId),
        date: inspectDate,
        start_time: inspectStartTime.length === 5 ? `${inspectStartTime}:00` : inspectStartTime,
        end_time: inspectEndTime.length === 5 ? `${inspectEndTime}:00` : inspectEndTime,
      });
      setAvailabilityResult({
        available: res.available,
        conflicts: res.conflicts,
        alternatives: res.alternatives,
      });
    } catch (err: unknown) {
      if (isAxiosError(err)) {
        setInspectError(err.response?.data?.detail || 'Availability check failed.');
      } else {
        setInspectError('Availability check failed.');
      }
    } finally {
      setIsCheckingAvailability(false);
    }
  };

  // ── Filtered Datasets ───────────────────────────────────────────────────────

  const filteredResources = useMemo(() => {
    return resources.filter((r) => {
      const matchesSearch =
        !searchTerm.trim() ||
        r.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (r.location && r.location.toLowerCase().includes(searchTerm.toLowerCase()));

      const matchesType = typeFilter === 'ALL' || r.resource_type === typeFilter;
      const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;

      return matchesSearch && matchesType && matchesStatus;
    });
  }, [resources, searchTerm, typeFilter, statusFilter]);

  const filteredBookings = useMemo(() => {
    return bookings.filter((b) => {
      if (bookingStatusFilter === 'ALL') return true;
      return b.status === bookingStatusFilter;
    });
  }, [bookings, bookingStatusFilter]);

  // Statistics
  const stats = useMemo(() => {
    const totalRes = resources.length;
    const activeRes = resources.filter((r) => r.status === 'ACTIVE').length;
    const pendingBks = bookings.filter((b) => b.status === 'PENDING').length;
    const approvedBks = bookings.filter((b) => b.status === 'APPROVED').length;
    return { totalRes, activeRes, pendingBks, approvedBks };
  }, [resources, bookings]);

  // ── Columns ─────────────────────────────────────────────────────────────────

  const resourceColumns: Column<ResourceResponse>[] = [
    {
      header: 'ID',
      accessor: 'id',
      render: (r) => <span className="font-tabular text-slate-500 font-medium">#{r.id}</span>,
    },
    {
      header: 'Resource Name',
      accessor: 'name',
      render: (r) => {
        const typeInfo = RESOURCE_TYPES.find((t) => t.value === r.resource_type);
        const IconComponent = typeInfo ? typeInfo.icon : Boxes;
        return (
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center flex-shrink-0">
              <IconComponent className="w-4 h-4" />
            </div>
            <div>
              <div className="font-medium text-slate-900">{r.name}</div>
              <div className="text-xs text-slate-500">{typeInfo?.label || r.resource_type}</div>
            </div>
          </div>
        );
      },
    },
    {
      header: 'Location / Room',
      accessor: 'location',
      render: (r) => r.location || <span className="text-slate-400 italic">Unspecified</span>,
    },
    {
      header: 'Capacity',
      accessor: 'capacity',
      render: (r) =>
        r.capacity ? (
          <span className="font-tabular text-slate-700">{r.capacity}</span>
        ) : (
          <span className="text-slate-400">—</span>
        ),
    },
    {
      header: 'Status',
      accessor: 'status',
      render: (r) => {
        const variant: StatusVariant =
          r.status === 'ACTIVE' ? 'success' : r.status === 'MAINTENANCE' ? 'warning' : 'neutral';
        return <StatusBadge variant={variant} label={r.status} />;
      },
    },
    {
      header: 'Actions',
      accessor: 'id',
      render: (r) => (
        <div className="flex items-center gap-1.5 justify-end">
          <button
            onClick={() => openEditModal(r)}
            className="p-1.5 text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"
            title="Edit Resource"
          >
            <Edit2 className="w-4 h-4" />
          </button>
          <button
            onClick={() => setResourceToDelete(r)}
            className="p-1.5 text-slate-600 hover:text-rose-600 hover:bg-rose-50 rounded transition-colors"
            title="Deactivate / Delete Resource"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      ),
    },
  ];

  const bookingColumns: Column<ResourceBookingResponse>[] = [
    {
      header: 'ID',
      accessor: 'id',
      render: (b) => <span className="font-tabular text-slate-500 font-medium">#{b.id}</span>,
    },
    {
      header: 'Resource',
      accessor: 'resource_name',
      render: (b) => (
        <div>
          <div className="font-medium text-slate-900">{b.resource_name || `Resource #${b.resource_id}`}</div>
          <div className="text-xs text-slate-500">
            {b.resource_type} {b.resource_location ? `• ${b.resource_location}` : ''}
          </div>
        </div>
      ),
    },
    {
      header: 'Requester',
      accessor: 'requester_name',
      render: (b) => (
        <div>
          <div className="font-medium text-slate-800">{b.requester_name || `User #${b.requested_by}`}</div>
          <div className="text-xs text-slate-500">{b.requester_email || '—'}</div>
        </div>
      ),
    },
    {
      header: 'Date & Time Slot',
      accessor: 'date',
      render: (b) => (
        <div className="text-sm">
          <div className="font-medium text-slate-900 flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5 text-slate-400" />
            {b.date}
          </div>
          <div className="text-xs text-slate-600 font-tabular flex items-center gap-1.5 mt-0.5">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            {b.start_time.slice(0, 5)} – {b.end_time.slice(0, 5)}
          </div>
        </div>
      ),
    },
    {
      header: 'Purpose',
      accessor: 'purpose',
      render: (b) => (
        <span className="text-slate-700 text-sm max-w-xs truncate block" title={b.purpose || ''}>
          {b.purpose || <span className="text-slate-400 italic">No purpose noted</span>}
        </span>
      ),
    },
    {
      header: 'Status',
      accessor: 'status',
      render: (b) => {
        const variant: StatusVariant =
          b.status === 'APPROVED'
            ? 'success'
            : b.status === 'PENDING'
            ? 'warning'
            : b.status === 'REJECTED'
            ? 'danger'
            : 'neutral';
        return <StatusBadge variant={variant} label={b.status} />;
      },
    },
    {
      header: 'Actions',
      accessor: 'id',
      render: (b) => (
        <div className="flex items-center gap-1.5 justify-end">
          {b.status === 'PENDING' && (
            <>
              <button
                onClick={() => approveBookingMutation.mutate(b.id)}
                disabled={approveBookingMutation.isPending}
                className="px-2.5 py-1 text-xs font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded flex items-center gap-1 transition-colors disabled:opacity-50"
                title="Approve Reservation"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                Approve
              </button>
              <button
                onClick={() => setRejectionModalBooking(b)}
                className="px-2.5 py-1 text-xs font-medium text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded flex items-center gap-1 transition-colors"
                title="Reject Reservation"
              >
                <XCircle className="w-3.5 h-3.5" />
                Reject
              </button>
            </>
          )}

          {b.status === 'APPROVED' && (
            <button
              onClick={() => setCancelModalBooking(b)}
              className="px-2.5 py-1 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-200 rounded flex items-center gap-1 transition-colors"
              title="Cancel Approved Booking"
            >
              Cancel
            </button>
          )}
        </div>
      ),
    },
  ];

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      <PageHeader
        title="Resource Allocation & Administration"
        subtitle="Coordinate campus infrastructure, manage specialized facility inventory, and review booking requests."
        actions={
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                refetchResources();
                refetchBookings();
              }}
              className="p-2 text-slate-600 hover:text-slate-900 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors shadow-sm"
              title="Refresh Data"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={openCreateModal}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg text-sm flex items-center gap-2 shadow-sm transition-colors"
            >
              <Plus className="w-4 h-4" />
              New Resource
            </button>
          </div>
        }
      />

      {/* KPI Stats Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Resources"
          value={stats.totalRes}
          sub="Catalogued facilities & devices"
          icon={<Boxes className="w-5 h-5 text-blue-600" />}
        />
        <StatCard
          label="Active Facilities"
          value={stats.activeRes}
          sub="Available for allocation"
          icon={<CheckCircle2 className="w-5 h-5 text-emerald-600" />}
        />
        <StatCard
          label="Pending Requests"
          value={stats.pendingBks}
          sub="Awaiting administrative review"
          icon={<Clock className="w-5 h-5 text-amber-600" />}
        />
        <StatCard
          label="Approved Bookings"
          value={stats.approvedBks}
          sub="Confirmed campus reservations"
          icon={<CalendarCheck className="w-5 h-5 text-indigo-600" />}
        />
      </div>

      {/* Tab Navigation */}
      <div className="border-b border-slate-200">
        <nav className="flex space-x-6" aria-label="Tabs">
          <button
            onClick={() => setActiveTab('inventory')}
            className={`py-3 px-1 border-b-2 font-medium text-sm flex items-center gap-2 ${
              activeTab === 'inventory'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            <Boxes className="w-4 h-4" />
            Resource Inventory ({resources.length})
          </button>
          <button
            onClick={() => setActiveTab('bookings')}
            className={`py-3 px-1 border-b-2 font-medium text-sm flex items-center gap-2 ${
              activeTab === 'bookings'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            <CalendarCheck className="w-4 h-4" />
            Booking Requests ({bookings.length})
            {stats.pendingBks > 0 && (
              <span className="ml-1 px-1.5 py-0.5 text-xs font-semibold rounded-full bg-amber-100 text-amber-800">
                {stats.pendingBks}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('availability')}
            className={`py-3 px-1 border-b-2 font-medium text-sm flex items-center gap-2 ${
              activeTab === 'availability'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            <Search className="w-4 h-4" />
            Availability & Conflict Inspector
          </button>
        </nav>
      </div>

      {/* ── TAB 1: Resource Inventory ─────────────────────────────────────────── */}
      {activeTab === 'inventory' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white p-3 rounded-lg border border-slate-200 shadow-sm">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search resources by name or location..."
                className="w-full pl-9 pr-3 py-1.5 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 text-sm text-slate-600">
                <Filter className="w-4 h-4 text-slate-400" />
                <span>Type:</span>
              </div>
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="border border-slate-300 rounded-md px-2.5 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="ALL">All Categories</option>
                {RESOURCE_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>

              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="border border-slate-300 rounded-md px-2.5 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="ALL">All Statuses</option>
                <option value="ACTIVE">Active</option>
                <option value="INACTIVE">Inactive</option>
                <option value="MAINTENANCE">Maintenance</option>
              </select>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
            <DataTable
              columns={resourceColumns}
              data={filteredResources}
              isLoading={isLoadingResources}
              isError={isErrorResources}
              error={resourcesError instanceof Error ? resourcesError : null}
              onRefresh={refetchResources}
              keyExtractor={(r) => r.id}
              emptyMessage="No facilities or equipment match your selected filters."
            />
          </div>
        </div>
      )}

      {/* ── TAB 2: Booking Management ─────────────────────────────────────────── */}
      {activeTab === 'bookings' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white p-3 rounded-lg border border-slate-200 shadow-sm">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-slate-700">Filter Status:</span>
              {(['ALL', 'PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'] as const).map((st) => (
                <button
                  key={st}
                  onClick={() => setBookingStatusFilter(st)}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                    bookingStatusFilter === st
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>

            <div className="text-xs text-slate-500">
              Showing {filteredBookings.length} of {bookings.length} reservations
            </div>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
            <DataTable
              columns={bookingColumns}
              data={filteredBookings}
              isLoading={isLoadingBookings}
              isError={isErrorBookings}
              error={bookingsError instanceof Error ? bookingsError : null}
              onRefresh={refetchBookings}
              keyExtractor={(b) => b.id}
              emptyMessage="No reservation requests match the current status filter."
            />
          </div>
        </div>
      )}

      {/* ── TAB 3: Availability & Conflict Inspector ──────────────────────────── */}
      {activeTab === 'availability' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Query Form Panel */}
          <div className="bg-white p-5 rounded-lg border border-slate-200 shadow-sm space-y-4">
            <h3 className="text-base font-semibold text-slate-900 flex items-center gap-2">
              <Search className="w-4 h-4 text-blue-600" />
              Check Facility Availability
            </h3>
            <p className="text-xs text-slate-500">
              Select a target facility and time interval to verify against live timetable schedules and approved reservations.
            </p>

            <form onSubmit={handleRunAvailabilityCheck} className="space-y-4 pt-2">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Target Resource
                </label>
                <select
                  value={inspectResourceId}
                  onChange={(e) => setInspectResourceId(e.target.value ? Number(e.target.value) : '')}
                  required
                  className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">-- Select a Resource --</option>
                  {resources.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} ({r.resource_type}) {r.location ? `• ${r.location}` : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Reservation Date
                </label>
                <input
                  type="date"
                  value={inspectDate}
                  onChange={(e) => setInspectDate(e.target.value)}
                  required
                  className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                    Start Time
                  </label>
                  <input
                    type="time"
                    value={inspectStartTime}
                    onChange={(e) => setInspectStartTime(e.target.value)}
                    required
                    className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                    End Time
                  </label>
                  <input
                    type="time"
                    value={inspectEndTime}
                    onChange={(e) => setInspectEndTime(e.target.value)}
                    required
                    className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              {inspectError && (
                <div className="p-3 bg-rose-50 border border-rose-200 rounded-md text-xs text-rose-700">
                  {inspectError}
                </div>
              )}

              <button
                type="submit"
                disabled={isCheckingAvailability}
                className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm rounded-lg shadow-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isCheckingAvailability ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    Querying Engine...
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4" />
                    Check Availability
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Results Panel */}
          <div className="lg:col-span-2 space-y-4">
            {!availabilityResult ? (
              <div className="bg-slate-50 border border-dashed border-slate-300 rounded-lg p-12 text-center">
                <Info className="w-8 h-8 text-slate-400 mx-auto mb-2" />
                <h4 className="text-sm font-semibold text-slate-700">No Query Executed</h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
                  Choose a resource and time window on the left to run conflict validation and discover available alternatives.
                </p>
              </div>
            ) : availabilityResult.available ? (
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-6 space-y-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center">
                    <CheckCircle2 className="w-6 h-6" />
                  </div>
                  <div>
                    <h4 className="text-base font-semibold text-emerald-900">Facility is Available</h4>
                    <p className="text-xs text-emerald-700">
                      No conflicting reservations or scheduled timetable classes were found on {inspectDate} between{' '}
                      {inspectStartTime} and {inspectEndTime}.
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Conflict Notice */}
                <div className="bg-rose-50 border border-rose-200 rounded-lg p-5 space-y-3">
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <AlertTriangle className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="text-base font-semibold text-rose-900">Resource Conflict Detected</h4>
                      <p className="text-xs text-rose-700 mt-0.5">
                        The requested facility is occupied and cannot be allocated for the specified interval.
                      </p>

                      <div className="mt-3 space-y-2">
                        {availabilityResult.conflicts.map((c, idx) => (
                          <div
                            key={idx}
                            className="bg-white border border-rose-200 rounded p-2.5 text-xs text-slate-800 flex items-center justify-between"
                          >
                            <div>
                              <span className="font-semibold text-rose-600 uppercase tracking-wider mr-2">
                                {c.conflict_type.replace('_', ' ')}
                              </span>
                              <span>{c.description}</span>
                            </div>
                            {c.start_time && c.end_time && (
                              <span className="font-tabular font-medium text-slate-600">
                                {c.start_time.slice(0, 5)} - {c.end_time.slice(0, 5)}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Alternative Suggestions */}
                <div className="bg-white border border-slate-200 rounded-lg p-5 space-y-3 shadow-sm">
                  <h4 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                    <Boxes className="w-4 h-4 text-blue-600" />
                    Compatible Alternative Resources ({availabilityResult.alternatives.length})
                  </h4>
                  <p className="text-xs text-slate-500">
                    The allocation engine identified these unoccupied resources of matching category and capacity for the same interval:
                  </p>

                  {availabilityResult.alternatives.length === 0 ? (
                    <div className="p-4 bg-slate-50 rounded border border-slate-200 text-xs text-slate-500 text-center">
                      No alternate facilities of the same category are currently free for this exact time window.
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden">
                      {availabilityResult.alternatives.map((alt) => (
                        <div
                          key={alt.id}
                          className="p-3 bg-white hover:bg-slate-50 flex items-center justify-between text-sm transition-colors"
                        >
                          <div>
                            <div className="font-medium text-slate-900">{alt.name}</div>
                            <div className="text-xs text-slate-500">
                              {alt.resource_type} {alt.location ? `• ${alt.location}` : ''}{' '}
                              {alt.capacity ? `• Capacity: ${alt.capacity}` : ''}
                            </div>
                          </div>
                          <button
                            onClick={() => {
                              setInspectResourceId(alt.id);
                              setAvailabilityResult(null);
                            }}
                            className="px-3 py-1.5 text-xs font-medium text-blue-600 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 rounded flex items-center gap-1 transition-colors"
                          >
                            Inspect This
                            <ArrowRight className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Resource Create / Edit Modal ─────────────────────────────────────── */}
      <FormModal
        isOpen={isResourceModalOpen}
        onClose={closeResourceModal}
        title={selectedResource ? `Edit Resource #${selectedResource.id}` : 'Create New Resource'}
      >
        <form onSubmit={handleSaveResource} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
              Resource Name *
            </label>
            <input
              type="text"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              placeholder="e.g. Advanced AI Research Lab"
              required
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
              Resource Category *
            </label>
            <select
              value={formType}
              onChange={(e) => setFormType(e.target.value as ResourceType)}
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {RESOURCE_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label} ({t.value})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
              Location / Room Mapping
            </label>
            <input
              type="text"
              value={formLocation}
              onChange={(e) => setFormLocation(e.target.value)}
              placeholder="e.g. LAB-301 or Engineering Block 2nd Floor"
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-[11px] text-slate-400 mt-1">
              If mapped to a classroom or lab room number, published timetable conflicts will be automatically detected.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Capacity
              </label>
              <input
                type="number"
                min="0"
                value={formCapacity}
                onChange={(e) => setFormCapacity(e.target.value ? Number(e.target.value) : '')}
                placeholder="e.g. 60"
                className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Status
              </label>
              <select
                value={formStatus}
                onChange={(e) => setFormStatus(e.target.value as ResourceStatus)}
                className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="ACTIVE">ACTIVE</option>
                <option value="INACTIVE">INACTIVE</option>
                <option value="MAINTENANCE">MAINTENANCE</option>
              </select>
            </div>
          </div>

          {formError && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-md text-xs text-rose-700">
              {formError}
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-200">
            <button
              type="button"
              onClick={closeResourceModal}
              className="px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 rounded-md transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createResourceMutation.isPending || updateResourceMutation.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md shadow-sm transition-colors disabled:opacity-50"
            >
              {selectedResource ? 'Save Changes' : 'Create Resource'}
            </button>
          </div>
        </form>
      </FormModal>

      {/* ── Deactivate / Delete Confirmation Dialog ─────────────────────────── */}
      <ConfirmDialog
        isOpen={Boolean(resourceToDelete)}
        onCancel={() => setResourceToDelete(null)}
        onConfirm={() => resourceToDelete && deleteResourceMutation.mutate(resourceToDelete.id)}
        title="Deactivate or Delete Resource"
        message={`Are you sure you want to deactivate or remove '${resourceToDelete?.name}'? If active or historical bookings depend on this resource, it will be safely deactivated to preserve audit integrity.`}
        confirmLabel="Confirm"
        isDestructive={true}
      />

      {/* ── Reject Booking Modal ────────────────────────────────────────────── */}
      <FormModal
        isOpen={Boolean(rejectionModalBooking)}
        onClose={() => {
          setRejectionModalBooking(null);
          setRejectionReason('');
        }}
        title={`Reject Reservation Request #${rejectionModalBooking?.id}`}
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600">
            Provide an optional reason for rejecting the booking request for{' '}
            <span className="font-semibold text-slate-900">{rejectionModalBooking?.resource_name}</span> requested by{' '}
            <span className="font-semibold text-slate-900">{rejectionModalBooking?.requester_name}</span>.
          </p>

          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
              Rejection Reason
            </label>
            <textarea
              rows={3}
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              placeholder="e.g. Conflicting departmental event or maintenance requirement"
              className="w-full border border-slate-300 rounded-md p-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-200">
            <button
              onClick={() => {
                setRejectionModalBooking(null);
                setRejectionReason('');
              }}
              className="px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 rounded-md"
            >
              Cancel
            </button>
            <button
              onClick={() =>
                rejectionModalBooking &&
                rejectBookingMutation.mutate({
                  id: rejectionModalBooking.id,
                  reason: rejectionReason.trim(),
                })
              }
              disabled={rejectBookingMutation.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-rose-600 hover:bg-rose-700 rounded-md shadow-sm disabled:opacity-50"
            >
              Confirm Rejection
            </button>
          </div>
        </div>
      </FormModal>

      {/* ── Cancel Booking Modal ────────────────────────────────────────────── */}
      <FormModal
        isOpen={Boolean(cancelModalBooking)}
        onClose={() => {
          setCancelModalBooking(null);
          setCancelReason('');
        }}
        title={`Cancel Reservation #${cancelModalBooking?.id}`}
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600">
            Are you sure you want to cancel the reservation for{' '}
            <span className="font-semibold text-slate-900">{cancelModalBooking?.resource_name}</span> on{' '}
            <span className="font-semibold text-slate-900">{cancelModalBooking?.date}</span>?
          </p>

          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
              Cancellation Reason
            </label>
            <textarea
              rows={2}
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              placeholder="e.g. Schedule adjustment or event rescheduled"
              className="w-full border border-slate-300 rounded-md p-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-200">
            <button
              onClick={() => {
                setCancelModalBooking(null);
                setCancelReason('');
              }}
              className="px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 rounded-md"
            >
              Dismiss
            </button>
            <button
              onClick={() =>
                cancelModalBooking &&
                cancelBookingMutation.mutate({
                  id: cancelModalBooking.id,
                  reason: cancelReason.trim(),
                })
              }
              disabled={cancelBookingMutation.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-slate-800 hover:bg-slate-900 rounded-md shadow-sm disabled:opacity-50"
            >
              Confirm Cancellation
            </button>
          </div>
        </div>
      </FormModal>

      {/* ── Conflict & Alternatives Alert Modal ──────────────────────────────── */}
      <FormModal
        isOpen={Boolean(conflictModalData)}
        onClose={() => setConflictModalData(null)}
        title="Reservation Approval Blocked by Conflict"
      >
        <div className="space-y-4">
          <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-sm text-rose-800">
            <div className="font-semibold flex items-center gap-1.5 mb-1">
              <AlertTriangle className="w-4 h-4 text-rose-600" />
              Conflict Explanation
            </div>
            {conflictModalData?.message}
          </div>

          {conflictModalData && conflictModalData.conflicts.length > 0 && (
            <div className="space-y-2">
              <h5 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">Specific Overlaps:</h5>
              <div className="space-y-1.5">
                {conflictModalData.conflicts.map((c, i) => (
                  <div key={i} className="text-xs bg-slate-50 p-2.5 rounded border border-slate-200 text-slate-700">
                    <span className="font-semibold text-slate-900 mr-2">[{c.conflict_type}]</span>
                    {c.description}
                  </div>
                ))}
              </div>
            </div>
          )}

          {conflictModalData && conflictModalData.alternatives.length > 0 && (
            <div className="space-y-2 pt-2 border-t border-slate-200">
              <h5 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                Recommended Alternative Resources:
              </h5>
              <div className="divide-y divide-slate-100 border border-slate-200 rounded-md overflow-hidden">
                {conflictModalData.alternatives.map((alt) => (
                  <div key={alt.id} className="p-2.5 text-xs flex items-center justify-between bg-white">
                    <div>
                      <span className="font-semibold text-slate-900">{alt.name}</span>
                      <span className="text-slate-500 ml-2">
                        ({alt.resource_type} {alt.location ? `• ${alt.location}` : ''})
                      </span>
                    </div>
                    <span className="text-emerald-600 font-medium bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      Available
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex justify-end pt-3 border-t border-slate-200">
            <button
              onClick={() => setConflictModalData(null)}
              className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-md"
            >
              Close
            </button>
          </div>
        </div>
      </FormModal>
    </div>
  );
}
