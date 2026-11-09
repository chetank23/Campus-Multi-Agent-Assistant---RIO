/**
 * frontend/src/pages/admin/AdminSettingsPage.tsx
 * ----------------------------------------------
 * Comprehensive Admin Settings & Operational Data Management:
 * 1. General Settings (Institution details, scheduling defaults, notifications)
 * 2. Data Management (Safe Operational Data Management — preview, category clear, audit tracking)
 * 3. User & Access Settings (RBAC overview, account distribution, token expiry)
 * 4. Timetable Settings (Working days Mon-Sat/Mon-Fri, 7 periods + breaks, constraint tuning)
 * 5. System & Integration Settings (PostgreSQL status, Multi-agent LLM status, Supabase readiness)
 */

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Building2,
  CalendarClock,
  ShieldCheck,
  Database,
  Users,
  CheckCircle2,
  AlertTriangle,
  Trash2,
  RefreshCw,
  Server,
  Sliders,
  Sparkles,
  Loader2,
  X,
} from 'lucide-react';
import { PageHeader, RefreshButton } from '@/components/common';
import { useToast } from '@/context/useToast';
import {
  settingsApi,
  type DataClearPreviewResponse,
} from '@/api/settings';
import { useNotifications } from '@/context/useNotifications';

type SettingsTab = 'general' | 'data' | 'timetable' | 'access' | 'system';

