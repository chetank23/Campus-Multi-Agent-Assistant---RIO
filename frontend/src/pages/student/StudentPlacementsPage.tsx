/**
 * pages/student/StudentPlacementsPage.tsx
 * ---------------------------------------
 * CDC Campus Placement Drives & Internship Portal for Students.
 * Features deterministic eligibility badges, schedule breakdown, and application guidelines.
 */

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Briefcase,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Calendar,
  Clock,
  MapPin,
  ExternalLink,
  Search,
  DollarSign,
  ArrowRight,
  ShieldCheck,
  FileText,
  Send,
} from 'lucide-react';

import {
  PageHeader,
  StatCard,
  LoadingState,
  FormModal,
} from '@/components/common';
import { useToast } from '@/context/useToast';

import {
  placementsApi,
  type PlacementDriveItem,
  type PlacementApplicationItem,
} from '@/api/placements';

export function StudentPlacementsPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [activeTab, setActiveTab] = useState<'all' | 'eligible' | 'internship' | 'full_time' | 'my_applications'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDrive, setSelectedDrive] = useState<PlacementDriveItem | null>(null);

  // Apply Modal state
  const [applyingDrive, setApplyingDrive] = useState<PlacementDriveItem | null>(null);
  const [resumeUrl, setResumeUrl] = useState('');
  const [applyNotes, setApplyNotes] = useState('');

  // Queries
  const { data: drives = [], isLoading } = useQuery<PlacementDriveItem[]>({
    queryKey: ['student', 'placement-drives'],
    queryFn: () => placementsApi.listDrives(),
    refetchInterval: 60_000,
  });

  const { data: myApplications = [], isLoading: isLoadingApps } = useQuery<PlacementApplicationItem[]>({
    queryKey: ['student', 'placement-applications'],
    queryFn: () => placementsApi.getMyApplications(),
    refetchInterval: 60_000,
  });

  // Map of applied drives
  const appliedMap = useMemo(
    () => new Map(myApplications.map((a) => [a.drive_id, a])),
    [myApplications]
  );

  // Apply mutation
  const applyMutation = useMutation({
    mutationFn: ({ driveId, payload }: { driveId: number; payload: { resume_url?: string; notes?: string } }) =>
      placementsApi.applyForDrive(driveId, payload),
    onSuccess: () => {
      toast.success('Your placement application has been successfully submitted!');
      queryClient.invalidateQueries({ queryKey: ['student', 'placement-applications'] });
      setApplyingDrive(null);
      setResumeUrl('');
      setApplyNotes('');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Failed to submit application. Please check eligibility.');
    },
  });

  // Filtered drives
  const filteredDrives = useMemo(() => {
    let result = drives;

    if (activeTab === 'eligible') {
      result = result.filter((d) => d.eligibility?.status === 'ELIGIBLE');
    } else if (activeTab === 'internship') {
      result = result.filter((d) => d.job_type === 'INTERNSHIP');
    } else if (activeTab === 'full_time') {
      result = result.filter((d) => d.job_type === 'FULL_TIME' || d.job_type === 'INTERN_PLUS_FULL_TIME');
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (d) =>
          d.company_name.toLowerCase().includes(q) ||
          d.job_role.toLowerCase().includes(q) ||
          d.title.toLowerCase().includes(q) ||
          (d.work_location && d.work_location.toLowerCase().includes(q))
      );
    }

    return result;
  }, [drives, activeTab, searchQuery]);

  // Statistics
  const stats = useMemo(() => {
    const total = drives.length;
    const eligibleCount = drives.filter((d) => d.eligibility?.status === 'ELIGIBLE').length;
    const pendingRecordCount = drives.filter((d) => d.eligibility?.status === 'CANNOT_DETERMINE').length;
    const upcomingDeadlines = drives.filter((d) => !d.is_deadline_passed).length;

    return { total, eligibleCount, pendingRecordCount, upcomingDeadlines };
  }, [drives]);

  const renderEligibilityBadge = (status?: string) => {
    switch (status) {
      case 'ELIGIBLE':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 size={13} className="text-emerald-600" />
            Eligible
          </span>
        );
      case 'NOT_ELIGIBLE':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <XCircle size={13} className="text-rose-600" />
            Not Eligible
          </span>
        );
      case 'CANNOT_DETERMINE':
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <AlertCircle size={13} className="text-amber-600" />
            Record Pending
          </span>
        );
    }
  };

  const getJobTypeLabel = (type: string) => {
    switch (type) {
      case 'INTERNSHIP':
        return 'Internship';
      case 'FULL_TIME':
        return 'Full Time';
      case 'INTERN_PLUS_FULL_TIME':
        return 'Intern + Full Time';
      default:
        return type;
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="CDC Placement Drives"
        subtitle="Explore verified campus recruitment drives, internships, selection schedules, and check your real-time eligibility."
        breadcrumbs={[
          { label: 'Dashboard', href: '/student' },
          { label: 'Placement Drives' },
        ]}
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Active Drives"
          value={stats.total}
          icon={<Briefcase size={20} className="text-blue-600" />}
          sub="Published on campus"
        />
        <StatCard
          label="Eligible for You"
          value={stats.eligibleCount}
          icon={<CheckCircle2 size={20} className="text-emerald-600" />}
          sub="Meet all criteria"
          variant="success"
        />
        <StatCard
          label="Record Incomplete"
          value={stats.pendingRecordCount}
          icon={<AlertCircle size={20} className="text-amber-600" />}
          sub={stats.pendingRecordCount > 0 ? 'Update CGPA with CDC' : 'All profiles verified'}
          variant={stats.pendingRecordCount > 0 ? 'warning' : 'default'}
        />
        <StatCard
          label="Open Deadlines"
          value={stats.upcomingDeadlines}
          icon={<Clock size={20} className="text-purple-600" />}
          sub="Applications active"
        />
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl shadow-xs border border-slate-200 flex flex-col md:flex-row gap-4 items-center justify-between">
        <div className="flex gap-2 w-full md:w-auto overflow-x-auto">
          <button
            onClick={() => setActiveTab('all')}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'all'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            All Drives ({drives.length})
          </button>
          <button
            onClick={() => setActiveTab('eligible')}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'eligible'
                ? 'bg-emerald-600 text-white'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            Eligible for Me ({stats.eligibleCount})
          </button>
          <button
            onClick={() => setActiveTab('full_time')}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'full_time'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            Full-Time
          </button>
          <button
            onClick={() => setActiveTab('internship')}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'internship'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            Internship
          </button>
          <button
            onClick={() => setActiveTab('my_applications')}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'my_applications'
                ? 'bg-purple-600 text-white'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            My Applications ({myApplications.length})
          </button>
        </div>

        <div className="relative w-full md:w-72">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search company, role..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white"
          />
        </div>
      </div>

      {/* Drives Grid or Applications List */}
      {activeTab === 'my_applications' ? (
        isLoadingApps ? (
          <LoadingState message="Loading your placement applications..." />
        ) : myApplications.length === 0 ? (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
            <Briefcase size={40} className="mx-auto text-slate-300 mb-3" />
            <h3 className="text-base font-semibold text-slate-800">No Applications Submitted Yet</h3>
            <p className="text-sm text-slate-500 mt-1 max-w-sm mx-auto">
              You haven't applied to any placement drives yet. Switch to "Eligible for Me" to explore and submit applications!
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {myApplications.map((app) => (
              <div
                key={app.id}
                className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-purple-50 border border-purple-100 flex items-center justify-center text-purple-700 font-bold text-base shrink-0">
                      {app.company_name?.charAt(0).toUpperCase() || 'P'}
                    </div>
                    <div>
                      <h3 className="font-semibold text-slate-900 text-sm">
                        {app.company_name} — {app.job_role}
                      </h3>
                      <p className="text-xs text-slate-500">
                        Applied on {new Date(app.applied_at).toLocaleDateString()} at{' '}
                        {new Date(app.applied_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  </div>
                  {app.notes && (
                    <p className="text-xs text-slate-600 bg-slate-50 p-2 rounded border border-slate-100 mt-2">
                      <span className="font-semibold text-slate-700">Notes: </span>
                      {app.notes}
                    </p>
                  )}
                  {app.resume_url && (
                    <div className="text-xs text-blue-600 mt-1">
                      <a href={app.resume_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:underline">
                        <FileText size={12} />
                        View Attached Resume
                      </a>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide border ${
                      app.status === 'SELECTED'
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        : app.status === 'SHORTLISTED' || app.status === 'INTERVIEW_SCHEDULED'
                        ? 'bg-blue-50 text-blue-700 border-blue-200'
                        : app.status === 'REJECTED'
                        ? 'bg-rose-50 text-rose-700 border-rose-200'
                        : 'bg-slate-100 text-slate-700 border-slate-200'
                    }`}
                  >
                    {app.status.replace('_', ' ')}
                  </span>
                  {app.drive_id && (
                    <button
                      onClick={() => {
                        const targetDrive = drives.find((d) => d.id === app.drive_id);
                        if (targetDrive) setSelectedDrive(targetDrive);
                      }}
                      className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                    >
                      Drive Details
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )
      ) : isLoading ? (
        <LoadingState message="Loading campus placement drives..." />
      ) : filteredDrives.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
          <Briefcase size={40} className="mx-auto text-slate-300 mb-3" />
          <h3 className="text-base font-semibold text-slate-800">No Placement Drives Found</h3>
          <p className="text-sm text-slate-500 mt-1 max-w-sm mx-auto">
            {searchQuery
              ? 'No recruitment drives match your search query.'
              : activeTab === 'eligible'
              ? 'You do not currently match the requirements for active drives, or your academic record needs verification.'
              : 'There are currently no active placement drives published.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredDrives.map((drive) => {
            const elig = drive.eligibility;
            const isDeadlineOver = drive.is_deadline_passed;
            const hasApplied = appliedMap.has(drive.id);
            const myApp = appliedMap.get(drive.id);

            return (
              <div
                key={drive.id}
                className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs hover:shadow-md transition flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-11 h-11 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-700 font-bold text-lg shrink-0">
                        {drive.company_name.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <h3 className="font-semibold text-slate-900 leading-snug line-clamp-1">
                          {drive.company_name}
                        </h3>
                        <p className="text-xs text-slate-500 line-clamp-1">{drive.job_role}</p>
                      </div>
                    </div>
                    {hasApplied ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                        <CheckCircle2 size={13} className="text-blue-600" />
                        Applied ({myApp?.status})
                      </span>
                    ) : (
                      renderEligibilityBadge(elig?.status)
                    )}
                  </div>

                  <div className="space-y-2 text-xs text-slate-600 mb-4 mt-2">
                    <div className="flex items-center gap-2">
                      <Briefcase size={14} className="text-slate-400 shrink-0" />
                      <span className="font-medium text-slate-700">{getJobTypeLabel(drive.job_type)}</span>
                      {drive.tier && (
                        <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono text-[11px]">
                          {drive.tier}
                        </span>
                      )}
                    </div>

                    {drive.compensation_details && (
                      <div className="flex items-center gap-2">
                        <DollarSign size={14} className="text-emerald-600 shrink-0" />
                        <span className="font-medium text-emerald-700">{drive.compensation_details}</span>
                      </div>
                    )}

                    {drive.work_location && (
                      <div className="flex items-center gap-2">
                        <MapPin size={14} className="text-slate-400 shrink-0" />
                        <span className="truncate">{drive.work_location}</span>
                      </div>
                    )}

                    <div className="flex items-center gap-2">
                      <Clock size={14} className={isDeadlineOver ? 'text-rose-500 shrink-0' : 'text-amber-500 shrink-0'} />
                      <span className={isDeadlineOver ? 'text-rose-600 font-medium' : 'text-slate-600'}>
                        {isDeadlineOver ? 'Deadline Passed' : `Deadline: ${new Date(drive.application_deadline).toLocaleDateString()}`}
                      </span>
                    </div>

                    {drive.schedules && drive.schedules.length > 0 && (
                      <div className="flex items-center gap-2">
                        <Calendar size={14} className="text-blue-500 shrink-0" />
                        <span>{drive.schedules.length} Selection Round{drive.schedules.length > 1 ? 's' : ''}</span>
                      </div>
                    )}
                  </div>

                  {/* Criteria snippet */}
                  <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 text-[11px] text-slate-600 space-y-1 mb-4">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Min CGPA:</span>
                      <span className="font-medium text-slate-800">
                        {drive.min_cgpa ? `${drive.min_cgpa} / ${drive.grading_scale}` : 'No minimum'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Max Backlogs:</span>
                      <span className="font-medium text-slate-800">
                        {drive.max_active_backlogs != null ? drive.max_active_backlogs : 'Any'}
                      </span>
                    </div>
                    {drive.eligible_department_names && drive.eligible_department_names.length > 0 && (
                      <div className="flex justify-between items-center">
                        <span className="text-slate-500">Branches:</span>
                        <span className="font-medium text-slate-800 truncate max-w-[140px]">
                          {drive.eligible_department_names.join(', ')}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-100 flex items-center gap-2">
                  <button
                    onClick={() => setSelectedDrive(drive)}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 text-xs font-semibold text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded-lg transition"
                  >
                    View Details & Rounds
                    <ArrowRight size={14} />
                  </button>
                  {!hasApplied && elig?.status === 'ELIGIBLE' && !isDeadlineOver && (
                    <button
                      onClick={() => setApplyingDrive(drive)}
                      className="py-2 px-3 text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition shrink-0"
                    >
                      Apply
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Drive Detail & Application Modal */}
      {selectedDrive && (
        <FormModal
          isOpen={!!selectedDrive}
          onClose={() => setSelectedDrive(null)}
          title={selectedDrive.company_name}
          maxWidth="xl"
        >
          <div className="space-y-5">
            {/* Header / Intro */}
            <div className="flex items-start justify-between border-b border-slate-100 pb-4">
              <div>
                <h2 className="text-lg font-bold text-slate-900">{selectedDrive.job_role}</h2>
                <p className="text-xs text-slate-500 mt-0.5">{selectedDrive.title}</p>
                <div className="flex flex-wrap items-center gap-2 mt-2">
                  <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700">
                    {getJobTypeLabel(selectedDrive.job_type)}
                  </span>
                  {selectedDrive.tier && (
                    <span className="px-2 py-0.5 rounded text-xs font-mono bg-slate-100 text-slate-600">
                      Tier: {selectedDrive.tier}
                    </span>
                  )}
                  {selectedDrive.work_location && (
                    <span className="text-xs text-slate-600 flex items-center gap-1">
                      <MapPin size={12} className="text-slate-400" />
                      {selectedDrive.work_location}
                    </span>
                  )}
                </div>
              </div>

              <div>{renderEligibilityBadge(selectedDrive.eligibility?.status)}</div>
            </div>

            {/* Compensation & Deadlines */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs">
              <div>
                <span className="text-slate-500 block">Compensation Package:</span>
                <span className="font-semibold text-emerald-700 text-sm">
                  {selectedDrive.compensation_details || 'As per industry standards'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Application Deadline:</span>
                <span className="font-semibold text-slate-800 text-sm">
                  {new Date(selectedDrive.application_deadline).toLocaleString()}
                </span>
              </div>
            </div>

            {/* Real-time Deterministic Eligibility Breakdown */}
            <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                <ShieldCheck size={18} className="text-blue-600" />
                Verified Eligibility Evaluation
              </div>
              <p className="text-xs text-slate-500">
                System evaluated your authoritative academic record against the drive requirements:
              </p>

              <div className="space-y-1.5 mt-2">
                {selectedDrive.eligibility?.reasons && selectedDrive.eligibility.reasons.length > 0 ? (
                  selectedDrive.eligibility.reasons.map((r, idx) => (
                    <div
                      key={idx}
                      className={`flex items-start gap-2 text-xs p-2 rounded-lg ${
                        r.toLowerCase().includes('ineligible') ||
                        r.toLowerCase().includes('below') ||
                        r.toLowerCase().includes('exceeds')
                          ? 'bg-rose-50 text-rose-800 border border-rose-100'
                          : r.toLowerCase().includes('pending') || r.toLowerCase().includes('missing')
                          ? 'bg-amber-50 text-amber-800 border border-amber-100'
                          : 'bg-emerald-50 text-emerald-800 border border-emerald-100'
                      }`}
                    >
                      {r.toLowerCase().includes('ineligible') ||
                      r.toLowerCase().includes('below') ||
                      r.toLowerCase().includes('exceeds') ? (
                        <XCircle size={14} className="text-rose-600 shrink-0 mt-0.5" />
                      ) : r.toLowerCase().includes('pending') || r.toLowerCase().includes('missing') ? (
                        <AlertCircle size={14} className="text-amber-600 shrink-0 mt-0.5" />
                      ) : (
                        <CheckCircle2 size={14} className="text-emerald-600 shrink-0 mt-0.5" />
                      )}
                      <span>{r}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-xs text-slate-500">
                    No specific restrictions recorded or all criteria fulfilled.
                  </div>
                )}
              </div>
            </div>

            {/* Description & Overview */}
            {selectedDrive.job_description && (
              <div className="space-y-1 text-xs">
                <h4 className="font-semibold text-slate-800">Job Description</h4>
                <p className="text-slate-600 whitespace-pre-line leading-relaxed bg-slate-50 p-3 rounded-lg border border-slate-100">
                  {selectedDrive.job_description}
                </p>
              </div>
            )}

            {/* Selection Rounds / Schedules */}
            <div className="space-y-2">
              <h4 className="font-semibold text-slate-800 text-xs">Selection Rounds & Timeline</h4>
              {selectedDrive.schedules && selectedDrive.schedules.length > 0 ? (
                <div className="space-y-2">
                  {selectedDrive.schedules.map((sc, idx) => (
                    <div
                      key={sc.id || idx}
                      className="p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs flex flex-col md:flex-row md:items-center justify-between gap-2"
                    >
                      <div>
                        <div className="font-semibold text-slate-800 flex items-center gap-2">
                          <span className="w-5 h-5 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-[10px] font-bold">
                            {sc.round_order || idx + 1}
                          </span>
                          {sc.title} ({sc.round_type})
                        </div>
                        <div className="text-slate-500 text-[11px] mt-1 flex flex-wrap items-center gap-3">
                          <span className="flex items-center gap-1">
                            <Clock size={12} />
                            {new Date(sc.start_time).toLocaleString()} - {new Date(sc.end_time).toLocaleTimeString()}
                          </span>
                          {sc.is_online ? (
                            <span className="text-blue-600 font-medium">Online Mode</span>
                          ) : (
                            <span className="flex items-center gap-1">
                              <MapPin size={12} />
                              {sc.venue_name || 'Campus Venue'}
                            </span>
                          )}
                        </div>
                      </div>

                      {sc.meeting_link && (
                        <a
                          href={sc.meeting_link}
                          target="_blank"
                          rel="noreferrer"
                          className="px-3 py-1 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded text-xs font-semibold inline-flex items-center gap-1 shrink-0"
                        >
                          Join Meeting
                          <ExternalLink size={12} />
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400">Rounds schedule will be updated shortly by the CDC coordinator.</p>
              )}
            </div>

            {/* Application Instructions & Links */}
            <div className="pt-3 border-t border-slate-100 flex flex-col md:flex-row items-center justify-between gap-3">
              <div className="text-xs text-slate-500">
                {selectedDrive.contact_email && (
                  <span>Contact CDC Coordinator: {selectedDrive.contact_email}</span>
                )}
              </div>

              <div className="flex items-center gap-3 w-full md:w-auto">
                <button
                  type="button"
                  onClick={() => setSelectedDrive(null)}
                  className="px-4 py-2 border border-slate-200 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50"
                >
                  Close
                </button>

                {appliedMap.has(selectedDrive.id) ? (
                  <span className="px-4 py-2 bg-blue-50 text-blue-700 border border-blue-200 rounded-lg text-xs font-semibold inline-flex items-center gap-1.5">
                    <CheckCircle2 size={13} className="text-blue-600" />
                    Application Submitted ({appliedMap.get(selectedDrive.id)?.status})
                  </span>
                ) : (
                  !selectedDrive.is_deadline_passed &&
                  selectedDrive.eligibility?.status === 'ELIGIBLE' && (
                    <button
                      type="button"
                      onClick={() => {
                        const target = selectedDrive;
                        setSelectedDrive(null);
                        setApplyingDrive(target);
                      }}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold inline-flex items-center gap-1.5 shadow-xs"
                    >
                      <Send size={13} />
                      Apply for Drive
                    </button>
                  )
                )}

                {selectedDrive.application_link && !selectedDrive.is_deadline_passed && (
                  <a
                    href={selectedDrive.application_link}
                    target="_blank"
                    rel="noreferrer"
                    className="px-4 py-2 rounded-lg text-xs font-semibold inline-flex items-center gap-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200"
                  >
                    External Link
                    <ExternalLink size={13} />
                  </a>
                )}
              </div>
            </div>
          </div>
        </FormModal>
      )}

      {/* Apply Form Modal */}
      {applyingDrive && (
        <FormModal
          isOpen={!!applyingDrive}
          onClose={() => setApplyingDrive(null)}
          title={`Apply: ${applyingDrive.company_name}`}
        >
          <div className="space-y-4 text-xs">
            <div className="p-3 bg-blue-50 border border-blue-100 rounded-lg text-blue-900">
              <div className="font-bold text-sm">{applyingDrive.job_role}</div>
              <div className="text-slate-600 mt-0.5">
                {applyingDrive.title} — {applyingDrive.compensation_details || 'Compensation undisclosed'}
              </div>
            </div>

            <div>
              <label className="block text-slate-700 font-semibold mb-1">
                Resume / Portfolio Link (Google Drive, LinkedIn, or Cloud Storage)
              </label>
              <input
                type="url"
                placeholder="https://drive.google.com/... or https://..."
                value={resumeUrl}
                onChange={(e) => setResumeUrl(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-slate-700 font-semibold mb-1">
                Candidate Notes / Cover Letter Remarks (Optional)
              </label>
              <textarea
                rows={3}
                placeholder="Add any relevant achievements, preferred domains, or notes for the recruitment team..."
                value={applyNotes}
                onChange={(e) => setApplyNotes(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setApplyingDrive(null)}
                className="px-4 py-2 border border-slate-200 text-slate-700 rounded-lg font-semibold hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={applyMutation.isPending}
                onClick={() =>
                  applyMutation.mutate({
                    driveId: applyingDrive.id,
                    payload: { resume_url: resumeUrl || undefined, notes: applyNotes || undefined },
                  })
                }
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold inline-flex items-center gap-1.5 disabled:opacity-50"
              >
                <Send size={13} />
                {applyMutation.isPending ? 'Submitting...' : 'Submit Application'}
              </button>
            </div>
          </div>
        </FormModal>
      )}
    </div>
  );
}
