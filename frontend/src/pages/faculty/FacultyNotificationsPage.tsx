import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Bell,
  CheckCheck,
  Check,
  Calendar,
  Megaphone,
  Clock,
} from 'lucide-react';
import {
  getNotifications,
  markNotificationAsRead,
  markAllNotificationsAsRead,
} from '@/api/notifications';
import { LoadingState } from '@/components/common';

export function FacultyNotificationsPage() {
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
    if (filterType === 'ANNOUNCEMENTS') return n.type === 'ANNOUNCEMENT';
    if (filterType === 'UPDATES') return n.type?.startsWith('CLASS_') || n.type?.includes('TIMETABLE');
    return true;
  });

  const unreadTotal = (notifications || []).filter((n) => !n.is_read).length;

  return (
    <div className="space-y-6 max-w-[1200px] mx-auto pb-10">
      {/* Top Banner */}
      <div className="bg-[#142542] text-white p-6 rounded-2xl shadow-sm border border-[#1D3152] flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Bell size={20} className="text-[#38BDF8]" />
            <h1 className="text-xl font-black tracking-tight">Faculty Notification Center</h1>
          </div>
          <p className="text-xs text-[#8FA3BF] mt-1">
            Real-time campus advisories, timetable publication dispatches, and student class updates.
          </p>
        </div>

        {unreadTotal > 0 && (
          <button
            onClick={() => markAllMutation.mutate()}
            disabled={markAllMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-[#1D3152] hover:bg-[#2B426B] text-white text-xs font-bold rounded-xl border border-[#2B426B] transition-colors"
          >
            <CheckCheck size={14} className="text-[#38BDF8]" />
            <span>Mark All as Read ({unreadTotal})</span>
          </button>
        )}
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center justify-between bg-white p-3 rounded-xl border border-slate-200">
        <div className="flex items-center gap-2">
          {(['ALL', 'UNREAD', 'ANNOUNCEMENTS', 'UPDATES'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setFilterType(tab)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                filterType === tab
                  ? 'bg-primary-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {tab === 'ALL'
                ? `All (${notifications?.length || 0})`
                : tab === 'UNREAD'
                ? `Unread (${unreadTotal})`
                : tab}
            </button>
          ))}
        </div>
      </div>

      {/* Notification List */}
      {isLoading ? (
        <div className="py-12">
          <LoadingState message="Loading your notification feed…" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="p-12 bg-white rounded-2xl border border-slate-200 text-center space-y-2">
          <div className="w-12 h-12 rounded-xl bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
            <Bell size={24} />
          </div>
          <h3 className="text-sm font-bold text-slate-900">No Notifications</h3>
          <p className="text-xs text-slate-500">You are all caught up with campus announcements.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((item) => (
            <div
              key={item.id}
              className={`p-4 rounded-xl border transition-all flex items-start justify-between gap-4 ${
                item.is_read
                  ? 'bg-white border-slate-200 text-slate-700'
                  : 'bg-primary-50/40 border-primary-200 text-slate-900'
              }`}
            >
              <div className="flex items-start gap-3 flex-1 min-w-0">
                <div
                  className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 mt-0.5 ${
                    item.type === 'ANNOUNCEMENT'
                      ? 'bg-purple-100 text-purple-700'
                      : item.type?.startsWith('CLASS_')
                      ? 'bg-amber-100 text-amber-700'
                      : 'bg-blue-100 text-blue-700'
                  }`}
                >
                  {item.type === 'ANNOUNCEMENT' ? (
                    <Megaphone size={18} />
                  ) : item.type?.startsWith('CLASS_') ? (
                    <Clock size={18} />
                  ) : (
                    <Calendar size={18} />
                  )}
                </div>

                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-bold truncate">{item.title}</h4>
                    {!item.is_read && (
                      <span className="w-2 h-2 rounded-full bg-primary-600 shrink-0" />
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
                  className="p-1.5 text-slate-400 hover:text-primary-700 hover:bg-primary-50 rounded-lg transition-colors shrink-0"
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
