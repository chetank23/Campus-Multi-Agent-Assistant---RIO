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
  default: 'bg-[#F1F5F9] text-[#536783]',
  primary: 'bg-[#D8E9FE] text-[#1685E8]',
  success: 'bg-[#D1F4E0] text-[#059669]',
  warning: 'bg-[#FDE8C7] text-[#D97706]',
  danger: 'bg-[#FCD7D7] text-[#DC2626]',
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
      className={`bg-white rounded-xl border border-[#E4EAF2] p-4 sm:p-5 shadow-subtle hover:shadow-card transition-all flex flex-col justify-between ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-wider text-[#536783] truncate">
            {label}
          </p>
          <p className="text-2xl font-extrabold text-[#111D35] mt-1 tracking-tight font-tabular">
            {value}
          </p>
        </div>
        {icon && (
          <div
            className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${iconVariantStyles[variant] || iconVariantStyles.default}`}
            aria-hidden="true"
          >
            {icon}
          </div>
        )}
      </div>
      {sub && (
        <p className="text-xs text-[#536783] mt-3 pt-2.5 border-t border-[#E4EAF2]/60 truncate">
          {sub}
        </p>
      )}
    </div>
  );
};
