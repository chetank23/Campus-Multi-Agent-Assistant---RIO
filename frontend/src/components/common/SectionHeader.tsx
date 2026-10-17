import React from 'react';

interface SectionHeaderProps {
  title: string;
  description?: string;
  count?: number | string;
  action?: React.ReactNode;
  className?: string;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({
  title,
  description,
  count,
  action,
  className = '',
}) => {
  return (
    <div className={`flex items-center justify-between gap-4 pb-3 mb-4 border-b border-slate-200/80 ${className}`}>
      <div>
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-slate-900 tracking-tight">{title}</h2>
          {count !== undefined && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200 font-tabular">
              {count}
            </span>
          )}
        </div>
        {description && <p className="text-xs text-slate-500 mt-0.5">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
};
