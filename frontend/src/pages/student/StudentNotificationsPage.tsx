import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Bell,
  CheckCheck,
  Check,
  Calendar,
  Clock,
  Megaphone,
} from 'lucide-react';
import {
  getNotifications,
  markNotificationAsRead,
  markAllNotificationsAsRead,
} from '@/api/notifications';
import { LoadingState } from '@/components/common';

export function StudentNotificationsPage() {
  const queryClient = useQueryClient();
  const [filterType, setFilterType] = useState<string>('ALL');

  const { data: notifications, isLoading } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => getNotifications(false, 0, 100),
  });

  const markReadMutation = useMutation({
    mutationFn: markNotificationAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
      queryClient.invalidateQueries({ queryKey: ['unread-notifications-count'] });
    },
  });

  const markAllMutation = useMutation({
    mutationFn: markAllNotificationsAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
      queryClient.invalidateQueries({ queryKey: ['unread-notifications-count'] });
    },
  });

  const filtered = (notifications || []).filter((n) => {
    if (filterType === 'UNREAD') return !n.is_read;
    if (filterType === 'CLASS_UPDATES') return n.type?.startsWith('CLASS_');
    if (filterType === 'ANNOUNCEMENTS') return n.type === 'ANNOUNCEMENT';
    return true;
  });

  const unreadTotal = (notifications || []).filter((n) => !n.is_read).length;

  return (
    <div className="space-y-6 max-w-[1200px] mx-auto pb-10">
      {/* Top Banner Header */}
      <div className="bg-[#172554] text-white p-6 rounded-2xl shadow-sm border border-[#1E3A8A] flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Bell size={20} className="text-[#60A5FA]" />
            <h1 className="text-xl font-black tracking-tight">Student Notification Center</h1>
          </div>
          <p className="text-xs text-[#93C5FD] mt-1">
            Real-time updates regarding class room changes, timetable releases, and university advisories.
          </p>
        </div>

        {unreadTotal > 0 && (
          <button
            onClick={() => markAllMutation.mutate()}
            disabled={markAllMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-[#1E3A8A] hover:bg-[#2563EB] text-white text-xs font-bold rounded-xl border border-[#2563EB] transition-colors"
          >
            <CheckCheck size={14} className="text-[#60A5FA]" />
            <span>Mark All as Read ({unreadTotal})</span>
          </button>
        )}
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center justify-between bg-white p-3 rounded-xl border border-slate-200">
        <div className="flex items-center gap-2">
          {(['ALL', 'UNREAD', 'CLASS_UPDATES', 'ANNOUNCEMENTS'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setFilterType(tab)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                filterType === tab
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {tab === 'ALL'
                ? `All (${notifications?.length || 0})`
                : tab === 'UNREAD'
                ? `Unread (${unreadTotal})`
                : tab === 'CLASS_UPDATES'
                ? 'Class Updates'
                : 'Announcements'}
            </button>
          ))}
        </div>
      </div>

      {/* Notification List */}
      {isLoading ? (
        <div className="py-12">
          <LoadingState message="Loading your notifications…" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="p-12 bg-white rounded-2xl border border-slate-200 text-center space-y-2">
          <div className="w-12 h-12 rounded-xl bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
            <Bell size={24} />
          </div>
          <h3 className="text-sm font-bold text-slate-900">No Notifications</h3>
          <p className="text-xs text-slate-500">You are completely up to date.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((item) => (
            <div
              key={item.id}
              className={`p-4 rounded-xl border transition-all flex items-start justify-between gap-4 ${
                item.is_read
                  ? 'bg-white border-slate-200 text-slate-700'
                  : 'bg-blue-50/40 border-blue-200 text-slate-900'
              }`}
            >
              <div className="flex items-start gap-3 flex-1 min-w-0">
                <div
                  className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 mt-0.5 ${
                    item.type?.startsWith('CLASS_')
                      ? 'bg-amber-100 text-amber-700'
                      : item.type === 'ANNOUNCEMENT'
                      ? 'bg-purple-100 text-purple-700'
                      : 'bg-blue-100 text-blue-700'
                  }`}
                >
                  {item.type?.startsWith('CLASS_') ? (
                    <Clock size={18} />
                  ) : item.type === 'ANNOUNCEMENT' ? (
                    <Megaphone size={18} />
                  ) : (
                    <Calendar size={18} />
                  )}
                </div>

                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-bold truncate">{item.title}</h4>
                    {!item.is_read && (
                      <span className="w-2 h-2 rounded-full bg-blue-600 shrink-0" />
                    )}
                  </div>
                  <p className="text-xs text-slate-600 leading-relaxed whitespace-pre-wrap">
                    {item.message}
                  </p>
                  <p className="text-[10px] text-slate-400 font-mono">
                    {new Date(item.created_at).toLocaleString()}
                  </p>
                </div>
              </div>

              {!item.is_read && (
                <button
                  onClick={() => markReadMutation.mutate(item.id)}
                  className="p-1.5 text-slate-400 hover:text-blue-700 hover:bg-blue-50 rounded-lg transition-colors shrink-0"
                  title="Mark as read"
                >
                  <Check size={16} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
