import React from 'react';
import { Gauge, Clock, Calendar, Building, CheckCircle2, AlertTriangle, XCircle, Sliders } from 'lucide-react';
import type { GenerationSummary as SummaryType } from '@/api/timetable';

interface GenerationSummaryProps {
  summary: SummaryType;
}

export const GenerationSummary: React.FC<GenerationSummaryProps> = ({ summary }) => {
  if (summary.status !== 'SUCCESS' || !summary.score) {
    return null;
  }

  const { score } = summary;

  return (
    <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs space-y-6">
      <div className="flex items-center justify-between pb-4 border-b border-slate-200/80">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-primary-50 text-primary-700">
            <Gauge size={18} />
          </div>
          <div>
            <h3 className="text-base font-semibold text-slate-900">Optimization Engine Telemetry</h3>
            <p className="text-xs text-slate-500">CP-SAT solver operational convergence and constraint scoring</p>
          </div>
        </div>
        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
          <CheckCircle2 size={13} className="text-emerald-600" />
          Optimal Solution
        </div>
      </div>

      {/* Primary KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-slate-50/70 border border-slate-200/70">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500">Total Score</span>
            <Gauge size={16} className="text-primary-600" />
          </div>
          <div className="text-2xl font-bold tracking-tight text-primary-700">
            {score.total_score.toFixed(2)}
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Weighted objective function</p>
        </div>

        <div className="p-4 rounded-xl bg-slate-50/70 border border-slate-200/70">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500">Generated Entries</span>
            <Calendar size={16} className="text-primary-600" />
          </div>
          <div className="text-2xl font-bold tracking-tight text-slate-900">
            {summary.generated_entries?.length || 0}
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Class periods assigned</p>
        </div>

        <div className="p-4 rounded-xl bg-slate-50/70 border border-slate-200/70">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500">Solve Time</span>
            <Clock size={16} className="text-primary-600" />
          </div>
          <div className="text-2xl font-bold tracking-tight text-slate-900">
            {summary.solve_time_seconds !== undefined ? `${summary.solve_time_seconds.toFixed(2)}s` : '—'}
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Solver execution latency</p>
        </div>

        <div className="p-4 rounded-xl bg-slate-50/70 border border-slate-200/70">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500">Room Utilization</span>
            <Building size={16} className="text-primary-600" />
          </div>
          <div className="text-2xl font-bold tracking-tight text-slate-900">
            {(score.room_utilization_pct * 100).toFixed(1)}%
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Physical space efficiency</p>
        </div>
      </div>

      {/* Constraint Quality Breakdown */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Sliders size={14} className="text-slate-400" />
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Soft Constraint Quality Breakdown
          </h4>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="p-3 rounded-lg border border-slate-200/60 bg-white">
            <div className="text-xs text-slate-500">Workload Balance</div>
            <div className="text-lg font-bold text-slate-800 mt-0.5">
              {score.workload_balance_quality.toFixed(2)}
            </div>
          </div>
          <div className="p-3 rounded-lg border border-slate-200/60 bg-white">
            <div className="text-xs text-slate-500">Faculty Gap Quality</div>
            <div className="text-lg font-bold text-slate-800 mt-0.5">
              {score.faculty_gap_quality.toFixed(2)}
            </div>
          </div>
          <div className="p-3 rounded-lg border border-slate-200/60 bg-white">
            <div className="text-xs text-slate-500">Student Gap Quality</div>
            <div className="text-lg font-bold text-slate-800 mt-0.5">
              {score.student_gap_quality.toFixed(2)}
            </div>
          </div>
          <div className="p-3 rounded-lg border border-slate-200/60 bg-white">
            <div className="text-xs text-slate-500">Room Change Quality</div>
            <div className="text-lg font-bold text-slate-800 mt-0.5">
              {score.room_change_quality.toFixed(2)}
            </div>
          </div>
        </div>
      </div>

      {/* Violations Strip */}
      {(score.hard_violations > 0 || score.soft_violations > 0) && (
        <div className="pt-3 border-t border-slate-200/80 flex flex-wrap gap-4 text-xs">
          {score.hard_violations > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-rose-50 text-rose-800 border border-rose-200 font-semibold">
              <XCircle size={14} className="text-rose-600" />
              Hard Violations: {score.hard_violations}
            </span>
          )}
          {score.soft_violations > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-amber-50 text-amber-800 border border-amber-200 font-semibold">
              <AlertTriangle size={14} className="text-amber-600" />
              Soft Violations: {score.soft_violations}
            </span>
          )}
        </div>
      )}
    </div>
  );
};
