import React from 'react';
import { Loader2 } from 'lucide-react';

interface LoadingStateProps {
  message?: string;
  variant?: 'spinner' | 'skeleton' | 'table-skeleton';
  rows?: number;
  columns?: number;
  className?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = 'Loading data…',
  variant = 'spinner',
  rows = 5,
  columns = 4,
  className = '',
}) => {
  if (variant === 'table-skeleton') {
    return (
      <div className={`divide-y divide-slate-100 animate-pulse ${className}`}>
        {Array.from({ length: rows }).map((_, rIdx) => (
          <div key={rIdx} className="px-6 py-4 flex items-center gap-4">
            {Array.from({ length: columns }).map((_, cIdx) => (
              <div
                key={cIdx}
                className="h-4 bg-slate-200/80 rounded"
                style={{ width: `${Math.max(30, 90 - cIdx * 15)}%` }}
              />
            ))}
          </div>
        ))}
      </div>
    );
  }

  if (variant === 'skeleton') {
    return (
      <div className={`space-y-3 animate-pulse p-6 bg-white rounded-xl border border-slate-200 ${className}`}>
        <div className="h-5 bg-slate-200 rounded w-1/3 mb-4" />
        <div className="h-4 bg-slate-100 rounded w-full" />
        <div className="h-4 bg-slate-100 rounded w-5/6" />
        <div className="h-4 bg-slate-100 rounded w-2/3" />
      </div>
    );
  }

  return (
    <div
      className={`flex flex-col items-center justify-center p-10 text-center min-h-[160px] ${className}`}
    >
      <Loader2 size={24} className="text-primary-600 animate-spin mb-3" />
      <p className="text-xs font-medium text-slate-500 tracking-wide">{message}</p>
    </div>
  );
};
