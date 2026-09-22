import React from 'react';
import { type ValidationResult } from '@/api/timetable';
import { AlertTriangle, XCircle, CheckCircle2 } from 'lucide-react';

interface ValidationResultDisplayProps {
  result: ValidationResult;
}

export const ValidationResultDisplay: React.FC<ValidationResultDisplayProps> = ({ result }) => {
  const hardViolations = result.violations.filter(v => v.severity === 'HARD');
  const softViolations = result.violations.filter(v => v.severity === 'SOFT');

  if (result.is_valid && result.violations.length === 0) {
    return (
      <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex items-start">
        <CheckCircle2 className="w-5 h-5 text-green-600 mt-0.5 mr-3 shrink-0" />
        <div>
          <h3 className="text-sm font-medium text-green-800">Validation Passed</h3>
          <p className="mt-1 text-sm text-green-700">The timetable satisfies all hard constraints.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`border rounded-lg p-4 ${result.is_valid ? 'bg-yellow-50 border-yellow-200' : 'bg-red-50 border-red-200'}`}>
      <div className="flex items-start">
        {result.is_valid ? (
          <AlertTriangle className="w-5 h-5 text-yellow-600 mt-0.5 mr-3 shrink-0" />
        ) : (
          <XCircle className="w-5 h-5 text-red-600 mt-0.5 mr-3 shrink-0" />
        )}
        <div className="flex-1">
          <h3 className={`text-sm font-medium ${result.is_valid ? 'text-yellow-800' : 'text-red-800'}`}>
            {result.is_valid ? 'Validation Passed with Warnings' : 'Validation Failed: Hard Constraints Violated'}
          </h3>
          
          <div className="mt-3 space-y-4">
            {hardViolations.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-red-800 mb-2">
                  Hard Violations ({hardViolations.length})
                </h4>
                <ul className="list-disc pl-5 space-y-1">
                  {hardViolations.map((v, idx) => (
                    <li key={`hard-${idx}`} className="text-sm text-red-700">{v.message}</li>
                  ))}
                </ul>
              </div>
            )}

            {softViolations.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-yellow-800 mb-2">
                  Soft Violations ({softViolations.length})
                </h4>
                <ul className="list-disc pl-5 space-y-1">
                  {softViolations.map((v, idx) => (
                    <li key={`soft-${idx}`} className="text-sm text-yellow-700">{v.message}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
