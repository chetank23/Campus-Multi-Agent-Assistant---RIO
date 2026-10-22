/**
 * frontend/src/components/notifications/NotificationBellDropdown.tsx
 * ------------------------------------------------------------------
 * Interactive Notification Bell and Dropdown Center.
 * Features:
 * - Real-time animated unread badge.
 * - Tabs for "All" and "Unread".
 * - Direct navigation to target timetable or booking on click.
 * - Mark as read / mark all as read.
 * - Responsive popover with outside click dismissal.
 */

import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bell,
  Check,
  CheckCheck,
  Clock,
  Calendar,
  BookOpen,
  Info,
  ExternalLink,
  RotateCw,
} from 'lucide-react';
import { useNotifications } from '@/context/NotificationContext';
import { useAuth } from '@/auth/AuthProvider';
import type { NotificationItem } from '@/api/notifications';

function formatRelativeTime(dateString: string): string {
  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffSec < 60) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHour < 24) return `${diffHour}h ago`;
    if (diffDay < 7) return `${diffDay}d ago`;
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch {
    return 'Recently';
  }
}

function getNotificationIcon(type?: string | null) {
  const t = (type || '').toUpperCase();
  if (t.includes('TIMETABLE')) {
    return <Calendar size={15} className="text-[#3975D1]" />;
  }
  if (t.includes('BOOKING')) {
    return <Clock size={15} className="text-[#D97706]" />;
  }
  if (t.includes('CLASS')) {
    return <BookOpen size={15} className="text-[#059669]" />;
  }
  return <Info size={15} className="text-[#647795]" />;
}

