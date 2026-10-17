import React from 'react';
import { SlidersHorizontal, RotateCcw } from 'lucide-react';

interface FilterBarProps {
  children: React.ReactNode;
  activeCount?: number;
  onReset?: () => void;
  className?: string;
}

export const FilterBar: React.FC<FilterBarProps> = ({
  children,
  activeCount = 0,
  onReset,
  className = '',
}) => {
  return (
    <div
      className={`bg-white rounded-xl border border-slate-200/80 p-3.5 shadow-subtle flex flex-col md:flex-row md:items-center justify-between gap-3 ${className}`}
    >
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500 shrink-0">
        <SlidersHorizontal size={14} className="text-slate-400" />
        <span>Filters</span>
        {activeCount > 0 && (
          <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-primary-100 text-primary-800">
            {activeCount}
          </span>
        )}
      </div>

      <div className="flex-1 flex flex-wrap items-center gap-3">
        {children}
      </div>

      {onReset && activeCount > 0 && (
        <button
          type="button"
          onClick={onReset}
          className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800 font-medium px-2 py-1 rounded transition-colors shrink-0"
        >
          <RotateCcw size={12} />
          <span>Reset</span>
        </button>
      )}
    </div>
  );
};