export const AdminSettingsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { refresh: refreshNotifications } = useNotifications();
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<SettingsTab>('general');

  // Notification Toast State (maintains inline toast for backward compatibility with live tests)
  const [toastMessage, setToastMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Data Management Selection State
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [previewData, setPreviewData] = useState<DataClearPreviewResponse | null>(null);
  const [showPreviewModal, setShowPreviewModal] = useState<boolean>(false);
  const [confirmCheckbox, setConfirmCheckbox] = useState<boolean>(false);

  // User form overrides
  const [generalOverrides, setGeneralOverrides] = useState<{
    institution_name?: string;
    campus_name?: string;
    department?: string;
    timezone?: string;
    email_alerts_enabled?: boolean;
    timetable_publish_alerts?: boolean;
    substitution_alerts?: boolean;
  }>({});

  const [timetableOverrides, setTimetableOverrides] = useState<{
    working_days?: 'MON_SAT' | 'MON_FRI';
    max_consecutive_faculty_lectures?: number;
    enable_soft_lab_preference?: boolean;
  }>({});

  // 1. Fetch Full Settings
  const { data: fullSettings, refetch: refetchSettings } = useQuery({
    queryKey: ['admin-full-settings'],
    queryFn: settingsApi.getFullSettings,
  });

  // Derived Form State
  const generalForm = {
    institution_name: generalOverrides.institution_name ?? fullSettings?.general.institution.institution_name ?? 'REVA University',
    campus_name: generalOverrides.campus_name ?? fullSettings?.general.institution.campus_name ?? 'Rukmini Knowledge Park, Kattigenahalli, Yelahanka, Bengaluru',
    department: generalOverrides.department ?? fullSettings?.general.institution.department ?? 'School of Computer Science & Engineering (AI & DS)',
    timezone: generalOverrides.timezone ?? fullSettings?.general.institution.timezone ?? 'Asia/Kolkata',
    email_alerts_enabled: generalOverrides.email_alerts_enabled ?? fullSettings?.general.notifications.email_alerts_enabled ?? true,
    timetable_publish_alerts: generalOverrides.timetable_publish_alerts ?? fullSettings?.general.notifications.timetable_publish_alerts ?? true,
    substitution_alerts: generalOverrides.substitution_alerts ?? fullSettings?.general.notifications.substitution_alerts ?? true,
  };

  const timetableForm = {
    working_days: timetableOverrides.working_days ?? fullSettings?.timetable.working_days ?? 'MON_SAT',
    max_consecutive_faculty_lectures: timetableOverrides.max_consecutive_faculty_lectures ?? fullSettings?.timetable.max_consecutive_faculty_lectures ?? 3,
    enable_soft_lab_preference: timetableOverrides.enable_soft_lab_preference ?? fullSettings?.timetable.enable_soft_lab_preference ?? true,
  };

  // 2. Fetch Data Management Summary
  const { data: dataSummary, isLoading: loadingDataSummary, refetch: refetchDataSummary } = useQuery({
    queryKey: ['admin-data-management-summary'],
    queryFn: settingsApi.getDataManagementSummary,
  });

  // 3. Update General Settings Mutation
  const updateGeneralMutation = useMutation({
    mutationFn: () =>
      settingsApi.updateGeneralSettings({
        institution: {
          institution_name: generalForm.institution_name,
          campus_name: generalForm.campus_name,
          department: generalForm.department,
          timezone: generalForm.timezone,
        },
        notifications: {
          email_alerts_enabled: generalForm.email_alerts_enabled,
          timetable_publish_alerts: generalForm.timetable_publish_alerts,
          substitution_alerts: generalForm.substitution_alerts,
        },
      }),
    onSuccess: () => {
      setToastMessage({ type: 'success', text: 'General settings updated successfully!' });
      toast.success('General institutional settings updated successfully!');
      refetchSettings();
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || 'Failed to update settings.';
      setToastMessage({ type: 'error', text: msg });
      toast.error(`Update failed: ${msg}`);
    },
  });

  // 4. Update Timetable Settings Mutation
  const updateTimetableMutation = useMutation({
    mutationFn: () =>
      settingsApi.updateTimetableSettings({
        working_days: timetableForm.working_days,
        max_consecutive_faculty_lectures: timetableForm.max_consecutive_faculty_lectures,
        enable_soft_lab_preference: timetableForm.enable_soft_lab_preference,
      }),
    onSuccess: () => {
      setToastMessage({ type: 'success', text: 'Timetable defaults saved successfully!' });
      toast.success('Timetable generation defaults saved successfully!');
      refetchSettings();
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || 'Failed to save timetable settings.';
      setToastMessage({ type: 'error', text: msg });
      toast.error(`Save failed: ${msg}`);
    },
  });

  // 5. Data Clear Preview Mutation
  const previewClearMutation = useMutation({
    mutationFn: (args: { categories: string[]; clear_all: boolean }) =>
      settingsApi.previewDataClear(args.categories, args.clear_all),
    onSuccess: (data) => {
      setPreviewData(data);
      setShowPreviewModal(true);
      setConfirmCheckbox(false);
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || 'Failed to generate preview.';
      setToastMessage({ type: 'error', text: msg });
      toast.error(`Preview failed: ${msg}`);
    },
  });

  // 6. Data Clear Execution Mutation
  const executeClearMutation = useMutation({
    mutationFn: (args: { categories: string[]; clear_all: boolean }) =>
      settingsApi.executeDataClear(args.categories, args.clear_all, true),
    onSuccess: async (res) => {
      setShowPreviewModal(false);
      setPreviewData(null);
      setSelectedCategories([]);
      const successText = `Successfully cleared ${res.total_records_deleted} operational records (Audit Log #${res.audit_log_id}).`;
      setToastMessage({
        type: 'success',
        text: successText,
      });
      toast.success(successText, { duration: 6000 });
      // Purge and invalidate all stale queries across the entire application
      await queryClient.invalidateQueries();
      refetchDataSummary();
      // Re-sync notifications in real time so the broadcast is immediately visible
      refreshNotifications();
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || 'Failed to execute clear operation.';
      setToastMessage({ type: 'error', text: msg });
      toast.error(`Clear operation failed: ${msg}`);
    },
  });

  const handleToggleCategory = (catId: string) => {
    setSelectedCategories((prev) =>
      prev.includes(catId) ? prev.filter((id) => id !== catId) : [...prev, catId]
    );
  };

  const handleTriggerPreview = (clearAll: boolean) => {
    const cats = clearAll ? (dataSummary?.categories.map((c) => c.category_id) || []) : selectedCategories;
    if (!clearAll && cats.length === 0) {
      setToastMessage({ type: 'error', text: 'Please select at least one generated data category to clear.' });
      return;
    }
    previewClearMutation.mutate({ categories: cats, clear_all: clearAll });
  };

  const tabs = [
    { id: 'general', label: 'General Settings', icon: <Sliders size={16} /> },
    { id: 'data', label: 'Data Management', icon: <Database size={16} />, highlight: true },
    { id: 'timetable', label: 'Timetable Settings', icon: <CalendarClock size={16} /> },
    { id: 'access', label: 'User & Access', icon: <Users size={16} /> },
    { id: 'system', label: 'System & Integrations', icon: <Server size={16} /> },
  ];

  return (
    <div className="space-y-6 pb-12">
      {/* ── Page Header ──────────────────────────────────────────────────── */}
      <PageHeader
        title="Settings & Data Management"
        subtitle="Configure institutional defaults, safe operational data lifecycle, timetable parameters, and system integrations."
        refresh={
          <RefreshButton
            entityName="Settings & Operational Summary"
            queryKeys={[['admin-system-settings'], ['admin-data-management-summary']]}
            label="Refresh Settings"
            variant="outline"
          />
        }
      />

      {/* ── Global Toast ─────────────────────────────────────────────────── */}
      {toastMessage && (
        <div
          className={`p-4 rounded-xl flex items-center justify-between shadow-sm animate-fadeIn border ${
            toastMessage.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          <div className="flex items-center gap-3">
            {toastMessage.type === 'success' ? (
              <CheckCircle2 size={18} className="text-emerald-600 shrink-0" />
            ) : (
              <AlertTriangle size={18} className="text-rose-600 shrink-0" />
            )}
            <span className="text-sm font-medium">{toastMessage.text}</span>
          </div>
          <button
            onClick={() => setToastMessage(null)}
            className="text-xs font-semibold hover:underline ml-4"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ── Navigation Tabs ──────────────────────────────────────────────── */}
      <div className="border-b border-slate-200 bg-white rounded-t-xl px-4 pt-2 shadow-sm">
        <div className="flex items-center gap-2 overflow-x-auto">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as SettingsTab)}
                className={`flex items-center gap-2 px-4 py-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
                  isActive
                    ? 'border-blue-600 text-blue-600 bg-blue-50/50 rounded-t-lg'
                    : 'border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300'
                } ${tab.highlight ? 'relative' : ''}`}
              >
                {tab.icon}
                <span>{tab.label}</span>
                {tab.highlight && (
                  <span className="ml-1.5 px-1.5 py-0.5 text-[10px] font-bold uppercase rounded bg-rose-100 text-rose-700">
                    Safe Reset
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Tab Content: GENERAL ─────────────────────────────────────────── */}
      {activeTab === 'general' && (
        <div className="bg-white rounded-b-xl rounded-t-none shadow-sm border border-slate-200 p-6 space-y-6">
          <div className="border-b border-slate-100 pb-4">
            <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Building2 size={18} className="text-blue-600" />
              Institution Profile & Academic Context
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              Active identity and academic jurisdiction for campus scheduling operations.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                Institution Name
              </label>
              <input
                type="text"
                value={generalForm.institution_name}
                onChange={(e) => setGeneralOverrides((prev) => ({ ...prev, institution_name: e.target.value }))}
                className="w-full text-xs px-3.5 py-2.5 rounded-lg border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                Department
              </label>
              <input
                type="text"
                value={generalForm.department}
                onChange={(e) => setGeneralOverrides((prev) => ({ ...prev, department: e.target.value }))}
                className="w-full text-xs px-3.5 py-2.5 rounded-lg border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                Campus Location
              </label>
              <input
                type="text"
                value={generalForm.campus_name}
                onChange={(e) => setGeneralOverrides((prev) => ({ ...prev, campus_name: e.target.value }))}
                className="w-full text-xs px-3.5 py-2.5 rounded-lg border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                System Timezone
              </label>
              <select
                value={generalForm.timezone}
                onChange={(e) => setGeneralOverrides((prev) => ({ ...prev, timezone: e.target.value }))}
                className="w-full text-xs px-3.5 py-2.5 rounded-lg border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none"
              >
                <option value="Asia/Kolkata">Asia/Kolkata (IST, UTC+05:30)</option>
                <option value="UTC">UTC</option>
              </select>
            </div>
          </div>

          <div className="border-t border-slate-100 pt-5 space-y-3">
            <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
              Notification Preferences
            </h4>
            <div className="space-y-2.5">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={generalForm.email_alerts_enabled}
                  onChange={(e) => setGeneralOverrides((prev) => ({ ...prev, email_alerts_enabled: e.target.checked }))}
                  className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                />
                <span className="text-xs text-slate-700 font-medium">
                  Enable system email and outbox delivery dispatch
                </span>
              </label>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={generalForm.timetable_publish_alerts}
                  onChange={(e) => setGeneralOverrides((prev) => ({ ...prev, timetable_publish_alerts: e.target.checked }))}
                  className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                />
                <span className="text-xs text-slate-700 font-medium">
                  Automatically broadcast notifications to Faculty and Students on timetable publication
                </span>
              </label>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={generalForm.substitution_alerts}
                  onChange={(e) => setGeneralOverrides((prev) => ({ ...prev, substitution_alerts: e.target.checked }))}
                  className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                />
                <span className="text-xs text-slate-700 font-medium">
                  Notify substitute faculty upon administrative approval
                </span>
              </label>
            </div>
          </div>

          <div className="flex justify-end pt-4 border-t border-slate-100">
            <button
              onClick={() => updateGeneralMutation.mutate()}
              disabled={updateGeneralMutation.isPending}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shadow-sm focus:ring-2 focus:ring-blue-500 transition-all disabled:opacity-50"
            >
              {updateGeneralMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <SaveIcon />}
              Save General Settings
            </button>
          </div>
        </div>
      )}

      {/* ── Tab Content: DATA MANAGEMENT (CRITICAL) ──────────────────────── */}
      {activeTab === 'data' && (
        <div className="space-y-6">
          {/* Safeguard Assurance Banner */}
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5 shadow-sm">
            <div className="flex items-start gap-3">
              <ShieldCheck size={22} className="text-emerald-600 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-bold text-emerald-900">
                  Strict Master Data Safeguard Active
                </h4>
                <p className="text-xs text-emerald-700 mt-1 leading-relaxed">
                  Data clearing operations manage <strong>ONLY generated operational data</strong> (temporary schedules, bookings, and request logs). Academic master entities (Departments, Programs, Semesters, Sections, 18 Courses, Buildings, 225 Rooms, 10 Faculty, 60 Students, and 72 Accounts) are <strong>strictly protected and will never be deleted</strong>.
                </p>
                <div className="mt-2.5 flex items-center gap-2 text-[11px] font-semibold text-emerald-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                  Authoritative Baseline: {dataSummary?.authoritative_dataset || 'AIDS-A Master Workbook'}
                </div>
              </div>
            </div>
          </div>

          {/* Operational Categories Grid */}
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-6">
            <div className="flex items-center justify-between flex-wrap gap-4 border-b border-slate-100 pb-4">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <Database size={18} className="text-blue-600" />
                  Generated Operational Data Management
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  Select operational categories to clear, or purge all generated records safely in a single transaction.
                </p>
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => refetchDataSummary()}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
                >
                  <RefreshCw size={13} className={loadingDataSummary ? 'animate-spin' : ''} />
                  Refresh Counts
                </button>
              </div>
            </div>

            {/* Categories List */}
            <div className="space-y-4">
              {dataSummary?.categories.map((cat) => {
                const isSelected = selectedCategories.includes(cat.category_id);
                return (
                  <div
                    key={cat.category_id}
                    className={`border rounded-xl p-4 transition-all ${
                      isSelected
                        ? 'border-blue-400 bg-blue-50/30 ring-1 ring-blue-300'
                        : 'border-slate-200 bg-white hover:border-slate-300'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          id={`cat-${cat.category_id}`}
                          checked={isSelected}
                          onChange={() => handleToggleCategory(cat.category_id)}
                          className="mt-1 rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-4 w-4 cursor-pointer"
                        />
                        <div>
                          <label
                            htmlFor={`cat-${cat.category_id}`}
                            className="text-xs font-bold text-slate-900 cursor-pointer flex items-center gap-2"
                          >
                            {cat.category_name}
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
                              {cat.total_records} record{cat.total_records === 1 ? '' : 's'}
                            </span>
                          </label>
                          <p className="text-xs text-slate-500 mt-0.5">{cat.description}</p>
                          {cat.warning && (
                            <p className="text-[11px] text-amber-700 mt-1 flex items-center gap-1 font-medium">
                              <AlertTriangle size={12} className="shrink-0" />
                              {cat.warning}
                            </p>
                          )}
                        </div>
                      </div>

                      {/* Sub-table Breakdown */}
                      <div className="text-right text-[11px] text-slate-400 shrink-0 hidden sm:block">
                        {cat.tables.map((t) => (
                          <div key={t.table_name}>
                            <span className="text-slate-600 font-medium">{t.display_name}:</span> {t.count}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Action Bar */}
            <div className="border-t border-slate-100 pt-5 flex items-center justify-between flex-wrap gap-4">
              <div className="text-xs text-slate-500">
                <strong>{selectedCategories.length}</strong> categor{selectedCategories.length === 1 ? 'y' : 'ies'} selected
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => handleTriggerPreview(false)}
                  disabled={selectedCategories.length === 0 || previewClearMutation.isPending}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs font-semibold text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 shadow-sm transition-all disabled:opacity-40"
                >
                  <Trash2 size={14} />
                  CLEAR SELECTED GENERATED DATA
                </button>

                <button
                  type="button"
                  onClick={() => handleTriggerPreview(true)}
                  disabled={previewClearMutation.isPending}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-xs font-bold text-white bg-rose-600 hover:bg-rose-700 shadow-sm focus:ring-2 focus:ring-rose-500 transition-all disabled:opacity-40"
                >
                  <AlertTriangle size={14} />
                  CLEAR ALL GENERATED OPERATIONAL DATA
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Tab Content: TIMETABLE SETTINGS ──────────────────────────────── */}
      {activeTab === 'timetable' && (
        <div className="bg-white rounded-b-xl rounded-t-none shadow-sm border border-slate-200 p-6 space-y-6">
          <div className="border-b border-slate-100 pb-4">
            <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <CalendarClock size={18} className="text-blue-600" />
              Canonical Timetable Scheduling Parameters
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              Solver constraints, canonical working days, and instructional interval standards.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                Default Working Days Architecture
              </label>
              <select
                value={timetableForm.working_days}
                onChange={(e) =>
                  setTimetableOverrides((prev) => ({
                    ...prev,
                    working_days: e.target.value as 'MON_SAT' | 'MON_FRI',
                  }))
                }
                className="w-full text-xs px-3.5 py-2.5 rounded-lg border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none"
              >
                <option value="MON_SAT">Monday–Saturday (6 Teaching Days, 42 Periods)</option>
                <option value="MON_FRI">Monday–Friday (5 Teaching Days, 35 Periods)</option>
              </select>
              <p className="text-[11px] text-slate-500 mt-1">
                Standard REVA institutional default is Monday through Saturday.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                Max Consecutive Faculty Lectures
              </label>
              <input
                type="number"
                min={1}
                max={5}
                value={timetableForm.max_consecutive_faculty_lectures}
                onChange={(e) =>
                  setTimetableOverrides((prev) => ({
                    ...prev,
                    max_consecutive_faculty_lectures: Number(e.target.value),
                  }))
                }
                className="w-full text-xs px-3.5 py-2.5 rounded-lg border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
              <p className="text-[11px] text-slate-500 mt-1">
                Hard constraint in OR-Tools solver preventing faculty burnout.
              </p>
            </div>

            <div className="md:col-span-2">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={timetableForm.enable_soft_lab_preference}
                  onChange={(e) =>
                    setTimetableOverrides((prev) => ({
                      ...prev,
                      enable_soft_lab_preference: e.target.checked,
                    }))
                  }
                  className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                />
                <span className="text-xs text-slate-700 font-medium">
                  Enable afternoon lab preference (prioritize laboratory blocks from Period 5 onwards)
                </span>
              </label>
            </div>
          </div>

          {/* Standard Period Timings Breakdown */}
          <div className="border-t border-slate-100 pt-5 space-y-3">
            <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
              Authoritative Period Timings (Standard 9-Interval Schedule)
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                <span className="font-semibold text-slate-800 block">Morning Block</span>
                <span className="text-slate-500 text-[11px]">Period 1: 08:30–09:25</span>
                <br />
                <span className="text-slate-500 text-[11px]">Period 2: 09:25–10:20</span>
              </div>
              <div className="p-3 bg-amber-50/60 rounded-lg border border-amber-200">
                <span className="font-semibold text-amber-900 block">Tea Break</span>
                <span className="text-amber-700 text-[11px]">10:20–10:40 (20 mins)</span>
                <br />
                <span className="font-semibold text-slate-800 block mt-1">Mid-day Block</span>
                <span className="text-slate-500 text-[11px]">Period 3: 10:40–11:35</span>
                <br />
                <span className="text-slate-500 text-[11px]">Period 4: 11:35–12:30</span>
              </div>
              <div className="p-3 bg-amber-50/60 rounded-lg border border-amber-200">
                <span className="font-semibold text-amber-900 block">Lunch Break</span>
                <span className="text-amber-700 text-[11px]">12:30–13:30 (60 mins)</span>
                <br />
                <span className="font-semibold text-slate-800 block mt-1">Afternoon Block</span>
                <span className="text-slate-500 text-[11px]">Period 5: 13:30–14:25</span>
                <br />
                <span className="text-slate-500 text-[11px]">Period 6: 14:25–15:20</span>
                <br />
                <span className="text-slate-500 text-[11px]">Period 7: 15:20–16:15</span>
              </div>
            </div>
          </div>

          <div className="flex justify-end pt-4 border-t border-slate-100">
            <button
              onClick={() => updateTimetableMutation.mutate()}
              disabled={updateTimetableMutation.isPending}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shadow-sm focus:ring-2 focus:ring-blue-500 transition-all disabled:opacity-50"
            >
              {updateTimetableMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <SaveIcon />}
              Save Timetable Settings
            </button>
          </div>
        </div>
      )}

      {/* ── Tab Content: USER & ACCESS ───────────────────────────────────── */}
      {activeTab === 'access' && (
        <div className="bg-white rounded-b-xl rounded-t-none shadow-sm border border-slate-200 p-6 space-y-6">
          <div className="border-b border-slate-100 pb-4">
            <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Users size={18} className="text-blue-600" />
              User Accounts & Role Distribution
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              Active identity census and session policy governance.
            </p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="p-4 bg-purple-50 rounded-xl border border-purple-100 text-center">
              <span className="text-2xl font-bold text-purple-700">
                {fullSettings?.access.super_admin_count ?? 1}
              </span>
              <span className="text-xs font-semibold text-purple-900 block mt-1">Super Admin</span>
              <span className="text-[10px] text-purple-600">Curriculum Governance</span>
            </div>
            <div className="p-4 bg-blue-50 rounded-xl border border-blue-100 text-center">
              <span className="text-2xl font-bold text-blue-700">
                {fullSettings?.access.admin_count ?? 1}
              </span>
              <span className="text-xs font-semibold text-blue-900 block mt-1">System Admin</span>
              <span className="text-[10px] text-blue-600">Timetable & Operations</span>
            </div>
            <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-100 text-center">
              <span className="text-2xl font-bold text-emerald-700">
                {fullSettings?.access.faculty_count ?? 10}
              </span>
              <span className="text-xs font-semibold text-emerald-900 block mt-1">Faculty</span>
              <span className="text-[10px] text-emerald-600">Teaching Roster</span>
            </div>
            <div className="p-4 bg-amber-50 rounded-xl border border-amber-100 text-center">
              <span className="text-2xl font-bold text-amber-700">
                {fullSettings?.access.student_count ?? 60}
              </span>
              <span className="text-xs font-semibold text-amber-900 block mt-1">Students</span>
              <span className="text-[10px] text-amber-600">AIDS-A Enrolled</span>
            </div>
          </div>

          <div className="border-t border-slate-100 pt-5 space-y-3">
            <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
              Session & Security Policy
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs text-slate-700">
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                <span className="font-semibold block text-slate-900">Access Token Expiry</span>
                <span className="text-slate-500 text-[11px]">20 minutes (stateless JWT HS256)</span>
              </div>
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                <span className="font-semibold block text-slate-900">Refresh Token Expiry</span>
                <span className="text-slate-500 text-[11px]">7 days (persisted session)</span>
              </div>
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                <span className="font-semibold block text-slate-900">Total Provisioned Accounts</span>
                <span className="text-slate-500 text-[11px]">72 Authoritative Accounts</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Tab Content: SYSTEM & INTEGRATIONS ───────────────────────────── */}
      {activeTab === 'system' && (
        <div className="bg-white rounded-b-xl rounded-t-none shadow-sm border border-slate-200 p-6 space-y-6">
          <div className="border-b border-slate-100 pb-4">
            <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Server size={18} className="text-blue-600" />
              System Infrastructure & Integration Status
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              Live status for PostgreSQL, Multi-Agent AI system, and cloud databases.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* Database Card */}
            <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Database size={16} className="text-emerald-600" />
                  <span className="text-xs font-bold text-slate-900">PostgreSQL Database</span>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">
                  {fullSettings?.system.database_status || 'CONNECTED'}
                </span>
              </div>
              <div className="text-xs text-slate-600 space-y-1">
                <div><strong>Host:</strong> {fullSettings?.system.database_host}</div>
                <div><strong>Port:</strong> {fullSettings?.system.database_port}</div>
                <div><strong>Database:</strong> {fullSettings?.system.database_name}</div>
                <div><strong>Schema:</strong> {fullSettings?.system.database_schema}</div>
              </div>
            </div>

            {/* AI Agent Card */}
            <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Sparkles size={16} className="text-blue-600" />
                  <span className="text-xs font-bold text-slate-900">Multi-Agent Assistant</span>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-800">
                  {fullSettings?.system.ai_agent_status || 'READY'}
                </span>
              </div>
              <div className="text-xs text-slate-600 space-y-1">
                <div><strong>Provider:</strong> {fullSettings?.system.llm_provider}</div>
                <div>
                  <strong>Live API Configured:</strong>{' '}
                  {fullSettings?.system.llm_configured ? (
                    <span className="text-emerald-600 font-semibold">Yes</span>
                  ) : (
                    <span className="text-slate-500">Offline Fallback Active</span>
                  )}
                </div>
                <div><strong>Architecture:</strong> LangGraph Supervisor + Tools</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Dry-Run Confirmation Modal ───────────────────────────────────── */}
      {showPreviewModal && previewData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4 animate-fadeIn">
          <div className="bg-white rounded-2xl shadow-xl max-w-xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-5 border border-slate-200">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-rose-50 rounded-lg text-rose-600">
                  <AlertTriangle size={20} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    Confirm Operational Data Purge
                  </h3>
                  <p className="text-xs text-slate-500">Dry-run preview and dependency verification</p>
                </div>
              </div>
              <button
                onClick={() => setShowPreviewModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X size={18} />
              </button>
            </div>

            {/* Warnings */}
            {previewData.warnings.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 space-y-1.5 text-xs text-amber-900">
                <span className="font-bold flex items-center gap-1.5 text-amber-800">
                  <AlertTriangle size={14} /> Warning Notifications:
                </span>
                <ul className="list-disc list-inside space-y-1 pl-1 text-[11px] text-amber-800">
                  {previewData.warnings.map((w, idx) => (
                    <li key={idx}>{w}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Affected Tables Table */}
            <div className="border border-slate-200 rounded-xl overflow-hidden text-xs">
              <table className="w-full text-left border-collapse">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="p-2.5 font-bold text-slate-700">Affected Table</th>
                    <th className="p-2.5 font-bold text-slate-700 text-center">Records</th>
                    <th className="p-2.5 font-bold text-slate-700">Foreign Keys</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {previewData.affected_tables.map((t) => (
                    <tr key={t.table_name}>
                      <td className="p-2.5 font-medium text-slate-800">{t.display_name}</td>
                      <td className="p-2.5 text-center font-bold text-rose-600">{t.record_count}</td>
                      <td className="p-2.5 text-slate-500 text-[11px]">
                        {t.foreign_key_dependencies.join(', ') || 'None'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between text-xs font-semibold px-1 text-slate-700">
              <span>Total Records Scheduled for Deletion:</span>
              <span className="text-sm font-bold text-rose-600">{previewData.total_records_to_delete}</span>
            </div>

            {/* Confirmation Checkbox */}
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5">
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={confirmCheckbox}
                  onChange={(e) => setConfirmCheckbox(e.target.checked)}
                  className="mt-0.5 rounded border-slate-300 text-rose-600 focus:ring-rose-500 h-4 w-4"
                />
                <span className="text-xs text-slate-700 leading-relaxed font-medium">
                  I understand this action will permanently remove the listed generated operational records. I confirm that master academic entities remain untouched.
                </span>
              </label>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowPreviewModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={() =>
                  executeClearMutation.mutate({
                    categories: previewData.categories_selected,
                    clear_all: previewData.clear_all,
                  })
                }
                disabled={!confirmCheckbox || executeClearMutation.isPending}
                className="inline-flex items-center gap-2 px-5 py-2 text-xs font-bold text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-sm focus:ring-2 focus:ring-rose-500 transition-all disabled:opacity-40"
              >
                {executeClearMutation.isPending ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Executing Deletion...
                  </>
                ) : (
                  <>
                    <Trash2 size={14} />
                    EXECUTE SAFE PURGE
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

function SaveIcon() {
  return <CheckCircle2 size={15} />;
}
