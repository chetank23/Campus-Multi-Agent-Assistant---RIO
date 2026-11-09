/**
 * frontend/src/components/common/RefreshButton.tsx
 * -------------------------------------------------
 * Centralized, reusable data refresh button & hook.
 *
 * Guarantees:
 * - Makes the explicit query/backend request via TanStack Query or custom handler.
 * - Displays an animated spinning icon while request is in flight.
 * - Disables user interaction to prevent duplicate rapid clicks.
 * - Updates the actual cached and rendered data.
 * - Updates the truthful lastRefreshed timestamp ONLY upon success.
 * - Dispatches accessible toast notifications (success / error).
 * - Never silently fails or performs dummy component re-renders.
 */

import React, { useState, useCallback } from 'react';
import { RotateCw, Check } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/context/useToast';

export interface UseDataRefreshOptions {
  onRefresh?: () => Promise<unknown> | void;
  queryKeys?: (string | readonly unknown[])[];
  entityName?: string;
  successMessage?: string;
  errorMessage?: string;
}

export function useDataRefresh({
  onRefresh,
  queryKeys,
  entityName,
  successMessage,
  errorMessage,
}: UseDataRefreshOptions) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  const handleRefresh = useCallback(async () => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    try {
      if (onRefresh) {
        await onRefresh();
      }
      if (queryKeys && queryKeys.length > 0) {
        await Promise.all(
          queryKeys.map((qk) =>
            queryClient.refetchQueries({ queryKey: Array.isArray(qk) ? qk : [qk] })
          )
        );
      }
      const now = new Date();
      setLastRefreshed(now);
      const name = entityName ? ` ${entityName}` : '';
      toast.success(successMessage || `Latest${name} data refreshed successfully.`, {
        key: `refresh-${entityName || 'generic'}`,
        duration: 3000,
      });
    } catch (err: unknown) {
      console.error('Data refresh failed:', err);
      const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
      const detail = axiosErr?.response?.data?.detail || axiosErr?.message || 'Server did not respond.';
      toast.error(errorMessage || `Failed to refresh data: ${detail}`, {
        key: `refresh-err-${entityName || 'generic'}`,
      });
    } finally {
      setIsRefreshing(false);
    }
  }, [isRefreshing, onRefresh, queryKeys, entityName, successMessage, errorMessage, queryClient, toast]);

  return { isRefreshing, lastRefreshed, handleRefresh };
}

export interface RefreshButtonProps {
  onRefresh?: () => Promise<unknown> | void;
  queryKeys?: (string | readonly unknown[])[];
  entityName?: string;
  label?: string;
  showTimestamp?: boolean;
  size?: 'sm' | 'md';
  variant?: 'outline' | 'secondary' | 'ghost';
  className?: string;
  successMessage?: string;
  errorMessage?: string;
}

export const RefreshButton: React.FC<RefreshButtonProps> = ({
  onRefresh,
  queryKeys,
  entityName,
  label = 'Refresh',
  showTimestamp = true,
  size = 'sm',
  variant = 'outline',
  className = '',
  successMessage,
  errorMessage,
}) => {
  const { isRefreshing, lastRefreshed, handleRefresh } = useDataRefresh({
    onRefresh,
    queryKeys,
    entityName,
    successMessage,
    errorMessage,
  });

  const baseClasses =
    'inline-flex items-center gap-1.5 font-semibold transition-all rounded-lg focus:outline-hidden focus:ring-2 focus:ring-primary-500/20 disabled:opacity-60 disabled:cursor-not-allowed select-none';

  const sizeClasses =
    size === 'sm' ? 'px-2.5 py-1.5 text-xs' : 'px-3.5 py-2 text-sm';

  const variantClasses =
    variant === 'outline'
      ? 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 hover:text-slate-900 shadow-2xs'
      : variant === 'secondary'
      ? 'bg-slate-100 text-slate-800 hover:bg-slate-200'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900';

  const formatTimestamp = (d: Date) => {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  return (
    <div className="inline-flex items-center gap-2">
      <button
        type="button"
        disabled={isRefreshing}
        onClick={handleRefresh}
        aria-busy={isRefreshing}
        aria-label={label || 'Refresh data'}
        className={`${baseClasses} ${sizeClasses} ${variantClasses} ${className}`}
      >
        <RotateCw
          className={`w-3.5 h-3.5 shrink-0 transition-transform ${
            isRefreshing ? 'animate-spin text-primary-600' : 'text-slate-500'
          }`}
        />
        <span>{isRefreshing ? 'Refreshing…' : label}</span>
      </button>

      {showTimestamp && lastRefreshed && (
        <span
          className="text-[11px] text-slate-400 font-tabular hidden sm:inline-flex items-center gap-1"
          title={`Last verified with server at ${lastRefreshed.toLocaleString()}`}
        >
          <Check size={11} className="text-emerald-500 shrink-0" />
          <span>Updated {formatTimestamp(lastRefreshed)}</span>
        </span>
      )}
    </div>
  );
};

