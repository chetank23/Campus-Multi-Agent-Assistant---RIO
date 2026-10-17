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
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200/80',
    dot: 'bg-emerald-500',
  },
  warning: {
    badge: 'bg-amber-50 text-amber-700 border-amber-200/80',
    dot: 'bg-amber-500',
  },
  danger: {
    badge: 'bg-rose-50 text-rose-700 border-rose-200/80',
    dot: 'bg-rose-500',
  },
  info: {
    badge: 'bg-sky-50 text-sky-700 border-sky-200/80',
    dot: 'bg-sky-500',
  },
  primary: {
    badge: 'bg-primary-50 text-primary-800 border-primary-200/80',
    dot: 'bg-primary-600',
  },
  neutral: {
    badge: 'bg-slate-100 text-slate-700 border-slate-200',
    dot: 'bg-slate-400',
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
