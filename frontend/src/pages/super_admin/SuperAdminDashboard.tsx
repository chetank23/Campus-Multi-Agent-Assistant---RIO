/**
 * pages/super_admin/SuperAdminDashboard.tsx
 * -----------------------------------------
 * Executive Overview Dashboard for Super Admin.
 */

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Award,
  Users2,
  BookOpen,
  Inbox,
  Sparkles,
  ArrowRight,
  FileText,
  Activity,
  Plus,
  Layers,
} from 'lucide-react';
import { getSuperAdminDashboardStats } from '@/api/curriculum';
import { LoadingState } from '@/components/common';

export const SuperAdminDashboard: React.FC = () => {
  const navigate = useNavigate();

  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['super-admin', 'dashboard-stats'],
    queryFn: getSuperAdminDashboardStats,
    refetchInterval: 15_000,
  });

  if (isLoading) {
    return (
      <div className="py-12 flex justify-center">
        <LoadingState message="Loading central governance metrics..." />
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
        Failed to load executive dashboard metrics. Please refresh or check connection.
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* ── Top Executive Hero Banner ─────────────────────────────────── */}
      <div className="bg-gradient-to-r from-[#1E1B4B] via-[#2E2866] to-[#4338CA] rounded-2xl p-6 sm:p-8 text-white shadow-lg relative overflow-hidden">
        <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-white/5 transform skew-x-12 pointer-events-none" />
        <div className="relative z-10 max-w-3xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-400/20 text-amber-300 text-xs font-semibold mb-3 border border-amber-400/30">
            <Sparkles className="w-3.5 h-3.5" />
            Central Academic Curriculum Registry
          </div>
          <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
            Institutional Academic Governance & Operations
          </h2>
          <p className="mt-2 text-indigo-100 text-sm leading-relaxed">
            Manage institutional academic regulations, admission cohorts, versioned curriculum matrices,
            and automated syllabus PDF extractions with verified course mapping and timetable coordination.
          </p>

          <div className="mt-6 flex flex-wrap gap-3">
            <button
              onClick={() => navigate('/super-admin/curriculum-versions')}
              className="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs rounded-xl shadow-md transition-all flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Manage Curricula
            </button>
            <button
              onClick={() => navigate('/super-admin/extraction')}
              className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white font-medium text-xs rounded-xl border border-white/20 transition-all flex items-center gap-2"
            >
              <FileText className="w-4 h-4" />
              AI Syllabus Studio
            </button>
            <button
              onClick={() => navigate('/super-admin/requests')}
              className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white font-medium text-xs rounded-xl border border-white/20 transition-all flex items-center gap-2"
            >
              <Inbox className="w-4 h-4" />
              Admin Requests ({stats.open_requests_count})
            </button>
          </div>
        </div>
      </div>

      {/* ── Key Governance Metric Cards ───────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Regulations */}
        <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Regulations</span>
            <div className="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-700 flex items-center justify-center">
              <Award className="w-5 h-5" />
            </div>
          </div>
          <p className="mt-3 text-2xl font-black text-slate-900">{stats.total_regulations}</p>
          <div className="mt-2 flex items-center text-xs text-slate-500 justify-between">
            <span>Approved Schemes</span>
            <button
              onClick={() => navigate('/super-admin/regulations')}
              className="text-indigo-600 font-semibold hover:underline flex items-center gap-1"
            >
              View <ArrowRight className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Admission Cohorts */}
        <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Cohorts</span>
            <div className="w-9 h-9 rounded-lg bg-sky-50 text-sky-700 flex items-center justify-center">
              <Users2 className="w-5 h-5" />
            </div>
          </div>
          <p className="mt-3 text-2xl font-black text-slate-900">{stats.total_cohorts}</p>
          <div className="mt-2 flex items-center text-xs text-slate-500 justify-between">
            <span>Active Student Batches</span>
            <button
              onClick={() => navigate('/super-admin/cohorts')}
              className="text-sky-600 font-semibold hover:underline flex items-center gap-1"
            >
              View <ArrowRight className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Curricula Versions */}
        <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Curricula</span>
            <div className="w-9 h-9 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center">
              <BookOpen className="w-5 h-5" />
            </div>
          </div>
          <p className="mt-3 text-2xl font-black text-slate-900">{stats.total_curriculum_versions}</p>
          <div className="mt-2 flex items-center text-xs text-slate-500 justify-between">
            <span className="text-emerald-700 font-medium">{stats.published_versions_count} Published</span>
            <button
              onClick={() => navigate('/super-admin/curriculum-versions')}
              className="text-emerald-600 font-semibold hover:underline flex items-center gap-1"
            >
              View <ArrowRight className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Open Requests */}
        <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Admin Requests</span>
            <div className="w-9 h-9 rounded-lg bg-amber-50 text-amber-700 flex items-center justify-center">
              <Inbox className="w-5 h-5" />
            </div>
          </div>
          <p className="mt-3 text-2xl font-black text-slate-900">{stats.open_requests_count}</p>
          <div className="mt-2 flex items-center text-xs text-slate-500 justify-between">
            <span className={stats.open_requests_count > 0 ? "text-amber-600 font-medium" : "text-slate-400"}>
              {stats.open_requests_count > 0 ? "Pending Resolution" : "All Caught Up"}
            </span>
            <button
              onClick={() => navigate('/super-admin/requests')}
              className="text-amber-600 font-semibold hover:underline flex items-center gap-1"
            >
              Review <ArrowRight className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>

      {/* ── Curriculum Version Lifecycle Status Breakdown ─────────────── */}
      <div className="bg-white rounded-xl border border-slate-200/80 p-6 shadow-sm">
        <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-4 flex items-center gap-2">
          <Layers className="w-4 h-4 text-indigo-600" />
          Curriculum Governance Lifecycle Pipeline
        </h3>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
            <span className="text-xs text-slate-500 font-semibold block">DRAFT</span>
            <span className="text-2xl font-black text-slate-800 mt-1 block">{stats.draft_versions_count}</span>
            <p className="text-[11px] text-slate-400 mt-1">In editing / extraction</p>
          </div>

          <div className="p-4 rounded-xl bg-amber-50/60 border border-amber-200/60">
            <span className="text-xs text-amber-700 font-semibold block">NEEDS REVIEW</span>
            <span className="text-2xl font-black text-amber-900 mt-1 block">{stats.needs_review_count}</span>
            <p className="text-[11px] text-amber-600 mt-1">Academic council review</p>
          </div>

          <div className="p-4 rounded-xl bg-blue-50/60 border border-blue-200/60">
            <span className="text-xs text-blue-700 font-semibold block">APPROVED</span>
            <span className="text-2xl font-black text-blue-900 mt-1 block">{stats.approved_versions_count}</span>
            <p className="text-[11px] text-blue-600 mt-1">Ready for publishing</p>
          </div>

          <div className="p-4 rounded-xl bg-emerald-50/60 border border-emerald-200/60">
            <span className="text-xs text-emerald-700 font-semibold block">PUBLISHED</span>
            <span className="text-2xl font-black text-emerald-900 mt-1 block">{stats.published_versions_count}</span>
            <p className="text-[11px] text-emerald-600 mt-1">Immutable & in operation</p>
          </div>
        </div>
      </div>

      {/* ── Recent Governance Audit Activity ──────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200/80 p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-600" />
            Recent Curriculum Audit Trail
          </h3>
          <button
            onClick={() => navigate('/super-admin/audit')}
            className="text-xs text-indigo-600 font-semibold hover:underline flex items-center gap-1"
          >
            Full Audit Log <ArrowRight className="w-3 h-3" />
          </button>
        </div>

        {stats.recent_activities.length === 0 ? (
          <p className="text-xs text-slate-400 italic py-4 text-center">No recent curriculum audit events recorded.</p>
        ) : (
          <div className="divide-y divide-slate-100">
            {stats.recent_activities.map((act) => (
              <div key={act.id} className="py-3 flex items-start justify-between text-xs">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded font-mono text-[10px] font-bold bg-slate-100 text-slate-700">
                      {act.action}
                    </span>
                    <span className="font-semibold text-slate-800">{act.entity_type} #{act.entity_id}</span>
                  </div>
                  <p className="text-slate-500 text-[11px]">By {act.user_name}</p>
                </div>
                <span className="text-slate-400 text-[11px] whitespace-nowrap">
                  {new Date(act.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
