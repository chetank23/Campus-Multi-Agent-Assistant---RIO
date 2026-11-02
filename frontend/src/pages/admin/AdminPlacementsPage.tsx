/**
 * pages/admin/AdminPlacementsPage.tsx
 * -----------------------------------
 * CDC Placement Management & Recruitment Hub for Administrators and CDC Coordinators.
 * Features:
 * - Operational KPI statistics & upcoming deadline tracking
 * - Drives directory with status filters (DRAFT, PUBLISHED, CLOSED, POSTPONED, CANCELLED)
 * - Direct publication with pre-flight validation checks
 * - Postpone & Cancel workflows with targeted candidate notifications
 * - New Drive creation modal with structured eligibility rules & multi-round selection schedule builder
 * - Student Academic Records management (CGPA, grading scale, backlogs)
 */

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Briefcase,
  CheckCircle2,
  AlertTriangle,
  Search,
  Plus,
  Clock,
  Ban,
  GraduationCap,
  Eye,
  Send,
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
  placementsApi,
  type PlacementDriveItem,
  type PlacementScheduleItem,
} from '@/api/placements';
import {
  departmentsApi,
  type DepartmentResponse,
} from '@/api/departments';

const STATUS_VARIANT_MAP: Record<string, StatusVariant> = {
  DRAFT: 'neutral',
  PUBLISHED: 'success',
  CLOSED: 'info',
  POSTPONED: 'warning',
  CANCELLED: 'danger',
  ARCHIVED: 'neutral',
};

