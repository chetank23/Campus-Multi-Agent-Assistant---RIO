import React from 'react';
import { AlertCircle, AlertTriangle } from 'lucide-react';

interface GenerationDiagnosticsProps {
  status: string;
  message: string;
  diagnostics?: string[];
}

export const GenerationDiagnostics: React.FC<GenerationDiagnosticsProps> = ({
  status,
  message,
  diagnostics,
}) => {
  if (status === 'SUCCESS' && (!diagnostics || diagnostics.length === 0)) {
    return null; // Don't show anything if perfect success
  }

  const isError = status !== 'SUCCESS';

  return (
    <div
      className={`p-4 rounded-xl border transition-all ${
        isError
          ? 'bg-rose-50/80 border-rose-200 text-rose-900'
          : 'bg-amber-50/80 border-amber-200 text-amber-900'
      }`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`p-1.5 rounded-lg shrink-0 mt-0.5 ${
            isError ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'
          }`}
        >
          {isError ? <AlertCircle size={18} /> : <AlertTriangle size={18} />}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold leading-snug">
            {message}
          </h3>
          {diagnostics && diagnostics.length > 0 && (
            <div className="mt-2.5 pt-2.5 border-t border-current/15 text-xs">
              <span className="font-semibold uppercase tracking-wider text-[10px] opacity-80 block mb-1.5">
                Engine Diagnostics Details:
              </span>
              <ul className="list-disc pl-5 space-y-1 opacity-90">
                {diagnostics.map((diag, index) => (
                  <li key={index}>{diag}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
