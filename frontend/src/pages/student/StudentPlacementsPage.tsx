/**
 * pages/student/StudentPlacementsPage.tsx
 * ---------------------------------------
 * CDC Campus Placement Drives & Internship Portal for Students.
 * Features deterministic eligibility badges, schedule breakdown, and application guidelines.
 */

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
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
} from 'lucide-react';

import {
  PageHeader,
  StatCard,
  LoadingState,
  FormModal,
} from '@/components/common';

import {
  placementsApi,
  type PlacementDriveItem,
} from '@/api/placements';

export function StudentPlacementsPage() {
  const [activeTab, setActiveTab] = useState<'all' | 'eligible' | 'internship' | 'full_time'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDrive, setSelectedDrive] = useState<PlacementDriveItem | null>(null);

  // Queries
  const { data: drives = [], isLoading } = useQuery<PlacementDriveItem[]>({
    queryKey: ['student', 'placement-drives'],
    queryFn: () => placementsApi.listDrives(),
    refetchInterval: 60_000,
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

      {/* Drives Grid */}
      {isLoading ? (
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
                    {renderEligibilityBadge(elig?.status)}
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

                <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
                  <button
                    onClick={() => setSelectedDrive(drive)}
                    className="w-full flex items-center justify-center gap-1.5 py-2 px-3 text-xs font-semibold text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded-lg transition"
                  >
                    View Details & Rounds
                    <ArrowRight size={14} />
                  </button>
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

                {selectedDrive.application_link && !selectedDrive.is_deadline_passed && (
                  <a
                    href={selectedDrive.application_link}
                    target="_blank"
                    rel="noreferrer"
                    className={`px-4 py-2 rounded-lg text-xs font-semibold inline-flex items-center gap-1.5 transition ${
                      selectedDrive.eligibility?.status === 'NOT_ELIGIBLE'
                        ? 'bg-slate-200 text-slate-500 pointer-events-none cursor-not-allowed'
                        : 'bg-blue-600 hover:bg-blue-700 text-white shadow-xs'
                    }`}
                  >
                    Apply Now
                    <ExternalLink size={13} />
                  </a>
                )}
              </div>
            </div>
          </div>
        </FormModal>
      )}
    </div>
  );
}
