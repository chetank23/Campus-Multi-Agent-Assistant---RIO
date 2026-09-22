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
    <div className={`p-4 rounded-lg border ${isError ? 'bg-red-50 border-red-200' : 'bg-yellow-50 border-yellow-200'}`}>
      <div className="flex items-start">
        {isError ? (
          <AlertCircle className="w-5 h-5 text-red-600 mt-0.5 mr-3 flex-shrink-0" />
        ) : (
          <AlertTriangle className="w-5 h-5 text-yellow-600 mt-0.5 mr-3 flex-shrink-0" />
        )}
        <div>
          <h3 className={`text-sm font-medium ${isError ? 'text-red-800' : 'text-yellow-800'}`}>
            {message}
          </h3>
          {diagnostics && diagnostics.length > 0 && (
            <div className={`mt-2 text-sm ${isError ? 'text-red-700' : 'text-yellow-700'}`}>
              <ul className="list-disc pl-5 space-y-1">
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
