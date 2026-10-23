import React from 'react';
import { type ValidationResult, type ValidationViolation } from '@/api/timetable';
import { AlertTriangle, XCircle, ShieldCheck, ShieldAlert, Info, Lightbulb } from 'lucide-react';

interface ValidationResultDisplayProps {
  result: ValidationResult;
}

export const ValidationResultDisplay: React.FC<ValidationResultDisplayProps> = ({ result }) => {
  const blockers = result.violations.filter(
    (v) => v.severity === 'BLOCKER' || v.severity === 'HARD'
  );
  const warnings = result.violations.filter(
    (v) => v.severity === 'WARNING' || v.severity === 'SOFT'
  );
  const infos = result.violations.filter(
    (v) => v.severity === 'INFO'
  );

  const blockerCount = result.blocker_count ?? blockers.length;
  const warningCount = result.warning_count ?? warnings.length;
  const infoCount = result.info_count ?? infos.length;

  const isFullyValid = result.is_valid && blockerCount === 0;

  if (isFullyValid && warningCount === 0 && infoCount === 0) {
    return (
      <div className="bg-emerald-50/80 border border-emerald-200/90 rounded-2xl p-5 flex items-start gap-3.5 shadow-xs">
        <div className="p-2 rounded-xl bg-emerald-100 text-emerald-700 shrink-0">
          <ShieldCheck size={20} />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-emerald-900">Validation Passed Successfully</h3>
            <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-200/70 text-emerald-900">
              0 Violations
            </span>
          </div>
          <p className="mt-1 text-xs text-emerald-800 leading-relaxed">
            The timetable satisfies all institutional scheduling rules and hard constraints.
            No faculty collisions, room overlaps, or section conflicts detected. Ready for publication.
          </p>
        </div>
      </div>
    );
  }

  const renderViolationItem = (v: ValidationViolation, idx: number, type: 'blocker' | 'warning' | 'info') => {
    return (
      <li key={`${type}-${idx}`} className="text-xs space-y-1.5 py-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {v.code && (
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider ${
                type === 'blocker'
                  ? 'bg-rose-100 text-rose-800 border border-rose-200'
                  : type === 'warning'
                  ? 'bg-amber-100 text-amber-800 border border-amber-200'
                  : 'bg-blue-100 text-blue-800 border border-blue-200'
              }`}
            >
              {v.code}
            </span>
          )}
          {v.entry_ids && v.entry_ids.length > 0 && (
            <span className="flex items-center gap-1">
              {v.entry_ids.map((eid) => (
                <span
                  key={eid}
                  className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-slate-100 text-slate-700 border border-slate-200"
                >
                  Entry #{eid}
                </span>
              ))}
            </span>
          )}
          <span className="text-slate-800 font-medium">{v.message}</span>
        </div>
        {v.suggestion && (
          <div className="flex items-start gap-1.5 pl-2 py-1 text-[11px] rounded-lg bg-slate-50 border border-slate-200 text-slate-600">
            <Lightbulb size={13} className="text-amber-500 shrink-0 mt-0.5" />
            <span>
              <strong className="text-slate-700">Suggestion:</strong> {v.suggestion}
            </span>
          </div>
        )}
      </li>
    );
  };

  return (
    <div
      className={`border rounded-2xl p-5 shadow-xs transition-all ${
        isFullyValid
          ? 'bg-amber-50/70 border-amber-200/90 text-amber-900'
          : 'bg-rose-50/70 border-rose-200/90 text-rose-900'
      }`}
    >
      <div className="flex items-start gap-3.5">
        <div
          className={`p-2 rounded-xl shrink-0 ${
            isFullyValid ? 'bg-amber-100 text-amber-700' : 'bg-rose-100 text-rose-700'
          }`}
        >
          {isFullyValid ? <AlertTriangle size={20} /> : <ShieldAlert size={20} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">
              {isFullyValid
                ? 'Validation Passed: Soft Advisory Warnings Found'
                : 'Validation Infeasible: Blocker Constraints Must Be Resolved'}
            </h3>
            <div className="flex items-center gap-1.5">
              <span
                className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                  blockerCount > 0 ? 'bg-rose-200/80 text-rose-950 font-bold' : 'bg-slate-100 text-slate-600'
                }`}
              >
                {blockerCount} Blocker{blockerCount === 1 ? '' : 's'}
              </span>
              <span
                className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                  warningCount > 0 ? 'bg-amber-200/80 text-amber-950' : 'bg-slate-100 text-slate-600'
                }`}
              >
                {warningCount} Warning{warningCount === 1 ? '' : 's'}
              </span>
              {infoCount > 0 && (
                <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-blue-100 text-blue-900">
                  {infoCount} Info
                </span>
              )}
            </div>
          </div>

          <p className="mt-1 text-xs text-slate-700">
            {isFullyValid
              ? 'All hard constraints are satisfied. You may finalize and publish this version, or review advisory notices below.'
              : 'Server-side publication safeguards prevent publishing timetable versions with active blocker violations. Address the issues below and re-validate.'}
          </p>

          <div className="mt-3.5 space-y-3">
            {blockers.length > 0 && (
              <div className="bg-white/90 rounded-xl p-3.5 border border-rose-200">
                <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-rose-800 mb-2">
                  <XCircle size={14} className="text-rose-600" />
                  Hard / Blocker Violations ({blockers.length})
                </div>
                <ul className="divide-y divide-rose-100/60 pl-1">
                  {blockers.map((v, idx) => renderViolationItem(v, idx, 'blocker'))}
                </ul>
              </div>
            )}

            {warnings.length > 0 && (
              <div className="bg-white/90 rounded-xl p-3.5 border border-amber-200">
                <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-amber-800 mb-2">
                  <AlertTriangle size={14} className="text-amber-600" />
                  Advisory Warnings ({warnings.length})
                </div>
                <ul className="divide-y divide-amber-100/60 pl-1">
                  {warnings.map((v, idx) => renderViolationItem(v, idx, 'warning'))}
                </ul>
              </div>
            )}

            {infos.length > 0 && (
              <div className="bg-white/90 rounded-xl p-3.5 border border-blue-200">
                <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-blue-800 mb-2">
                  <Info size={14} className="text-blue-600" />
                  Informational Notices ({infos.length})
                </div>
                <ul className="divide-y divide-blue-100/60 pl-1">
                  {infos.map((v, idx) => renderViolationItem(v, idx, 'info'))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
