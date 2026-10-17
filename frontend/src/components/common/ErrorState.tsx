import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Failed to load data',
  message = 'An unexpected error occurred while communicating with the campus server.',
  onRetry,
  className = '',
}) => {
  return (
    <div
      role="alert"
      className={`bg-rose-50/70 border border-rose-200/90 rounded-xl p-6 text-center ${className}`}
    >
      <div className="w-10 h-10 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center mx-auto mb-3">
        <AlertCircle size={20} />
      </div>
      <h3 className="text-sm font-semibold text-rose-900 mb-1">{title}</h3>
      <p className="text-xs text-rose-700 max-w-md mx-auto mb-4 leading-relaxed">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-white border border-rose-300 text-rose-700 rounded-lg hover:bg-rose-50 text-xs font-semibold shadow-xs transition-colors focus:outline-none focus:ring-2 focus:ring-rose-500"
        >
          <RefreshCw size={13} className="shrink-0" />
          <span>Retry</span>
        </button>
      )}
    </div>
  );
};
