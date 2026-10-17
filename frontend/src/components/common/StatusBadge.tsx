import React from 'react';

export type StatusVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'primary';

interface StatusBadgeProps {
  status?: string;
  variant?: StatusVariant;
  label?: string;
  dot?: boolean;
  size?: 'sm' | 'md';
  className?: string;
}

const variantStyles: Record<StatusVariant, { badge: string; dot: string }> = {
  success: {
    badge: 'bg-[#E6F7EF] text-[#087F5B] border-[#C8F1DF]',
    dot: 'bg-[#059669]',
  },
  warning: {
    badge: 'bg-[#FFF5E5] text-[#D97706] border-[#FDE8C7]',
    dot: 'bg-[#F59E0B]',
  },
  danger: {
    badge: 'bg-[#FDECEC] text-[#DC2626] border-[#FCD7D7]',
    dot: 'bg-[#EF4444]',
  },
  info: {
    badge: 'bg-[#EDF5FF] text-[#1685E8] border-[#D8E9FE]',
    dot: 'bg-[#2563EB]',
  },
  primary: {
    badge: 'bg-[#EDF5FF] text-[#1685E8] border-[#D8E9FE]',
    dot: 'bg-[#2563EB]',
  },
  neutral: {
    badge: 'bg-[#F1F5F9] text-[#536783] border-[#E4EAF2]',
    dot: 'bg-[#8190A5]',
  },
};

function resolveVariant(statusStr?: string): StatusVariant {
  if (!statusStr) return 'neutral';
  const s = statusStr.toUpperCase();
  if (['PUBLISHED', 'VALIDATED', 'ACTIVE', 'SUCCESS', 'CONFIRMED', 'PASSED'].includes(s)) {
    return 'success';
  }
  if (['REVIEWED', 'PENDING', 'WARNING', 'ELECTIVE', 'SCHEDULED'].includes(s)) {
    return 'warning';
  }
  if (['INFEASIBLE', 'ERROR', 'FAILED', 'REJECTED', 'INACTIVE', 'CRITICAL'].includes(s)) {
    return 'danger';
  }
  if (['FINALIZED', 'GENERATED', 'CORE', 'LAB', 'RUNNING'].includes(s)) {
    return 'info';
  }
  if (['PRIMARY', 'ADMIN'].includes(s)) {
    return 'primary';
  }
  return 'neutral';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  variant,
  label,
  dot = true,
  size = 'sm',
  className = '',
}) => {
  const resolvedVariant = variant || resolveVariant(status);
  const displayLabel = label || status || 'Unknown';
  const styles = variantStyles[resolvedVariant];

  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs font-semibold';

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium border ${styles.badge} ${sizeClasses} ${className}`}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${styles.dot}`} aria-hidden="true" />}
      <span className="truncate">{displayLabel}</span>
    </span>
  );
};
