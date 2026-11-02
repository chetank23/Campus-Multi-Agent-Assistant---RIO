import { useQuery } from '@tanstack/react-query';
import { Megaphone, RefreshCw } from 'lucide-react';
import { getNotifications } from '@/api/notifications';
import { LoadingState } from '@/components/common';

export function StudentAnnouncementsPage() {
  const { data: notifications, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => getNotifications(false, 0, 100),
  });

  // Filter announcements & campus bulletins
  const announcements = (notifications || []).filter(
    (n) => n.type === 'ANNOUNCEMENT' || n.title.toLowerCase().includes('announcement') || n.title.toLowerCase().includes('academic')
  );

  return (
    <div className="space-y-6 max-w-[1200px] mx-auto pb-10">
      {/* Top Banner Header */}
      <div className="bg-[#172554] text-white p-6 rounded-2xl shadow-sm border border-[#1E3A8A] flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Megaphone size={20} className="text-[#60A5FA]" />
            <h1 className="text-xl font-black tracking-tight">Campus Announcements & Notices</h1>
          </div>
          <p className="text-xs text-[#93C5FD] mt-1">
            Official institutional circulars, academic calendar alerts, and campus-wide notifications.
          </p>
        </div>

        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 px-3.5 py-1.5 bg-[#1E3A8A] hover:bg-[#2563EB] text-white text-xs font-semibold rounded-xl border border-[#2563EB] transition-colors"
        >
          <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
          <span>Refresh</span>
        </button>
      </div>

      {isLoading ? (
        <div className="py-12">
          <LoadingState message="Loading campus announcements…" />
        </div>
      ) : announcements.length === 0 ? (
        <div className="p-12 bg-white rounded-2xl border border-slate-200 text-center space-y-2">
          <div className="w-12 h-12 rounded-xl bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
            <Megaphone size={24} />
          </div>
          <h3 className="text-sm font-bold text-slate-900">No Announcements Active</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            There are no pending broadcast circulars or announcements posted by academic administration.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {announcements.map((item) => (
            <div
              key={item.id}
              className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs hover:border-blue-300 transition-all space-y-2.5"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase bg-purple-50 text-purple-700 border border-purple-200">
                    Official Notice
                  </span>
                  <span className="text-xs text-slate-400 font-mono">
                    {new Date(item.created_at).toLocaleDateString(undefined, {
                      weekday: 'short',
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                    })}
                  </span>
                </div>
              </div>

              <div>
                <h3 className="text-base font-bold text-slate-900">{item.title}</h3>
                <p className="text-xs text-slate-600 mt-1 leading-relaxed whitespace-pre-wrap">
                  {item.message}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
