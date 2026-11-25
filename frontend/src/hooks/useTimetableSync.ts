import { useEffect, useRef, useState, useCallback } from 'react';
import { getAccessToken } from '../api/client';

export type SyncConnectionStatus = 'connected' | 'reconnecting' | 'polling' | 'disconnected';

export interface RemoteSyncEvent {
  type: string;
  version_id: number;
  revision?: number;
  status?: string;
  actor_name?: string;
  timestamp?: string;
}

interface UseTimetableSyncOptions {
  versionId: number | null;
  enabled?: boolean;
  onRemoteUpdate?: (event: RemoteSyncEvent) => void;
  onPollTick?: () => void;
}

export function useTimetableSync({
  versionId,
  enabled = true,
  onRemoteUpdate,
  onPollTick,
}: UseTimetableSyncOptions) {
  const [connectionStatus, setConnectionStatus] = useState<SyncConnectionStatus>('disconnected');
  const [remoteNotice, setRemoteNotice] = useState<RemoteSyncEvent | null>(null);

  const onRemoteUpdateRef = useRef(onRemoteUpdate);
  const onPollTickRef = useRef(onPollTick);
  useEffect(() => {
    onRemoteUpdateRef.current = onRemoteUpdate;
    onPollTickRef.current = onPollTick;
  }, [onRemoteUpdate, onPollTick]);

  const clearRemoteNotice = useCallback(() => {
    setRemoteNotice(null);
  }, []);

  useEffect(() => {
    if (!enabled || !versionId) {
      return;
    }

    let cancelled = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let pingTimer: number | null = null;
    let pollTimer: number | null = null;
    let retryCount = 0;

    const startPollingFallback = () => {
      if (pollTimer !== null) return;
      setConnectionStatus('polling');
      pollTimer = window.setInterval(() => {
        onPollTickRef.current?.();
      }, 15000);
    };

    const stopPollingFallback = () => {
      if (pollTimer !== null) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
    };

    const connect = () => {
      if (cancelled) return;
      const token = getAccessToken();
      if (!token) {
        startPollingFallback();
        return;
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${protocol}//${window.location.host}/api/ws/timetable/versions/${versionId}?token=${encodeURIComponent(token)}`;

      try {
        ws = new WebSocket(url);
      } catch {
        startPollingFallback();
        return;
      }

      ws.onopen = () => {
        if (cancelled) return;
        retryCount = 0;
        stopPollingFallback();
        setConnectionStatus('connected');
        pingTimer = window.setInterval(() => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 25000);
      };

      ws.onmessage = (msg) => {
        if (cancelled) return;
        try {
          const data = JSON.parse(msg.data) as RemoteSyncEvent;
          if (
            data.type === 'ARRANGEMENTS_SAVED' ||
            data.type === 'VERSION_VALIDATED' ||
            data.type === 'VERSION_FINALIZED' ||
            data.type === 'VERSION_PUBLISHED'
          ) {
            setRemoteNotice(data);
            onRemoteUpdateRef.current?.(data);
          }
        } catch {
          // Ignore malformed frames
        }
      };

      ws.onclose = () => {
        if (pingTimer !== null) {
          window.clearInterval(pingTimer);
          pingTimer = null;
        }
        if (cancelled) return;
        retryCount += 1;
        if (retryCount >= 3) {
          startPollingFallback();
        } else {
          setConnectionStatus('reconnecting');
        }
        const delayMs = Math.min(1000 * Math.pow(2, retryCount - 1), 10000);
        reconnectTimer = window.setTimeout(connect, delayMs);
      };

      ws.onerror = () => {
        // onclose handles backoff & polling fallback
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (pingTimer !== null) window.clearInterval(pingTimer);
      stopPollingFallback();
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        ws.close();
      }
      setConnectionStatus('disconnected');
    };
  }, [versionId, enabled]);

  return {
    connectionStatus: (!enabled || !versionId) ? 'disconnected' : connectionStatus,
    remoteNotice,
    clearRemoteNotice,
  };
}
