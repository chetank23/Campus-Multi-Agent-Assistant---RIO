import React from 'react';

interface TimetableCellProps {
  courseCode?: string;
  courseName: string;
  facultyName: string;
  roomName: string;
  hourType: string;
}

export const TimetableCell: React.FC<TimetableCellProps> = ({
  courseCode,
  courseName,
  facultyName,
  roomName,
  hourType,
}) => {
  const isLab = hourType === 'LAB' || hourType === 'PRACTICAL';

  return (
    <div
      className={`w-full p-2.5 rounded-lg border text-xs flex flex-col justify-between transition-all duration-150 shadow-2xs ${
        isLab
          ? 'bg-indigo-50/90 border-indigo-200 text-indigo-950'
          : 'bg-blue-50/90 border-blue-200 text-blue-950'
      }`}
    >
      <div>
        <div className="flex items-start justify-between gap-1 mb-1">
          <span className="font-extrabold text-[12px] text-slate-900 tracking-tight">
            {courseCode || courseName}
          </span>
          <span
            className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${
              isLab
                ? 'bg-indigo-200 text-indigo-900'
                : 'bg-blue-200 text-blue-900'
            }`}
          >
            Class Type: {isLab ? 'Lab / Practical' : hourType || 'Theory'}
          </span>
        </div>
        {/* Complete Subject Title - wrapped, NO line-clamp, NO truncation */}
        <div className="text-[11px] font-medium text-slate-800 leading-snug mb-2 break-words">
          {courseName}
        </div>
      </div>

      <div className="pt-1.5 border-t border-slate-200/80 text-[11px] text-slate-700 space-y-0.5">
        <div className="flex items-start gap-1">
          <span className="text-slate-500 font-normal shrink-0">Faculty:</span>
          <span className="font-semibold text-slate-900 break-words">{facultyName || 'Unassigned'}</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-slate-500 font-normal">Room No.:</span>
          <span className="font-bold text-slate-900">{roomName || 'TBD'}</span>
        </div>
      </div>
    </div>
  );
};
