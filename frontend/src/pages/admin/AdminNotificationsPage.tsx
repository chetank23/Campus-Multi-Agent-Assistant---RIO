/**
 * frontend/src/pages/admin/AdminNotificationsPage.tsx
 * ----------------------------------------------------
 * Administrative Notification Center.
 * Features:
 * 1. Filterable alert log with unread counts and direct resolution.
 * 2. Targeted Campus Announcement Broadcaster (Department, Program, Section, Campus).
 */

import React, { useState, useEffect } from 'react';
import {
  Bell,
  Send,
  CheckCheck,
  Calendar,
  Clock,
  BookOpen,
  Info,
  Filter,
  Check,
  AlertCircle,
  ExternalLink,
} from 'lucide-react';
import { useNotifications } from '@/context/useNotifications';
import { useToast } from '@/context/useToast';
import { RefreshButton } from '@/components/common';
import { broadcastAnnouncement, type NotificationItem } from '@/api/notifications';
import { departmentsApi, type DepartmentResponse } from '@/api/departments';

export const AdminNotificationsPage: React.FC = () => {
  const { notifications, unreadCount, markAsRead, markAllAsRead, refresh } = useNotifications();
  const { toast } = useToast();

  // Tabs: 'feed' | 'broadcast'
  const [activeTab, setActiveTab] = useState<'feed' | 'broadcast'>('feed');
  const [filterType, setFilterType] = useState<string>('ALL');

  // Broadcast Form State
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [targetScope, setTargetScope] = useState<'CAMPUS' | 'DEPARTMENT'>('CAMPUS');
  const [selectedDeptId, setSelectedDeptId] = useState<number | ''>('');
  const [targetRole, setTargetRole] = useState<'ALL' | 'FACULTY' | 'STUDENT'>('ALL');
  const [isBroadcasting, setIsBroadcasting] = useState(false);
  const [broadcastResult, setBroadcastResult] = useState<{ success: boolean; message: string } | null>(null);

  // Departments for targeting
  const [departments, setDepartments] = useState<DepartmentResponse[]>([]);

  useEffect(() => {
    departmentsApi.getAll().then(setDepartments).catch(() => {});
  }, []);

  const handleBroadcast = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !message.trim()) return;

    setIsBroadcasting(true);
    setBroadcastResult(null);

    try {
      const res = await broadcastAnnouncement({
        title: title.trim(),
        message: message.trim(),
        target_role: targetRole,
        department_id: targetScope === 'DEPARTMENT' && selectedDeptId ? Number(selectedDeptId) : undefined,
      });

      const succMsg = `${res.message} (${res.recipients_count} notifications created).`;
      setBroadcastResult({
        success: true,
        message: succMsg,
      });
      toast.success(succMsg, { duration: 5000 });
      setTitle('');
      setMessage('');
      refresh();
    } catch {
      const errMsg = 'Broadcast dispatch failed. Please check backend logs.';
      setBroadcastResult({
        success: false,
        message: errMsg,
      });
      toast.error(errMsg);
    } finally {
      setIsBroadcasting(false);
    }
  };

  const filteredNotifications = notifications.filter((n) => {
    if (filterType === 'UNREAD') return !n.is_read;
    if (filterType === 'TIMETABLE') return (n.type || '').includes('TIMETABLE');
    if (filterType === 'BOOKING') return (n.type || '').includes('BOOKING');
    if (filterType === 'ANNOUNCEMENT') return (n.type || '').includes('ANNOUNCEMENT');
    return true;
  });

  const getIcon = (type?: string | null) => {
    const t = (type || '').toUpperCase();
    if (t.includes('TIMETABLE')) return <Calendar size={16} className="text-[#3975D1]" />;
    if (t.includes('BOOKING')) return <Clock size={16} className="text-[#D97706]" />;
    if (t.includes('CLASS')) return <BookOpen size={16} className="text-[#059669]" />;
    return <Info size={16} className="text-[#647795]" />;
  };

  return (
    <div className="max-w-6xl mx-auto py-6 px-4 sm:px-6">
      {/* ── Page Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-[#E3EBF6]">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-[#101D36] flex items-center gap-2.5">
            <Bell size={24} className="text-[#3975D1]" />
            <span>Notification & Announcement Center</span>
          </h1>
          <p className="text-xs sm:text-sm text-[#647795] mt-1">
            Authoritative administrative notification management, lifecycle dispatch alerts, and targeted broadcasts.
          </p>
        </div>

        {/* Header Actions & Tab Controls */}
        <div className="flex items-center gap-3 self-start sm:self-auto flex-wrap">
          <RefreshButton
            onRefresh={refresh}
            entityName="Notifications"
            variant="outline"
            label="Refresh Feed"
          />
          <div className="flex items-center gap-2 bg-[#F1F6FD] p-1 rounded-xl border border-[#E3EBF6]">
            <button
              type="button"
              onClick={() => setActiveTab('feed')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
                activeTab === 'feed'
                  ? 'bg-white text-[#101D36] shadow-xs'
                  : 'text-[#647795] hover:text-[#101D36]'
              }`}
            >
              Alert Feed ({unreadCount} unread)
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('broadcast')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                activeTab === 'broadcast'
                  ? 'bg-[#3975D1] text-white shadow-xs'
                  : 'text-[#647795] hover:text-[#101D36]'
              }`}
            >
              <Send size={12} />
              <span>Campus Broadcast</span>
            </button>
          </div>
        </div>
      </div>

      {/* ── Tab 1: Alert Feed ── */}
      {activeTab === 'feed' && (
        <div className="mt-6 space-y-4">
          {/* Controls bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 bg-white p-3.5 rounded-xl border border-[#E3EBF6] shadow-2xs">
            <div className="flex items-center gap-2">
              <Filter size={14} className="text-[#647795]" />
              <span className="text-xs font-semibold text-[#647795]">Filter:</span>
              {(['ALL', 'UNREAD', 'TIMETABLE', 'BOOKING', 'ANNOUNCEMENT'] as const).map((ft) => (
                <button
                  key={ft}
                  type="button"
                  onClick={() => setFilterType(ft)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${
                    filterType === ft
                      ? 'bg-[#EFF4FC] text-[#3975D1] border border-[#D1E3FD]'
                      : 'text-[#647795] hover:bg-[#F8FAFD]'
                  }`}
                >
                  {ft === 'ALL'
                    ? 'All'
                    : ft === 'UNREAD'
                    ? `Unread (${unreadCount})`
                    : ft.charAt(0) + ft.slice(1).toLowerCase()}
                </button>
              ))}
            </div>

            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => markAllAsRead()}
                className="flex items-center gap-1.5 text-xs font-semibold text-[#3975D1] hover:text-[#2857A1] bg-[#F1F6FD] px-3 py-1.5 rounded-lg transition-colors border border-[#D1E3FD]"
              >
                <CheckCheck size={14} />
                <span>Mark All as Read</span>
              </button>
            )}
          </div>

          {/* Feed List */}
          <div className="bg-white rounded-xl border border-[#E3EBF6] shadow-2xs divide-y divide-[#F1F5F9] overflow-hidden">
            {filteredNotifications.length === 0 ? (
              <div className="py-16 text-center">
                <Bell size={28} className="text-[#9BB3D6] mx-auto mb-2" />
                <p className="text-sm font-bold text-[#101D36]">No notifications found</p>
                <p className="text-xs text-[#647795] mt-0.5">
                  No alerts match your current filter selection.
                </p>
              </div>
            ) : (
              filteredNotifications.map((notif: NotificationItem) => (
                <div
                  key={notif.id}
                  className={`p-4 flex items-start justify-between gap-4 transition-colors ${
                    !notif.is_read ? 'bg-[#F8FAFD]' : 'bg-white'
                  }`}
                >
                  <div className="flex items-start gap-3.5 min-w-0">
                    <div className="w-9 h-9 rounded-xl bg-[#EFF4FC] flex items-center justify-center shrink-0 mt-0.5">
                      {getIcon(notif.type)}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-sm ${
                            !notif.is_read ? 'font-bold text-[#101D36]' : 'font-semibold text-[#374761]'
                          }`}
                        >
                          {notif.title}
                        </span>
                        {!notif.is_read && (
                          <span className="w-2 h-2 rounded-full bg-[#3975D1]" />
                        )}
                      </div>

                      <p className="text-xs text-[#536783] mt-1 leading-relaxed max-w-2xl">
                        {notif.message}
                      </p>

                      <div className="flex items-center gap-3 mt-2 text-[11px] text-[#8190A5]">
                        <span>{new Date(notif.created_at).toLocaleString()}</span>
                        {notif.type && (
                          <span className="bg-[#F1F5F9] px-2 py-0.5 rounded text-[10px] font-mono uppercase">
                            {notif.type}
                          </span>
                        )}
                        {notif.link && (
                          <a
                            href={notif.link}
                            className="text-[#3975D1] font-semibold hover:underline flex items-center gap-1"
                          >
                            <span>Open Target</span>
                            <ExternalLink size={11} />
                          </a>
                        )}
                      </div>
                    </div>
                  </div>

                  {!notif.is_read && (
                    <button
                      type="button"
                      onClick={() => markAsRead(notif.id)}
                      className="p-1.5 rounded-lg text-[#647795] hover:text-[#3975D1] hover:bg-[#EFF4FC] transition-colors shrink-0"
                      title="Mark as read"
                    >
                      <Check size={16} />
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* ── Tab 2: Campus Broadcast ── */}
      {activeTab === 'broadcast' && (
        <div className="mt-6 max-w-2xl bg-white p-6 rounded-xl border border-[#E3EBF6] shadow-2xs">
          <div className="flex items-center gap-2 pb-4 border-b border-[#E3EBF6] mb-5">
            <Send size={18} className="text-[#3975D1]" />
            <h2 className="text-sm font-bold text-[#101D36]">Create Administrative Announcement</h2>
          </div>

          {broadcastResult && (
            <div
              className={`p-3.5 mb-5 rounded-lg text-xs flex items-start gap-2.5 ${
                broadcastResult.success
                  ? 'bg-[#EBF7EE] text-[#1E7E34] border border-[#C3E6CB]'
                  : 'bg-[#FDF2F2] text-[#9B1C1C] border border-[#F8B4B4]'
              }`}
            >
              <AlertCircle size={16} className="shrink-0 mt-0.5" />
              <span>{broadcastResult.message}</span>
            </div>
          )}

          <form onSubmit={handleBroadcast} className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-[#101D36] mb-1">
                Announcement Title *
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Campus Holiday Schedule Update"
                required
                maxLength={150}
                className="w-full px-3.5 py-2 rounded-lg border border-[#E3EBF6] text-xs text-[#101D36] placeholder-[#8190A5] focus:outline-none focus:ring-2 focus:ring-[#3975D1]"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-[#101D36] mb-1">
                Announcement Message *
              </label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Detailed message delivered directly to affected users' notification trays..."
                required
                rows={4}
                className="w-full px-3.5 py-2 rounded-lg border border-[#E3EBF6] text-xs text-[#101D36] placeholder-[#8190A5] focus:outline-none focus:ring-2 focus:ring-[#3975D1]"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-[#101D36] mb-1">Target Scope</label>
                <select
                  value={targetScope}
                  onChange={(e) => setTargetScope(e.target.value as 'CAMPUS' | 'DEPARTMENT')}
                  className="w-full px-3 py-2 rounded-lg border border-[#E3EBF6] text-xs text-[#101D36] bg-white focus:outline-none focus:ring-2 focus:ring-[#3975D1]"
                >
                  <option value="CAMPUS">Entire Campus</option>
                  <option value="DEPARTMENT">Specific Department</option>
                </select>
              </div>

              {targetScope === 'DEPARTMENT' && (
                <div>
                  <label className="block text-xs font-bold text-[#101D36] mb-1">Select Department</label>
                  <select
                    value={selectedDeptId}
                    onChange={(e) => setSelectedDeptId(Number(e.target.value))}
                    required
                    className="w-full px-3 py-2 rounded-lg border border-[#E3EBF6] text-xs text-[#101D36] bg-white focus:outline-none focus:ring-2 focus:ring-[#3975D1]"
                  >
                    <option value="">Choose department...</option>
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.department_code} - {d.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-[#101D36] mb-1">Target Role</label>
                <select
                  value={targetRole}
                  onChange={(e) => setTargetRole(e.target.value as 'ALL' | 'FACULTY' | 'STUDENT')}
                  className="w-full px-3 py-2 rounded-lg border border-[#E3EBF6] text-xs text-[#101D36] bg-white focus:outline-none focus:ring-2 focus:ring-[#3975D1]"
                >
                  <option value="ALL">All Users (Faculty & Students)</option>
                  <option value="FACULTY">Faculty Only</option>
                  <option value="STUDENT">Students Only</option>
                </select>
              </div>
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={isBroadcasting}
                className="w-full sm:w-auto px-5 py-2.5 rounded-lg bg-[#3975D1] text-white text-xs font-bold hover:bg-[#2857A1] transition-colors flex items-center justify-center gap-2 shadow-xs disabled:opacity-50"
              >
                <Send size={13} />
                <span>{isBroadcasting ? 'Broadcasting...' : 'Dispatch Announcement'}</span>
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
