/**
 * frontend/src/components/common/useDataRefresh.ts
 * ------------------------------------------------
 * Reusable hook for explicit data refreshing.
 */

import { useState, useCallback } from 'react';
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
      console.error('Data refresh error:', err);
      const name = entityName ? ` ${entityName}` : '';
      toast.error(errorMessage || `Failed to refresh${name} data. Please try again.`, {
        key: `refresh-err-${entityName || 'generic'}`,
        duration: 5000,
      });
    } finally {
      setIsRefreshing(false);
    }
  }, [isRefreshing, onRefresh, queryKeys, entityName, successMessage, errorMessage, queryClient, toast]);

  return {
    isRefreshing,
    lastRefreshed,
    handleRefresh,
  };
}
