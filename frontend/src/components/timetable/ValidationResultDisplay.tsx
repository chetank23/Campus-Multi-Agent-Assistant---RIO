import React from 'react';
import { type ValidationResult } from '@/api/timetable';
import { AlertTriangle, XCircle, ShieldCheck, ShieldAlert } from 'lucide-react';

interface ValidationResultDisplayProps {
  result: ValidationResult;
}

export const ValidationResultDisplay: React.FC<ValidationResultDisplayProps> = ({ result }) => {
  const hardViolations = result.violations.filter((v) => v.severity === 'HARD');
  const softViolations = result.violations.filter((v) => v.severity === 'SOFT');

  if (result.is_valid && result.violations.length === 0) {
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
            The timetable satisfies all institutional hard constraints (no faculty overlaps, no room double-bookings, valid time windows).
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`border rounded-2xl p-5 shadow-xs transition-all ${
        result.is_valid
          ? 'bg-amber-50/70 border-amber-200/90 text-amber-900'
          : 'bg-rose-50/70 border-rose-200/90 text-rose-900'
      }`}
    >
      <div className="flex items-start gap-3.5">
        <div
          className={`p-2 rounded-xl shrink-0 ${
            result.is_valid ? 'bg-amber-100 text-amber-700' : 'bg-rose-100 text-rose-700'
          }`}
        >
          {result.is_valid ? <AlertTriangle size={20} /> : <ShieldAlert size={20} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">
              {result.is_valid
                ? 'Validation Passed with Soft Advisory Warnings'
                : 'Validation Failed: Hard Constraints Infeasible'}
            </h3>
            <span
              className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                result.is_valid ? 'bg-amber-200/70 text-amber-900' : 'bg-rose-200/70 text-rose-900'
              }`}
            >
              {hardViolations.length} Hard • {softViolations.length} Soft
            </span>
          </div>

          <div className="mt-3.5 space-y-3">
            {hardViolations.length > 0 && (
              <div className="bg-white/80 rounded-xl p-3.5 border border-rose-200/80">
                <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-rose-800 mb-2">
                  <XCircle size={14} className="text-rose-600" />
                  Hard Constraint Violations ({hardViolations.length})
                </div>
                <ul className="list-disc pl-5 space-y-1 text-xs text-rose-700">
                  {hardViolations.map((v, idx) => (
                    <li key={`hard-${idx}`}>{v.message}</li>
                  ))}
                </ul>
              </div>
            )}

            {softViolations.length > 0 && (
              <div className="bg-white/80 rounded-xl p-3.5 border border-amber-200/80">
                <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-amber-800 mb-2">
                  <AlertTriangle size={14} className="text-amber-600" />
                  Soft Advisory Warnings ({softViolations.length})
                </div>
                <ul className="list-disc pl-5 space-y-1 text-xs text-amber-700">
                  {softViolations.map((v, idx) => (
                    <li key={`soft-${idx}`}>{v.message}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