export const NotificationBellDropdown: React.FC<{
  buttonClassName?: string;
  badgeClassName?: string;
  iconSize?: number;
}> = ({
  buttonClassName,
  badgeClassName,
  iconSize = 18,
}) => {
  const { notifications, unreadCount, markAsRead, markAllAsRead, refresh, isLoading } = useNotifications();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [isOpen, setIsOpen] = useState(false);
  const [filterUnread, setFilterUnread] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click or Escape key
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  const displayedNotifications = filterUnread
    ? notifications.filter((n) => !n.is_read)
    : notifications;

  const handleNotificationClick = async (notif: NotificationItem) => {
    if (!notif.is_read) {
      await markAsRead(notif.id);
    }
    if (notif.link) {
      setIsOpen(false);
      navigate(notif.link);
    }
  };

  const defaultButtonClass =
    'p-2 rounded-lg text-[#536783] hover:text-[#111D35] hover:bg-[#F4F7FB] transition-colors relative focus:outline-none focus:ring-2 focus:ring-[#93B5E8]';

  return (
    <div className="relative" ref={containerRef}>
      {/* ── Bell Trigger Button ── */}
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={buttonClassName || defaultButtonClass}
        aria-label="View notifications"
        aria-expanded={isOpen}
        title="Notifications"
      >
        <Bell size={iconSize} />

        {unreadCount > 0 && (
          <span
            className={
              badgeClassName ||
              'absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 bg-[#3975D1] text-white text-[10px] font-bold rounded-full flex items-center justify-center ring-2 ring-white shadow-xs animate-in fade-in zoom-in-75 duration-200'
            }
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* ── Popover Flyout ── */}
      {isOpen && (
        <div
          className="absolute right-0 mt-2 w-80 sm:w-96 bg-white rounded-xl shadow-xl border border-[#E3EBF6] z-50 overflow-hidden flex flex-col max-h-[520px] animate-in fade-in slide-in-from-top-2 duration-150"
          role="dialog"
          aria-label="Notification Center"
        >
          {/* Header */}
          <div className="px-4 py-3 border-b border-[#E3EBF6] bg-[#FBFDFF] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm text-[#101D36]">Notifications</span>
              {unreadCount > 0 && (
                <span className="bg-[#EBF3FF] text-[#2C62B8] text-[10px] font-bold px-2 py-0.5 rounded-full border border-[#D1E3FD]">
                  {unreadCount} unread
                </span>
              )}
            </div>

            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => refresh()}
                disabled={isLoading}
                title="Refresh notifications"
                className="p-1.5 rounded-md text-[#647795] hover:text-[#101D36] hover:bg-[#EFF4FC] transition-colors"
              >
                <RotateCw size={13} className={isLoading ? 'animate-spin' : ''} />
              </button>

              {unreadCount > 0 && (
                <button
                  type="button"
                  onClick={() => markAllAsRead()}
                  className="flex items-center gap-1 text-[11px] font-semibold text-[#3975D1] hover:text-[#2857A1] px-2 py-1 rounded-md hover:bg-[#EFF4FC] transition-colors"
                  title="Mark all notifications as read"
                >
                  <CheckCheck size={13} />
                  <span>Mark all read</span>
                </button>
              )}
            </div>
          </div>

          {/* Filter Tabs */}
          <div className="flex border-b border-[#E3EBF6] bg-[#F8FAFD] text-xs font-semibold px-4 pt-1">
            <button
              type="button"
              onClick={() => setFilterUnread(false)}
              className={`pb-2 px-2 border-b-2 transition-colors ${
                !filterUnread
                  ? 'border-[#3975D1] text-[#3975D1]'
                  : 'border-transparent text-[#647795] hover:text-[#101D36]'
              }`}
            >
              All ({notifications.length})
            </button>
            <button
              type="button"
              onClick={() => setFilterUnread(true)}
              className={`pb-2 px-2 border-b-2 transition-colors ${
                filterUnread
                  ? 'border-[#3975D1] text-[#3975D1]'
                  : 'border-transparent text-[#647795] hover:text-[#101D36]'
              }`}
            >
              Unread ({unreadCount})
            </button>
          </div>

          {/* List Area */}
          <div className="overflow-y-auto divide-y divide-[#F1F5F9] flex-1">
            {displayedNotifications.length === 0 ? (
              <div className="py-12 px-6 text-center">
                <div className="w-10 h-10 rounded-full bg-[#F1F6FD] text-[#3975D1] flex items-center justify-center mx-auto mb-2.5">
                  <Bell size={18} />
                </div>
                <p className="text-xs font-bold text-[#101D36]">
                  {filterUnread ? 'No unread notifications' : 'No notifications yet'}
                </p>
                <p className="text-[11px] text-[#647795] mt-0.5">
                  {filterUnread
                    ? "You have reviewed all your alerts."
                    : 'Campus updates and scheduling alerts will appear here.'}
                </p>
              </div>
            ) : (
              displayedNotifications.map((notif) => (
                <div
                  key={notif.id}
                  className={`p-3.5 flex items-start gap-3 transition-colors text-left group ${
                    !notif.is_read ? 'bg-[#F6F9FE] hover:bg-[#EDF4FD]' : 'bg-white hover:bg-[#F9FBFE]'
                  }`}
                >
                  {/* Icon */}
                  <div className="w-8 h-8 rounded-lg bg-[#EFF4FC] flex items-center justify-center shrink-0 mt-0.5">
                    {getNotificationIcon(notif.type)}
                  </div>

                  {/* Content */}
                  <div
                    className="flex-1 min-w-0 cursor-pointer"
                    onClick={() => handleNotificationClick(notif)}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <p
                        className={`text-xs truncate ${
                          !notif.is_read ? 'font-bold text-[#101D36]' : 'font-medium text-[#293851]'
                        }`}
                      >
                        {notif.title}
                      </p>
                      <span className="text-[10px] text-[#8190A5] shrink-0 font-medium">
                        {formatRelativeTime(notif.created_at)}
                      </span>
                    </div>

                    <p className="text-[11px] text-[#536783] line-clamp-2 mt-0.5 leading-relaxed">
                      {notif.message}
                    </p>

                    {notif.link && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-[#3975D1] mt-1.5 hover:underline">
                        <span>View details</span>
                        <ExternalLink size={10} />
                      </span>
                    )}
                  </div>

                  {/* Actions / Unread dot */}
                  <div className="shrink-0 flex items-center gap-1">
                    {!notif.is_read ? (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          markAsRead(notif.id);
                        }}
                        className="w-5 h-5 rounded-full hover:bg-[#DCE7F9] text-[#3975D1] flex items-center justify-center transition-colors"
                        title="Mark as read"
                      >
                        <Check size={12} />
                      </button>
                    ) : (
                      <span className="w-1.5 h-1.5" />
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Footer */}
          <div className="p-2.5 border-t border-[#E3EBF6] bg-[#FBFDFF] text-center">
            {user?.role === 'ADMIN' ? (
              <button
                type="button"
                onClick={() => {
                  setIsOpen(false);
                  navigate('/admin/notifications');
                }}
                className="text-xs font-bold text-[#3975D1] hover:text-[#2857A1] transition-colors py-1 px-3 rounded-lg hover:bg-[#EFF4FC] inline-flex items-center gap-1.5"
              >
                <span>Open Notification Center</span>
                <ExternalLink size={12} />
              </button>
            ) : (
              <span className="text-[11px] text-[#8190A5] font-medium">
                Real-time alerts active · RIO-MJP
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
