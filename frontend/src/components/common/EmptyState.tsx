import React from 'react';
import { Inbox } from 'lucide-react';

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'No records found',
  description = 'There are currently no items matching your criteria in this view.',
  icon,
  action,
  className = '',
}) => {
  return (
    <div
      className={`flex flex-col items-center justify-center p-8 sm:p-12 text-center bg-white rounded-xl border border-[#E4EAF2] shadow-subtle ${className}`}
    >
      <div className="w-12 h-12 rounded-xl bg-[#F8FAFC] border border-[#E4EAF2] text-[#8190A5] flex items-center justify-center mb-3 shadow-2xs">
        {icon || <Inbox size={22} className="text-[#8190A5]" />}
      </div>
      <h3 className="text-sm font-bold text-[#111D35] tracking-tight">{title}</h3>
      {description && (
        <p className="text-xs text-[#536783] mt-1 max-w-sm leading-relaxed">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
};
