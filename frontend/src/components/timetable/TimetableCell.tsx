import React from 'react';

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
  const bgColor = hourType === 'LAB' ? 'bg-blue-50' : 'bg-gray-50';
  const borderColor = hourType === 'LAB' ? 'border-blue-200' : 'border-gray-200';

  return (
    <div className={`h-full w-full p-2 border rounded-md text-xs sm:text-sm flex flex-col justify-between ${bgColor} ${borderColor} shadow-sm`}>
      <div className="font-semibold text-gray-800 line-clamp-2" title={courseName}>
        {courseName}
      </div>
      <div className="mt-1 space-y-1">
        <div className="text-gray-600 truncate" title={facultyName}>
          {facultyName}
        </div>
        <div className="flex items-center justify-between">
          <span className="font-medium text-gray-700 truncate" title={roomName}>
            {roomName}
          </span>
          {hourType === 'LAB' && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-700">
              LAB
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
