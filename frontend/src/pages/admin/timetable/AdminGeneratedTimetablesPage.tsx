import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Layers,
  Calendar,
  CheckCircle2,
  Clock,
  Plus,
  Send,
  Trash2,
  Archive,
  FileCheck2,
  Users,
  Eye,
  Edit3,
  Building,
  GraduationCap,
  Loader2,
  X,
  AlertCircle,
} from 'lucide-react';
import {
  getTimetableVersions,
  getTimetableVersionsSummary,
  approveTimetableVersion,
  getTimetableCoordinators,
  archiveTimetableVersion,
  deleteTimetableVersion,
  publishTimetableVersion,
  getTimetableAcademicYears,
  getTimetableDepartments,
  type TimetableVersionResponse,
  type PublishPreflightResponse,
} from '@/api/timetable';
import { PageHeader, EmptyState, LoadingState, ErrorState, SearchBar } from '@/components/common';
import { useToast } from '@/context/useToast';

export const AdminGeneratedTimetablesPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  // Filters state
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDeptId, setSelectedDeptId] = useState<string>('ALL');
  const [selectedAyId, setSelectedAyId] = useState<string>('ALL');
  const [selectedStatusTab, setSelectedStatusTab] = useState<string>('ALL');
  const [sortBy, setSortBy] = useState<'NEWEST' | 'OLDEST' | 'REVISION'>('NEWEST');

  // Modal states
  const [publishModalVersion, setPublishModalVersion] = useState<TimetableVersionResponse | null>(null);
  const [approveModalVersion, setApproveModalVersion] = useState<TimetableVersionResponse | null>(null);
  const [deleteModalVersion, setDeleteModalVersion] = useState<TimetableVersionResponse | null>(null);

  // Queries
  const { data: summary } = useQuery({
    queryKey: ['timetable', 'versions', 'summary'],
    queryFn: getTimetableVersionsSummary,
  });

  const { data: versions = [], isLoading, isError, error } = useQuery({
    queryKey: ['timetable', 'versions'],
    queryFn: () => getTimetableVersions(),
  });

  const { data: academicYears = [] } = useQuery({
    queryKey: ['timetable-academic-years'],
    queryFn: getTimetableAcademicYears,
  });

  const { data: departments = [] } = useQuery({
    queryKey: ['timetable-departments', 'all'],
    queryFn: () => getTimetableDepartments(),
  });

  // Preflight coordinator query when modal is open
  const {
    data: preflightData,
    isLoading: loadingPreflight,
  } = useQuery<PublishPreflightResponse>({
    queryKey: ['timetable', 'coordinators', publishModalVersion?.id],
    queryFn: () => getTimetableCoordinators(publishModalVersion!.id),
    enabled: !!publishModalVersion,
  });

  // Mutations
  const approveMutation = useMutation({
    mutationFn: (versionId: number) => approveTimetableVersion(versionId),
    onSuccess: (data) => {
      toast.success(data.message || 'Timetable approved successfully.');
      queryClient.invalidateQueries({ queryKey: ['timetable', 'versions'] });
      setApproveModalVersion(null);
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || err?.message || 'Failed to approve timetable.';
      toast.error(`Approval failed: ${msg}`);
    },
  });

  const publishMutation = useMutation({
    mutationFn: (versionId: number) => publishTimetableVersion(versionId),
    onSuccess: (data) => {
      toast.success(data.message || 'Timetable published to coordinators and active portals.');
      queryClient.invalidateQueries({ queryKey: ['timetable', 'versions'] });
      setPublishModalVersion(null);
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || err?.message || 'Failed to publish timetable.';
      toast.error(`Publication failed: ${msg}`);
    },
  });

  const archiveMutation = useMutation({
    mutationFn: (versionId: number) => archiveTimetableVersion(versionId),
    onSuccess: (data) => {
      toast.success(data.message || 'Timetable archived.');
      queryClient.invalidateQueries({ queryKey: ['timetable', 'versions'] });
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || 'Failed to archive timetable.';
      toast.error(msg);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (versionId: number) => deleteTimetableVersion(versionId),
    onSuccess: (data) => {
      toast.success(data.message || 'Timetable version deleted.');
      queryClient.invalidateQueries({ queryKey: ['timetable', 'versions'] });
      setDeleteModalVersion(null);
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || 'Failed to delete timetable version.';
      toast.error(msg);
    },
  });

  // Filter and sort logic
  const filteredVersions = useMemo(() => {
    let result = [...versions];

    if (selectedDeptId !== 'ALL') {
      const deptIdNum = Number(selectedDeptId);
      result = result.filter((v) => v.department_id === deptIdNum);
    }

    if (selectedAyId !== 'ALL') {
      const ayIdNum = Number(selectedAyId);
      result = result.filter((v) => v.academic_year_id === ayIdNum);
    }

    if (selectedStatusTab !== 'ALL') {
      if (selectedStatusTab === 'REVIEW') {
        result = result.filter((v) => ['DRAFT', 'GENERATED', 'REVIEWED'].includes((v.status || '').toUpperCase()));
      } else if (selectedStatusTab === 'APPROVED') {
        result = result.filter((v) => ['VALIDATED', 'FINALIZED', 'APPROVED'].includes((v.status || '').toUpperCase()));
      } else if (selectedStatusTab === 'PUBLISHED') {
        result = result.filter((v) => (v.status || '').toUpperCase() === 'PUBLISHED');
      } else if (selectedStatusTab === 'ARCHIVED') {
        result = result.filter((v) => ['ARCHIVED', 'REJECTED'].includes((v.status || '').toUpperCase()));
      }
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter((v) => {
        const idStr = `v${v.id} ${v.id} rev ${v.revision || 1}`;
        const deptStr = v.department_name || '';
        const progStr = v.program_name || '';
        const ayStr = v.academic_year_name || '';
        const statusStr = v.status || '';
        const secStr = (v.section_names || []).join(' ');
        const creatorStr = v.created_by_name || '';
        const full = `${idStr} ${deptStr} ${progStr} ${ayStr} ${statusStr} ${secStr} ${creatorStr}`.toLowerCase();
        return full.includes(q);
      });
    }

    if (sortBy === 'NEWEST') {
      result.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    } else if (sortBy === 'OLDEST') {
      result.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
    } else if (sortBy === 'REVISION') {
      result.sort((a, b) => (b.revision || 1) - (a.revision || 1));
    }

    return result;
  }, [versions, selectedDeptId, selectedAyId, selectedStatusTab, searchQuery, sortBy]);

  const renderStatusBadge = (status: string | null) => {
    const s = (status || 'DRAFT').toUpperCase();
    switch (s) {
      case 'GENERATED':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">GENERATED</span>;
      case 'REVIEWED':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">IN REVIEW</span>;
      case 'VALIDATED':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">VALIDATED</span>;
      case 'FINALIZED':
      case 'APPROVED':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">APPROVED</span>;
      case 'PUBLISHED':
        return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-teal-50 text-teal-700 border border-teal-200"><CheckCircle2 size={11} /> PUBLISHED</span>;
      case 'ARCHIVED':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">ARCHIVED</span>;
      default:
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">{s}</span>;
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Generated Timetables"
        subtitle="Review, approve, and authoritatively publish generated academic timetables to related department coordinators."
        breadcrumbs={[
          { label: 'Admin', href: '/admin' },
          { label: 'Timetable', href: '/admin/timetable' },
          { label: 'Generated Timetables' },
        ]}
        actions={
          <button
            onClick={() => navigate('/admin/timetable')}
            className="academic-btn-primary inline-flex items-center gap-2"
          >
            <Plus size={16} />
            <span>Generate Timetable</span>
          </button>
        }
      />

      {/* 4 Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Total Generated</p>
            <p className="text-2xl font-bold text-slate-900 mt-1">{summary?.total_generated ?? versions.length}</p>
            <p className="text-xs text-slate-400 mt-0.5">Persisted drafts & versions</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
            <Layers size={20} />
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-amber-700 uppercase tracking-wider">Awaiting Review</p>
            <p className="text-2xl font-bold text-amber-700 mt-1">{summary?.awaiting_review ?? 0}</p>
            <p className="text-xs text-slate-400 mt-0.5">Draft, Generated, Reviewed</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
            <Clock size={20} />
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-indigo-700 uppercase tracking-wider">Validated / Approved</p>
            <p className="text-2xl font-bold text-indigo-700 mt-1">{summary?.approved ?? 0}</p>
            <p className="text-xs text-slate-400 mt-0.5">Ready for publication</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
            <FileCheck2 size={20} />
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-teal-700 uppercase tracking-wider">Live Published</p>
            <p className="text-2xl font-bold text-teal-700 mt-1">{summary?.published ?? 0}</p>
            <p className="text-xs text-slate-400 mt-0.5">Active on portals</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-teal-50 text-teal-600 flex items-center justify-center">
            <CheckCircle2 size={20} />
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-4">
        {/* Status Tabs */}
        <div className="flex flex-wrap items-center gap-1 border-b border-slate-100 pb-3">
          {[
            { id: 'ALL', label: 'All Versions' },
            { id: 'REVIEW', label: 'Awaiting Review' },
            { id: 'APPROVED', label: 'Approved & Validated' },
            { id: 'PUBLISHED', label: 'Published' },
            { id: 'ARCHIVED', label: 'Archived' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setSelectedStatusTab(tab.id)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                selectedStatusTab === tab.id
                  ? 'bg-slate-900 text-white'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Filter Controls Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          <SearchBar
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Search department, semester, V#..."
            className="w-full"
          />

          <select
            value={selectedDeptId}
            onChange={(e) => setSelectedDeptId(e.target.value)}
            className="w-full text-xs font-medium rounded-lg border border-slate-300 px-3 py-2 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="ALL">All Departments</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} ({d.department_code})
              </option>
            ))}
          </select>

          <select
            value={selectedAyId}
            onChange={(e) => setSelectedAyId(e.target.value)}
            className="w-full text-xs font-medium rounded-lg border border-slate-300 px-3 py-2 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="ALL">All Academic Years</option>
            {academicYears.map((ay) => (
              <option key={ay.id} value={ay.id}>
                {ay.name}
              </option>
            ))}
          </select>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="w-full text-xs font-medium rounded-lg border border-slate-300 px-3 py-2 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="NEWEST">Sort: Newest Generated</option>
            <option value="OLDEST">Sort: Oldest Generated</option>
            <option value="REVISION">Sort: Highest Revision</option>
          </select>
        </div>
      </div>

      {/* Main Content List / Table */}
      {isLoading ? (
        <LoadingState message="Loading generated timetables and approval status..." />
      ) : isError ? (
        <ErrorState
          title="Failed to Load Timetables"
          message={error instanceof Error ? error.message : 'Server error occurred while loading timetables.'}
        />
      ) : filteredVersions.length === 0 ? (
        <EmptyState
          icon={<Calendar size={28} className="text-slate-400" />}
          title="No Matching Timetables Found"
          description={
            searchQuery || selectedDeptId !== 'ALL' || selectedStatusTab !== 'ALL'
              ? 'No timetable versions match the selected search or filter criteria. Try resetting filters.'
              : 'No academic timetables have been generated yet. Click "Generate Timetable" to create a new draft.'
          }
          action={
            <button
              onClick={() => navigate('/admin/timetable')}
              className="academic-btn-primary text-xs inline-flex items-center gap-1.5"
            >
              <Plus size={14} />
              <span>Generate Timetable</span>
            </button>
          }
        />
      ) : (
        <div className="space-y-3">
          {filteredVersions.map((v) => {
            const isApproved = ['APPROVED', 'FINALIZED'].includes((v.status || '').toUpperCase());
            const isPublished = (v.status || '').toUpperCase() === 'PUBLISHED';
            const isValidated = (v.status || '').toUpperCase() === 'VALIDATED';
            const isArchived = ['ARCHIVED', 'REJECTED'].includes((v.status || '').toUpperCase());

            return (
              <div
                key={v.id}
                className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm hover:border-slate-300 transition-all flex flex-col lg:flex-row lg:items-center justify-between gap-4"
              >
                {/* Left: Info & Scope */}
                <div className="space-y-2 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm font-bold text-slate-900 bg-slate-100 px-2 py-0.5 rounded">
                      V{v.id}
                    </span>
                    {renderStatusBadge(v.status)}
                    <span className="text-xs text-slate-500 font-medium">
                      Revision {v.revision || 1}
                    </span>
                    {v.validated_revision === v.revision ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
                        <CheckCircle2 size={11} /> Conflict-free
                      </span>
                    ) : v.status !== 'PUBLISHED' ? (
                      <span className="text-[11px] font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded">
                        Edits need validation
                      </span>
                    ) : null}
                  </div>

                  {/* Academic Scope details */}
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-700">
                    <span className="inline-flex items-center gap-1.5 font-semibold text-slate-900">
                      <Building size={14} className="text-slate-400" />
                      {v.department_name || `Dept #${v.department_id || 'All'}`}
                    </span>
                    {v.semester_number && (
                      <span className="inline-flex items-center gap-1 text-slate-600">
                        <GraduationCap size={14} className="text-slate-400" />
                        Semester {v.semester_number}
                      </span>
                    )}
                    {v.section_names && v.section_names.length > 0 && (
                      <span className="inline-flex items-center gap-1 text-slate-600">
                        <Users size={14} className="text-slate-400" />
                        Sections: {v.section_names.join(', ')}
                      </span>
                    )}
                    {v.academic_year_name && (
                      <span className="text-slate-500">
                        AY: {v.academic_year_name}
                      </span>
                    )}
                    <span className="text-slate-400">
                      {v.entry_count ? `${v.entry_count} Classes` : 'Entries persisted'}
                    </span>
                  </div>

                  {/* Timestamps and Author */}
                  <div className="flex flex-wrap items-center gap-x-4 text-[11px] text-slate-400">
                    <span>Generated: {new Date(v.created_at).toLocaleDateString()} {new Date(v.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    {v.created_by_name && <span>By: {v.created_by_name}</span>}
                    {v.approved_at && (
                      <span className="text-emerald-700 font-medium">
                        Approved: {new Date(v.approved_at).toLocaleDateString()} {v.approved_by_name ? `by ${v.approved_by_name}` : ''}
                      </span>
                    )}
                    {v.published_at && (
                      <span className="text-teal-700 font-medium">
                        Published: {new Date(v.published_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>

                {/* Right: Actions */}
                <div className="flex flex-wrap items-center gap-2 shrink-0 pt-2 lg:pt-0 border-t lg:border-t-0 border-slate-100">
                  {/* Primary Review / Edit Button */}
                  <button
                    onClick={() => navigate(`/admin/timetable/versions/${v.id}`)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
                  >
                    {isPublished ? <Eye size={13} /> : <Edit3 size={13} />}
                    <span>{isPublished ? 'View Schedule' : 'Review & Edit'}</span>
                  </button>

                  {/* If Validated but not yet Approved: Quick Approve */}
                  {isValidated && (
                    <button
                      onClick={() => setApproveModalVersion(v)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm transition-colors"
                    >
                      <FileCheck2 size={13} />
                      <span>Approve</span>
                    </button>
                  )}

                  {/* If Approved: Publish to Coordinators */}
                  {isApproved && (
                    <button
                      onClick={() => setPublishModalVersion(v)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-teal-600 text-white hover:bg-teal-700 shadow-sm transition-colors"
                    >
                      <Send size={13} />
                      <span>Publish to Coordinators</span>
                    </button>
                  )}

                  {/* Archive / Delete actions */}
                  {!isPublished && !isArchived && (
                    <button
                      onClick={() => archiveMutation.mutate(v.id)}
                      disabled={archiveMutation.isPending}
                      title="Archive this version"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                    >
                      <Archive size={14} />
                    </button>
                  )}

                  {!isPublished && (
                    <button
                      onClick={() => setDeleteModalVersion(v)}
                      title="Delete draft version"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Approve Confirmation Modal */}
      {approveModalVersion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <FileCheck2 size={20} className="text-emerald-600" />
                <h3 className="text-base font-bold text-slate-900">Approve Timetable Version</h3>
              </div>
              <button
                onClick={() => setApproveModalVersion(null)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X size={18} />
              </button>
            </div>

            <p className="text-sm text-slate-600">
              You are approving <span className="font-bold text-slate-900">Timetable Version V{approveModalVersion.id}</span> (Revision {approveModalVersion.revision || 1}).
            </p>

            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-xs text-emerald-800 space-y-1">
              <p className="font-semibold">Approval Safeguards:</p>
              <ul className="list-disc pl-4 space-y-0.5">
                <li>Authoritative conflict validation will run immediately.</li>
                <li>Version will transition to <span className="font-semibold">APPROVED</span> status.</li>
                <li>Coordinators can inspect and you can proceed to formal publishing.</li>
                <li>Any subsequent edits will immediately invalidate this approval.</li>
              </ul>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setApproveModalVersion(null)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                onClick={() => approveMutation.mutate(approveModalVersion.id)}
                disabled={approveMutation.isPending}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm"
              >
                {approveMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <FileCheck2 size={14} />}
                <span>Confirm & Approve</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Coordinator Preflight & Publish Modal */}
      {publishModalVersion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <Send size={20} className="text-teal-600" />
                <h3 className="text-base font-bold text-slate-900">Publish Timetable to Coordinators</h3>
              </div>
              <button
                onClick={() => setPublishModalVersion(null)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X size={18} />
              </button>
            </div>

            {loadingPreflight ? (
              <div className="py-8 flex flex-col items-center justify-center space-y-2">
                <Loader2 size={24} className="text-teal-600 animate-spin" />
                <p className="text-xs text-slate-500">Resolving authoritative coordinators for this scope...</p>
              </div>
            ) : preflightData ? (
              <div className="space-y-4">
                {/* Academic Scope Summary */}
                <div className="bg-slate-50 rounded-xl p-3 text-xs space-y-1 border border-slate-200">
                  <p className="font-semibold text-slate-800">Target Academic Scope:</p>
                  <p className="text-slate-600">
                    <span className="font-medium">Department:</span> {preflightData.department_name || 'All'}
                    {preflightData.semester_number && ` • Semester ${preflightData.semester_number}`}
                    {preflightData.section_names.length > 0 && ` • Sections: ${preflightData.section_names.join(', ')}`}
                  </p>
                  <p className="text-slate-500">Version V{preflightData.version_id} (Rev {preflightData.revision})</p>
                </div>

                {/* Blocking Warnings if any */}
                {!preflightData.can_publish && preflightData.blocking_reasons.length > 0 && (
                  <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-xs text-red-800 space-y-1">
                    <div className="flex items-center gap-1.5 font-bold">
                      <AlertCircle size={14} className="text-red-600" />
                      <span>Publication Blocked:</span>
                    </div>
                    <ul className="list-disc pl-4 space-y-0.5">
                      {preflightData.blocking_reasons.map((reason, idx) => (
                        <li key={idx}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Coordinator Recipients List */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                      Target Coordinators ({preflightData.coordinator_count})
                    </span>
                    <span className="text-[11px] text-slate-500">From database relations</span>
                  </div>

                  {preflightData.coordinators.length === 0 ? (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-800">
                      No eligible coordinators mapped for this department/section scope. You must assign at least one coordinator or section class teacher before publishing.
                    </div>
                  ) : (
                    <div className="max-h-48 overflow-y-auto space-y-2 pr-1 border border-slate-200 rounded-xl p-2 bg-slate-50/50">
                      {preflightData.coordinators.map((c) => (
                        <div
                          key={c.id}
                          className="bg-white p-2.5 rounded-lg border border-slate-200 shadow-2xs flex items-center justify-between text-xs"
                        >
                          <div>
                            <p className="font-bold text-slate-900">{c.name}</p>
                            <p className="text-[11px] text-slate-500">{c.role_or_designation} • {c.scope_description}</p>
                          </div>
                          {c.email && (
                            <span className="text-[11px] text-slate-400 font-mono">{c.email}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Notice */}
                <div className="bg-teal-50 border border-teal-200 rounded-xl p-3 text-xs text-teal-800 space-y-1">
                  <p className="font-semibold">Publication Effects:</p>
                  <ul className="list-disc pl-4 space-y-0.5">
                    <li>Canonical timetable records will be atomically updated.</li>
                    <li>All resolved coordinators will receive instant notifications linking to their department view.</li>
                    <li>Student and faculty schedules will synchronize immediately.</li>
                  </ul>
                </div>

                {/* Action Buttons */}
                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                  <button
                    onClick={() => setPublishModalVersion(null)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => publishMutation.mutate(preflightData.version_id)}
                    disabled={!preflightData.can_publish || publishMutation.isPending}
                    className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white shadow-sm transition-colors ${
                      preflightData.can_publish && !publishMutation.isPending
                        ? 'bg-teal-600 hover:bg-teal-700'
                        : 'bg-slate-300 cursor-not-allowed'
                    }`}
                  >
                    {publishMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                    <span>Confirm & Publish to Coordinators</span>
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteModalVersion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-sm w-full p-6 shadow-xl border border-slate-200 space-y-4">
            <h3 className="text-base font-bold text-slate-900">Delete Draft Timetable?</h3>
            <p className="text-xs text-slate-600">
              Are you sure you want to delete draft version <span className="font-semibold text-slate-900">V{deleteModalVersion.id}</span>? This action removes all draft entries for this version and cannot be undone.
            </p>
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setDeleteModalVersion(null)}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteModalVersion.id)}
                disabled={deleteMutation.isPending}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-600 text-white hover:bg-red-700 shadow-sm"
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete Draft'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
