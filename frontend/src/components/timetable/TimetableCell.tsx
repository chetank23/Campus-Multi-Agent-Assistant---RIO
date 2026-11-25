import React from 'react';
import { GripVertical, Layers } from 'lucide-react';

interface TimetableCellProps {
  courseCode?: string;
  courseName: string;
  facultyName: string;
  roomName: string;
  hourType: string;
  sectionName?: string | null;
  isEditMode?: boolean;
  isPendingChange?: boolean;
  isConflictHighlighted?: boolean;
  isMultiPeriodBlock?: boolean;
}

export const TimetableCell: React.FC<TimetableCellProps> = ({
  courseCode,
  courseName,
  facultyName,
  roomName,
  hourType,
  sectionName,
  isEditMode = false,
  isPendingChange = false,
  isConflictHighlighted = false,
  isMultiPeriodBlock = false,
}) => {
  const isLab = hourType === 'LAB' || hourType === 'PRACTICAL';

  const ringClass = isConflictHighlighted
    ? 'ring-2 ring-red-500 border-red-400'
    : isPendingChange
      ? 'ring-2 ring-amber-500 border-amber-400'
      : '';

  return (
    <div
      className={`w-full p-2.5 rounded-lg border text-xs flex flex-col justify-between transition-all duration-150 shadow-2xs ${
        isLab
          ? 'bg-indigo-50/90 border-indigo-200 text-indigo-950'
          : 'bg-blue-50/90 border-blue-200 text-blue-950'
      } ${ringClass}`}
    >
      <div>
        <div className="flex items-start justify-between gap-1 mb-1">
          <div className="flex items-center gap-1 min-w-0">
            {isEditMode && (
              <GripVertical className="w-3.5 h-3.5 text-slate-400 shrink-0 cursor-grab active:cursor-grabbing" />
            )}
            <span className="font-extrabold text-[12px] text-slate-900 tracking-tight truncate">
              {courseCode || courseName}
            </span>
          </div>
          <span
            className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider shrink-0 ${
              isLab
                ? 'bg-indigo-200 text-indigo-900'
                : 'bg-blue-200 text-blue-900'
            }`}
          >
            {isLab ? 'Practical' : hourType === 'THEORY' ? 'Theory' : hourType || 'Theory'}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1 mb-1">
          {sectionName && (
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-white/80 border border-slate-200 text-slate-700">
              Sec {sectionName}
            </span>
          )}
          {isMultiPeriodBlock && (
            <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-800">
              <Layers className="w-2.5 h-2.5" />
              Lab Block
            </span>
          )}
          {isPendingChange && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-900">
              Unsaved
            </span>
          )}
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
