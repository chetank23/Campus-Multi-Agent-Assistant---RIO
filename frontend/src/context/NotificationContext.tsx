/**
 * frontend/src/context/NotificationContext.tsx
 * --------------------------------------------
 * Central notification context provider.
 * Manages real-time SSE stream, fallback polling, unread counts, and read mutations.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { useAuth } from '@/auth/AuthProvider';
import { getAccessToken, getApiBaseUrl } from '@/api/client';
import {
  getNotifications,
  getUnreadCount,
  markAllNotificationsAsRead,
  markNotificationAsRead,
  type NotificationItem,
} from '@/api/notifications';

interface NotificationContextValue {
  notifications: NotificationItem[];
  unreadCount: number;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  markAsRead: (id: number) => Promise<void>;
  markAllAsRead: () => Promise<void>;
}

const NotificationContext = createContext<NotificationContextValue | null>(null);

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
      setError(null);
      const [notifs, count] = await Promise.all([
        getNotifications(false, 0, 50),
        getUnreadCount(),
      ]);
      setNotifications(notifs);
      setUnreadCount(count);
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
    if (isAuthenticated && user) {
      fetchState();
    } else {
      setNotifications([]);
      setUnreadCount(0);
    }
  }, [isAuthenticated, user, fetchState]);

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

  const value: NotificationContextValue = {
    notifications,
    unreadCount,
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

export function useNotifications(): NotificationContextValue {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error('useNotifications must be used within a NotificationProvider');
  }
  return context;
}
