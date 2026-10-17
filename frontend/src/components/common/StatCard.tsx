import React from 'react';

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon?: React.ReactNode;
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'danger';
  className?: string;
}

const iconVariantStyles: Record<string, string> = {
  default: 'bg-slate-100 text-slate-700',
  primary: 'bg-primary-50 text-primary-700',
  success: 'bg-emerald-50 text-emerald-700',
  warning: 'bg-amber-50 text-amber-700',
  danger: 'bg-rose-50 text-rose-700',
};

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  sub,
  icon,
  variant = 'default',
  className = '',
}) => {
  return (
    <div
      className={`bg-white rounded-xl border border-slate-200/80 p-5 shadow-card hover:shadow-elevated transition-all flex flex-col justify-between ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 truncate">
            {label}
          </p>
          <p className="text-2xl font-bold text-slate-900 mt-1 tracking-tight font-tabular">
            {value}
          </p>
        </div>
        {icon && (
          <div
            className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${iconVariantStyles[variant] || iconVariantStyles.default}`}
            aria-hidden="true"
          >
            {icon}
          </div>
        )}
      </div>
      {sub && (
        <p className="text-xs text-slate-500 mt-3 pt-2.5 border-t border-slate-100 truncate">
          {sub}
        </p>
      )}
    </div>
  );
};