export function AdminPlacementsPage() {
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<'drives' | 'academic_records'>('drives');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState<string>('');

  // Modals state
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [selectedDrive, setSelectedDrive] = useState<PlacementDriveItem | null>(null);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  const [actionModal, setActionModal] = useState<{
    isOpen: boolean;
    type: 'postpone' | 'cancel' | 'publish' | null;
    driveId: number | null;
    driveTitle: string;
    reason: string;
  }>({
    isOpen: false,
    type: null,
    driveId: null,
    driveTitle: '',
    reason: '',
  });

  // Academic record modal
  const [isRecordModalOpen, setIsRecordModalOpen] = useState(false);
  const [academicRecordForm, setAcademicRecordForm] = useState({
    student_id: 1,
    cgpa: 8.5,
    grading_scale: 10.0,
    active_backlogs: 0,
    total_backlogs: 0,
    graduation_year: 2026,
    is_verified: true,
  });

  // Create form state
  const [formData, setFormData] = useState({
    company_name: '',
    company_description: '',
    company_website: '',
    title: '',
    job_role: '',
    job_description: '',
    job_type: 'FULL_TIME' as const,
    work_location: 'Bengaluru / Hybrid',
    compensation_details: 'CTC: 12 LPA',
    tier: 'DREAM',
    eligible_department_ids: [] as number[],
    graduation_year: 2026,
    min_cgpa: 7.0,
    grading_scale: 10.0,
    max_active_backlogs: 0,
    max_total_backlogs: 1,
    allowed_genders: 'ALL' as const,
    application_deadline: '',
    application_link: '',
    application_instructions: 'Complete application on the company portal with resume and transcripts.',
    required_documents: 'Resume (PDF), College ID Card, Grade Sheets',
  });

  // Schedule rounds state
  const [schedules, setSchedules] = useState<PlacementScheduleItem[]>([
    {
      round_type: 'ONLINE_ASSESSMENT',
      round_order: 1,
      title: 'Online Aptitude & Coding Test',
      start_time: '',
      end_time: '',
      is_online: true,
      meeting_link: 'https://assessment.company.com/login',
      instructions: 'Proctored 90-minute online coding test. Keep webcam active.',
    },
  ]);

  // Query stats
  const { data: stats } = useQuery({
    queryKey: ['placement-dashboard-stats'],
    queryFn: placementsApi.getDashboardStats,
  });

  // Query drives
  const { data: drives = [], isLoading: drivesLoading } = useQuery({
    queryKey: ['admin-placement-drives', statusFilter],
    queryFn: () =>
      placementsApi.listDrives(statusFilter === 'ALL' ? undefined : { status: statusFilter }),
  });

  // Query departments for checklist
  const { data: departments = [] } = useQuery<DepartmentResponse[]>({
    queryKey: ['departments-list'],
    queryFn: departmentsApi.getAll,
  });

  // Mutations
  const createDriveMutation = useMutation({
    mutationFn: ({ directPublish }: { directPublish: boolean }) => {
      const payload = {
        ...formData,
        eligible_department_ids:
          formData.eligible_department_ids.length > 0 ? formData.eligible_department_ids : undefined,
        schedules: schedules.filter((s) => s.title && s.start_time && s.end_time),
      };
      return placementsApi.createDrive(payload, directPublish);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-placement-drives'] });
      queryClient.invalidateQueries({ queryKey: ['placement-dashboard-stats'] });
      setIsCreateModalOpen(false);
      resetForm();
    },
    onError: (err) => {
      const msg = isAxiosError(err) ? err.response?.data?.detail : String(err);
      alert(`Failed to create placement drive: ${msg}`);
    },
  });

  const publishMutation = useMutation({
    mutationFn: (id: number) => placementsApi.publishDrive(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-placement-drives'] });
      queryClient.invalidateQueries({ queryKey: ['placement-dashboard-stats'] });
      closeActionModal();
    },
    onError: (err) => {
      const msg = isAxiosError(err) ? err.response?.data?.detail : String(err);
      alert(`Publish failed: ${msg}`);
    },
  });

  const postponeMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      placementsApi.postponeDrive(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-placement-drives'] });
      queryClient.invalidateQueries({ queryKey: ['placement-dashboard-stats'] });
      closeActionModal();
    },
    onError: (err) => {
      const msg = isAxiosError(err) ? err.response?.data?.detail : String(err);
      alert(`Postpone failed: ${msg}`);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      placementsApi.cancelDrive(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-placement-drives'] });
      queryClient.invalidateQueries({ queryKey: ['placement-dashboard-stats'] });
      closeActionModal();
    },
    onError: (err) => {
      const msg = isAxiosError(err) ? err.response?.data?.detail : String(err);
      alert(`Cancel failed: ${msg}`);
    },
  });

  const closeMutation = useMutation({
    mutationFn: (id: number) => placementsApi.closeDrive(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-placement-drives'] });
      queryClient.invalidateQueries({ queryKey: ['placement-dashboard-stats'] });
    },
    onError: (err) => {
      const msg = isAxiosError(err) ? err.response?.data?.detail : String(err);
      alert(`Close failed: ${msg}`);
    },
  });

  const upsertRecordMutation = useMutation({
    mutationFn: placementsApi.upsertAcademicRecord,
    onSuccess: () => {
      alert('Student academic metrics saved successfully.');
      setIsRecordModalOpen(false);
    },
    onError: (err) => {
      const msg = isAxiosError(err) ? err.response?.data?.detail : String(err);
      alert(`Save failed: ${msg}`);
    },
  });

  const resetForm = () => {
    setFormData({
      company_name: '',
      company_description: '',
      company_website: '',
      title: '',
      job_role: '',
      job_description: '',
      job_type: 'FULL_TIME',
      work_location: 'Bengaluru / Hybrid',
      compensation_details: 'CTC: 12 LPA',
      tier: 'DREAM',
      eligible_department_ids: [],
      graduation_year: 2026,
      min_cgpa: 7.0,
      grading_scale: 10.0,
      max_active_backlogs: 0,
      max_total_backlogs: 1,
      allowed_genders: 'ALL',
      application_deadline: '',
      application_link: '',
      application_instructions: 'Complete application on the company portal with resume and transcripts.',
      required_documents: 'Resume (PDF), College ID Card, Grade Sheets',
    });
    setSchedules([]);
  };

  const closeActionModal = () => {
    setActionModal({ isOpen: false, type: null, driveId: null, driveTitle: '', reason: '' });
  };

  // Filtered drives
  const filteredDrives = useMemo(() => {
    return drives.filter((d) => {
      if (!searchTerm) return true;
      const s = searchTerm.toLowerCase();
      return (
        d.company_name.toLowerCase().includes(s) ||
        d.title.toLowerCase().includes(s) ||
        d.job_role.toLowerCase().includes(s)
      );
    });
  }, [drives, searchTerm]);

  // Table columns
  const driveColumns: Column<PlacementDriveItem>[] = [
    {
      header: 'Company & Role',
      render: (row) => (
        <div>
          <div className="font-semibold text-gray-900">{row.company_name}</div>
          <div className="text-xs text-blue-600 font-medium">{row.job_role}</div>
          <div className="text-xs text-gray-500 line-clamp-1">{row.title}</div>
        </div>
      ),
    },
    {
      header: 'Type & Package',
      render: (row) => (
        <div>
          <span className="inline-block px-2 py-0.5 text-xs font-medium rounded bg-gray-100 text-gray-800">
            {row.job_type.replace('_', ' ')}
          </span>
          <div className="text-xs font-semibold text-emerald-700 mt-1">
            {row.compensation_details || 'Undisclosed'}
          </div>
        </div>
      ),
    },
    {
      header: 'Eligibility Criteria',
      render: (row) => (
        <div className="text-xs text-gray-600 space-y-0.5">
          <div>
            CGPA: <span className="font-semibold text-gray-800">{row.min_cgpa ? `${row.min_cgpa.toFixed(2)}` : 'Any'}</span>
          </div>
          <div>
            Batch: <span className="font-semibold text-gray-800">{row.graduation_year || 'Any'}</span>
          </div>
          <div>
            Max Backlogs: <span className="font-semibold text-gray-800">{row.max_active_backlogs ?? 'Any'}</span>
          </div>
        </div>
      ),
    },
    {
      header: 'Deadline',
      render: (row) => {
        const dl = new Date(row.application_deadline);
        return (
          <div className="text-xs">
            <div className={`font-medium ${row.is_deadline_passed ? 'text-red-600' : 'text-gray-900'}`}>
              {dl.toLocaleDateString()} {dl.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </div>
            {row.is_deadline_passed && (
              <span className="text-[10px] uppercase font-bold text-red-500">Expired</span>
            )}
          </div>
        );
      },
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
      render: (row) => (
        <div className="flex items-center space-x-1.5">
          <button
            onClick={() => {
              setSelectedDrive(row);
              setIsDetailModalOpen(true);
            }}
            className="p-1 text-gray-500 hover:text-blue-600 rounded"
            title="View Details"
          >
            <Eye size={16} />
          </button>
          {row.status === 'DRAFT' && (
            <button
              onClick={() =>
                setActionModal({
                  isOpen: true,
                  type: 'publish',
                  driveId: row.id,
                  driveTitle: row.title,
                  reason: '',
                })
              }
              className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"
              title="Direct Publish"
            >
              <Send size={16} />
            </button>
          )}
          {row.status === 'PUBLISHED' && (
            <>
              <button
                onClick={() =>
                  setActionModal({
                    isOpen: true,
                    type: 'postpone',
                    driveId: row.id,
                    driveTitle: row.title,
                    reason: '',
                  })
                }
                className="p-1 text-amber-600 hover:bg-amber-50 rounded"
                title="Postpone Drive"
              >
                <Clock size={16} />
              </button>
              <button
                onClick={() => closeMutation.mutate(row.id)}
                className="p-1 text-gray-600 hover:bg-gray-100 rounded text-xs font-semibold"
                title="Close Applications"
              >
                Close
              </button>
            </>
          )}
          {['DRAFT', 'PUBLISHED', 'POSTPONED'].includes(row.status) && (
            <button
              onClick={() =>
                setActionModal({
                  isOpen: true,
                  type: 'cancel',
                  driveId: row.id,
                  driveTitle: row.title,
                  reason: '',
                })
              }
              className="p-1 text-red-600 hover:bg-red-50 rounded"
              title="Cancel Drive"
            >
              <Ban size={16} />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="CDC Placement Management & Recruitment Hub"
        subtitle="Coordinate campus placement drives, manage structured eligibility, publish schedules, and evaluate student candidate pools."
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsRecordModalOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 shadow-sm transition-colors"
            >
              <GraduationCap size={16} />
              Student Academic Metrics
            </button>
            <button
              onClick={() => setIsCreateModalOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 shadow-sm transition-colors"
            >
              <Plus size={16} />
              New Placement Drive
            </button>
          </div>
        }
      />

      {/* KPI Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard
          label="Total Drives"
          value={stats?.total_drives ?? 0}
          icon={<Briefcase size={18} className="text-blue-600" />}
          sub="All recorded drives"
        />
        <StatCard
          label="Published / Active"
          value={stats?.published_drives ?? 0}
          icon={<CheckCircle2 size={18} className="text-emerald-600" />}
          sub="Visible to candidates"
        />
        <StatCard
          label="Upcoming Deadlines"
          value={stats?.upcoming_deadlines_count ?? 0}
          icon={<Clock size={18} className="text-amber-600" />}
          sub="Next 7 days"
        />
        <StatCard
          label="Draft Drives"
          value={stats?.draft_drives ?? 0}
          icon={<AlertTriangle size={18} className="text-purple-600" />}
          sub="Unpublished drafts"
        />
        <StatCard
          label="Postponed"
          value={stats?.postponed_drives ?? 0}
          icon={<Clock size={18} className="text-orange-600" />}
          sub="Rescheduled drives"
        />
        <StatCard
          label="Closed Drives"
          value={stats?.closed_drives ?? 0}
          icon={<Ban size={18} className="text-gray-600" />}
          sub="Completed/Closed"
        />
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex space-x-6">
          <button
            onClick={() => setActiveTab('drives')}
            className={`py-3 text-sm font-semibold border-b-2 flex items-center gap-2 ${
              activeTab === 'drives'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            <Briefcase size={16} />
            Placement Drives Directory
          </button>
          <button
            onClick={() => setActiveTab('academic_records')}
            className={`py-3 text-sm font-semibold border-b-2 flex items-center gap-2 ${
              activeTab === 'academic_records'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            <GraduationCap size={16} />
            Academic Records & Grading Scales
          </button>
        </nav>
      </div>

      {activeTab === 'drives' && (
        <div className="space-y-4">
          {/* Filters & Search */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white p-3 rounded-xl border border-gray-200 shadow-sm">
            <div className="relative w-full sm:w-80">
              <Search size={16} className="absolute left-3 top-2.5 text-gray-400" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search by company, role or title..."
                className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>

            <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto">
              {['ALL', 'PUBLISHED', 'DRAFT', 'POSTPONED', 'CLOSED', 'CANCELLED'].map((st) => (
                <button
                  key={st}
                  onClick={() => setStatusFilter(st)}
                  className={`px-3 py-1 text-xs font-semibold rounded-lg transition-colors ${
                    statusFilter === st
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>
          </div>

          {/* Drives Table */}
          <DataTable<PlacementDriveItem>
            data={filteredDrives}
            columns={driveColumns}
            isLoading={drivesLoading}
            isError={false}
            keyExtractor={(d) => d.id}
            emptyMessage="No placement drives found matching filter criteria."
          />
        </div>
      )}

      {activeTab === 'academic_records' && (
        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-gray-900">Student Placement Academic Verification</h3>
              <p className="text-xs text-gray-500">Authoritative records used by the deterministic eligibility engine.</p>
            </div>
            <button
              onClick={() => setIsRecordModalOpen(true)}
              className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700"
            >
              Verify / Add Student Metrics
            </button>
          </div>
          <p className="text-sm text-gray-600">
            Use the form modal to enter or update verified student CGPA, active backlogs, graduation year, and grading scale. Missing records cause candidate eligibility checks to fail closed with <code>CANNOT_DETERMINE</code>.
          </p>
        </div>
      )}

      {/* CREATE DRIVE MODAL */}
      <FormModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        title="Create Campus Placement Drive"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createDriveMutation.mutate({ directPublish: false });
          }}
          className="space-y-4 max-h-[75vh] overflow-y-auto px-1"
        >
          {/* Company details */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Company Name *</label>
              <input
                type="text"
                required
                value={formData.company_name}
                onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
                className="w-full px-3 py-1.5 text-sm border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Google / Microsoft / Amazon"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Official Website</label>
              <input
                type="url"
                value={formData.company_website}
                onChange={(e) => setFormData({ ...formData, company_website: e.target.value })}
                className="w-full px-3 py-1.5 text-sm border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="https://company.com/careers"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Drive Title *</label>
              <input
                type="text"
                required
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                className="w-full px-3 py-1.5 text-sm border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Software Development Engineer 2026"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Job Role *</label>
              <input
                type="text"
                required
                value={formData.job_role}
                onChange={(e) => setFormData({ ...formData, job_role: e.target.value })}
                className="w-full px-3 py-1.5 text-sm border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Graduate Engineer Trainee (GET)"
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Job Type</label>
              <select
                value={formData.job_type}
                onChange={(e) => setFormData({ ...formData, job_type: e.target.value as any })}
                className="w-full px-3 py-1.5 text-sm border rounded-lg"
              >
                <option value="FULL_TIME">Full Time</option>
                <option value="INTERNSHIP">Internship</option>
                <option value="INTERN_PLUS_FULL_TIME">Intern + Full Time</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Compensation / Package</label>
              <input
                type="text"
                value={formData.compensation_details}
                onChange={(e) => setFormData({ ...formData, compensation_details: e.target.value })}
                className="w-full px-3 py-1.5 text-sm border rounded-lg"
                placeholder="CTC: 14.5 LPA"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Location</label>
              <input
                type="text"
                value={formData.work_location}
                onChange={(e) => setFormData({ ...formData, work_location: e.target.value })}
                className="w-full px-3 py-1.5 text-sm border rounded-lg"
                placeholder="Bengaluru / Remote"
              />
            </div>
          </div>

          {/* Structured Eligibility Rules */}
          <div className="bg-blue-50/50 p-3 rounded-lg border border-blue-100 space-y-3">
            <h4 className="text-xs font-bold text-blue-900 uppercase">Deterministic Eligibility Rules</h4>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Min CGPA</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="10"
                  value={formData.min_cgpa}
                  onChange={(e) => setFormData({ ...formData, min_cgpa: parseFloat(e.target.value) || 0 })}
                  className="w-full px-3 py-1.5 text-sm border rounded-lg"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Graduation Batch Year</label>
                <input
                  type="number"
                  value={formData.graduation_year}
                  onChange={(e) => setFormData({ ...formData, graduation_year: parseInt(e.target.value) || 2026 })}
                  className="w-full px-3 py-1.5 text-sm border rounded-lg"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Max Active Backlogs</label>
                <input
                  type="number"
                  min="0"
                  value={formData.max_active_backlogs}
                  onChange={(e) => setFormData({ ...formData, max_active_backlogs: parseInt(e.target.value) || 0 })}
                  className="w-full px-3 py-1.5 text-sm border rounded-lg"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Eligible Branches / Departments</label>
              <div className="grid grid-cols-3 gap-1.5 max-h-24 overflow-y-auto">
                {departments.map((dept) => (
                  <label key={dept.id} className="flex items-center gap-1.5 text-xs text-gray-700">
                    <input
                      type="checkbox"
                      checked={formData.eligible_department_ids.includes(dept.id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setFormData({
                            ...formData,
                            eligible_department_ids: [...formData.eligible_department_ids, dept.id],
                          });
                        } else {
                          setFormData({
                            ...formData,
                            eligible_department_ids: formData.eligible_department_ids.filter((id) => id !== dept.id),
                          });
                        }
                      }}
                    />
                    <span className="truncate">{dept.name}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1">Application Deadline *</label>
            <input
              type="datetime-local"
              required
              value={formData.application_deadline}
              onChange={(e) => setFormData({ ...formData, application_deadline: e.target.value })}
              className="w-full px-3 py-1.5 text-sm border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Action buttons */}
          <div className="flex items-center justify-end gap-2 pt-3 border-t">
            <button
              type="button"
              onClick={() => setIsCreateModalOpen(false)}
              className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createDriveMutation.isPending}
              className="px-4 py-2 text-sm text-gray-800 bg-gray-200 hover:bg-gray-300 rounded-lg font-medium"
            >
              Save as Draft
            </button>
            <button
              type="button"
              onClick={() => createDriveMutation.mutate({ directPublish: true })}
              disabled={createDriveMutation.isPending}
              className="px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg font-medium shadow-sm"
            >
              Direct Publish
            </button>
          </div>
        </form>
      </FormModal>

      {/* DETAIL MODAL */}
      <FormModal
        isOpen={isDetailModalOpen}
        onClose={() => setIsDetailModalOpen(false)}
        title={selectedDrive ? `${selectedDrive.company_name} — ${selectedDrive.title}` : 'Drive Details'}
      >
        {selectedDrive && (
          <div className="space-y-4 max-h-[75vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b">
              <div>
                <span className="text-xs uppercase font-bold text-blue-600">{selectedDrive.job_role}</span>
                <div className="text-sm font-semibold text-gray-900">{selectedDrive.compensation_details}</div>
              </div>
              <StatusBadge
                status={selectedDrive.status}
                variant={STATUS_VARIANT_MAP[selectedDrive.status] || 'neutral'}
              />
            </div>

            <div className="space-y-2 text-xs text-gray-700">
              <p><strong>Work Location:</strong> {selectedDrive.work_location || 'Not specified'}</p>
              <p><strong>Job Type:</strong> {selectedDrive.job_type.replace('_', ' ')}</p>
              <p><strong>Application Deadline:</strong> {new Date(selectedDrive.application_deadline).toLocaleString()}</p>
              {selectedDrive.application_link && (
                <p>
                  <strong>Apply Link:</strong>{' '}
                  <a href={selectedDrive.application_link} target="_blank" rel="noreferrer" className="text-blue-600 underline">
                    {selectedDrive.application_link}
                  </a>
                </p>
              )}
            </div>

            {/* Selection rounds */}
            <div>
              <h4 className="text-xs font-bold text-gray-800 uppercase mb-2">Selection Rounds ({selectedDrive.schedules.length})</h4>
              {selectedDrive.schedules.length === 0 ? (
                <p className="text-xs text-gray-500 italic">No schedule rounds added yet.</p>
              ) : (
                <div className="space-y-2">
                  {selectedDrive.schedules.map((s, idx) => (
                    <div key={idx} className="p-2.5 rounded-lg bg-gray-50 border border-gray-200 text-xs">
                      <div className="font-semibold text-gray-900">{s.title} ({s.round_type})</div>
                      <div className="text-gray-500">
                        {new Date(s.start_time).toLocaleString()} to {new Date(s.end_time).toLocaleTimeString()}
                      </div>
                      <div className="text-gray-600 mt-0.5">
                        Venue: {s.room_number || s.venue_name || (s.is_online ? 'Online Platform' : 'TBA')}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="pt-3 border-t flex justify-end">
              <button
                type="button"
                onClick={() => setIsDetailModalOpen(false)}
                className="px-4 py-1.5 text-xs font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </FormModal>

      {/* ACTION MODAL (Publish, Postpone, Cancel) */}
      <FormModal
        isOpen={actionModal.isOpen}
        onClose={closeActionModal}
        title={
          actionModal.type === 'publish'
            ? 'Publish Placement Drive'
            : actionModal.type === 'postpone'
            ? 'Postpone Placement Drive'
            : 'Cancel Placement Drive'
        }
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-700">
            {actionModal.type === 'publish'
              ? `Are you sure you want to directly publish "${actionModal.driveTitle}"? All eligible students will receive an in-app recruitment notification.`
              : `Please provide a reason for ${actionModal.type === 'postpone' ? 'postponing' : 'cancelling'} "${actionModal.driveTitle}".`}
          </p>

          {actionModal.type !== 'publish' && (
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Reason *</label>
              <textarea
                required
                rows={3}
                value={actionModal.reason}
                onChange={(e) => setActionModal({ ...actionModal, reason: e.target.value })}
                placeholder="Reason for schedule adjustment..."
                className="w-full px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-blue-500"
              />
            </div>
          )}

          <div className="flex justify-end gap-2 pt-3 border-t">
            <button
              type="button"
              onClick={closeActionModal}
              className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
            >
              Back
            </button>
            <button
              type="button"
              onClick={() => {
                if (!actionModal.driveId) return;
                if (actionModal.type === 'publish') {
                  publishMutation.mutate(actionModal.driveId);
                } else if (actionModal.type === 'postpone') {
                  if (!actionModal.reason.trim()) {
                    alert('Reason is required.');
                    return;
                  }
                  postponeMutation.mutate({ id: actionModal.driveId, reason: actionModal.reason });
                } else if (actionModal.type === 'cancel') {
                  if (!actionModal.reason.trim()) {
                    alert('Reason is required.');
                    return;
                  }
                  cancelMutation.mutate({ id: actionModal.driveId, reason: actionModal.reason });
                }
              }}
              className={`px-4 py-2 text-sm font-medium text-white rounded-lg shadow-sm ${
                actionModal.type === 'cancel'
                  ? 'bg-red-600 hover:bg-red-700'
                  : actionModal.type === 'postpone'
                  ? 'bg-amber-600 hover:bg-amber-700'
                  : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              Confirm {actionModal.type === 'publish' ? 'Publish' : actionModal.type === 'postpone' ? 'Postpone' : 'Cancel'}
            </button>
          </div>
        </div>
      </FormModal>

      {/* STUDENT ACADEMIC RECORD MODAL */}
      <FormModal
        isOpen={isRecordModalOpen}
        onClose={() => setIsRecordModalOpen(false)}
        title="Student Placement Academic Record"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            upsertRecordMutation.mutate(academicRecordForm);
          }}
          className="space-y-3"
        >
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1">Student Record ID (PK) *</label>
            <input
              type="number"
              required
              min="1"
              value={academicRecordForm.student_id}
              onChange={(e) => setAcademicRecordForm({ ...academicRecordForm, student_id: parseInt(e.target.value) || 1 })}
              className="w-full px-3 py-1.5 text-sm border rounded-lg"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">CGPA</label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="10"
                value={academicRecordForm.cgpa}
                onChange={(e) => setAcademicRecordForm({ ...academicRecordForm, cgpa: parseFloat(e.target.value) || 0 })}
                className="w-full px-3 py-1.5 text-sm border rounded-lg"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Grading Scale</label>
              <input
                type="number"
                step="0.1"
                value={academicRecordForm.grading_scale}
                onChange={(e) => setAcademicRecordForm({ ...academicRecordForm, grading_scale: parseFloat(e.target.value) || 10.0 })}
                className="w-full px-3 py-1.5 text-sm border rounded-lg"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Active Backlogs</label>
              <input
                type="number"
                min="0"
                value={academicRecordForm.active_backlogs}
                onChange={(e) => setAcademicRecordForm({ ...academicRecordForm, active_backlogs: parseInt(e.target.value) || 0 })}
                className="w-full px-3 py-1.5 text-sm border rounded-lg"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">Graduation Year</label>
              <input
                type="number"
                value={academicRecordForm.graduation_year}
                onChange={(e) => setAcademicRecordForm({ ...academicRecordForm, graduation_year: parseInt(e.target.value) || 2026 })}
                className="w-full px-3 py-1.5 text-sm border rounded-lg"
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-3 border-t">
            <button
              type="button"
              onClick={() => setIsRecordModalOpen(false)}
              className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={upsertRecordMutation.isPending}
              className="px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg font-medium shadow-sm"
            >
              Save Record
            </button>
          </div>
        </form>
      </FormModal>
    </div>
  );
}
