import React from 'react';
import { User, MapPin } from 'lucide-react';

interface TimetableCellProps {
  courseName: string;
  facultyName: string;
  roomName: string;
  hourType: string;
}

export const TimetableCell: React.FC<TimetableCellProps> = ({
  courseName,
  facultyName,
  roomName,
  hourType,
}) => {
  const isLab = hourType === 'LAB' || hourType === 'PRACTICAL';

  return (
    <div
      className={`h-full w-full p-2.5 rounded-lg border text-xs flex flex-col justify-between transition-all duration-150 shadow-xs ${
        isLab
          ? 'bg-sky-50/70 border-sky-200 hover:border-sky-300'
          : 'bg-white border-slate-200 hover:border-slate-300'
      }`}
    >
      <div>
        <div className="flex items-start justify-between gap-1 mb-1">
          <span
            className="font-bold text-slate-900 tracking-tight line-clamp-1 leading-snug"
            title={courseName}
          >
            {courseName}
          </span>
          {isLab && (
            <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-sky-100 text-sky-850 border border-sky-200">
              LAB
            </span>
          )}
        </div>
      </div>

      <div className="space-y-1 mt-1.5 pt-1.5 border-t border-slate-100">
        <div
          className="text-slate-600 truncate flex items-center gap-1 font-medium text-[11px]"
          title={facultyName}
        >
          <User size={11} className="text-slate-400 shrink-0" />
          <span className="truncate">{facultyName}</span>
        </div>
        <div className="flex items-center justify-between text-[11px]">
          <span
            className="font-semibold text-slate-700 truncate flex items-center gap-1"
            title={roomName}
          >
            <MapPin size={11} className="text-slate-400 shrink-0" />
            <span className="truncate">{roomName || 'Unassigned'}</span>
          </span>
        </div>
      </div>
    </div>
  );
};
