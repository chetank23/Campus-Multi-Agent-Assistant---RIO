/**
 * frontend/src/context/NotificationContext.tsx
 * --------------------------------------------
 * Central notification context provider.
 * Manages real-time SSE stream, fallback polling, unread counts, and read mutations.
 */

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import { useAuth } from '@/auth/useAuth';
import { getAccessToken, getApiBaseUrl } from '@/api/client';
import {
  getNotifications,
  getUnreadCount,
  markAllNotificationsAsRead,
  markNotificationAsRead,
  type NotificationItem,
} from '@/api/notifications';

import {
  NotificationContext,
  type NotificationContextValue,
} from './NotificationContextDefinition';

export const NotificationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, user } = useAuth();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

  // ── Fetch notifications & unread count ──────────────────────────────────────
  const fetchState = useCallback(async () => {
    if (!isAuthenticated || !user) return;
    try {
      const [notifs, count] = await Promise.all([
        getNotifications(false, 0, 50),
        getUnreadCount(),
      ]);
      setNotifications(notifs);
      setUnreadCount(count);
      setError(null);
    } catch (err: unknown) {
      console.warn('Failed to fetch notifications:', err);
      setError('Unable to load notifications.');
    }
  }, [isAuthenticated, user]);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    await fetchState();
    setIsLoading(false);
  }, [fetchState]);

  // Initial load on authentication
  useEffect(() => {
    let ignore = false;
    if (isAuthenticated && user) {
      Promise.all([
        getNotifications(false, 0, 50),
        getUnreadCount(),
      ])
        .then(([notifs, count]) => {
          if (!ignore) {
            setNotifications(notifs);
            setUnreadCount(count);
            setError(null);
          }
        })
        .catch((err: unknown) => {
          if (!ignore) {
            console.warn('Failed to fetch notifications:', err);
            setError('Unable to load notifications.');
          }
        });
    }
    return () => {
      ignore = true;
    };
  }, [isAuthenticated, user]);

  // ── Real-Time Delivery (SSE + Polling Fallback) ──────────────────────────────
  useEffect(() => {
    if (!isAuthenticated || !user) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      return;
    }

    const token = getAccessToken();
    const baseUrl = getApiBaseUrl();
    const streamUrl = `${baseUrl}/notifications/stream${token ? `?token=${encodeURIComponent(token)}` : ''}`;

    let es: EventSource | null = null;
    try {
      es = new EventSource(streamUrl);
      eventSourceRef.current = es;

      es.addEventListener('connected', (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          if (typeof data.unread_count === 'number') {
            setUnreadCount(data.unread_count);
          }
        } catch {
          // Ignore JSON parse errors
        }
      });

      es.addEventListener('notification', (e: MessageEvent) => {
        try {
          const notif = JSON.parse(e.data) as NotificationItem;
          setNotifications((prev) => {
            // Deduplicate incoming stream messages by id
            if (prev.some((n) => n.id === notif.id)) return prev;
            return [notif, ...prev];
          });
          setUnreadCount((c) => c + 1);
        } catch {
          // Ignore parse errors
        }
      });

      es.onerror = () => {
        // EventSource automatically retries connection
      };
    } catch {
      // If EventSource is unsupported or throws, fallback to polling below
    }

    // Resilience polling fallback every 25 seconds
    const intervalId = window.setInterval(async () => {
      try {
        const count = await getUnreadCount();
        setUnreadCount((prev) => {
          if (prev !== count) {
            // Unread count changed, re-sync full list
            getNotifications(false, 0, 50).then(setNotifications).catch(() => {});
          }
          return count;
        });
      } catch {
        // Silent fail on background poll
      }
    }, 25000);

    return () => {
      window.clearInterval(intervalId);
      if (es) {
        es.close();
      }
      if (eventSourceRef.current === es) {
        eventSourceRef.current = null;
      }
    };
  }, [isAuthenticated, user]);

  // ── Mark as read actions ────────────────────────────────────────────────────
  const markAsRead = useCallback(async (id: number) => {
    // Optimistic update
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)),
    );
    setUnreadCount((c) => Math.max(0, c - 1));

    try {
      await markNotificationAsRead(id);
    } catch (err) {
      console.error(`Failed to mark notification #${id} as read:`, err);
      // Re-sync on failure
      fetchState();
    }
  }, [fetchState]);

  const markAllAsRead = useCallback(async () => {
    // Optimistic update
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);

    try {
      await markAllNotificationsAsRead();
    } catch (err) {
      console.error('Failed to mark all notifications as read:', err);
      // Re-sync on failure
      fetchState();
    }
  }, [fetchState]);

  const activeNotifications = (isAuthenticated && user) ? notifications : [];
  const activeUnreadCount = (isAuthenticated && user) ? unreadCount : 0;

  const value: NotificationContextValue = {
    notifications: activeNotifications,
    unreadCount: activeUnreadCount,
    isLoading,
    error,
    refresh,
    markAsRead,
    markAllAsRead,
  };

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  );
};
