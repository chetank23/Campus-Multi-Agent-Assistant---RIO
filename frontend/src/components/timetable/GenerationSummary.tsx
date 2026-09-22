import React from 'react';
import type { GenerationSummary as SummaryType } from '@/api/timetable';

interface GenerationSummaryProps {
  summary: SummaryType;
}

export const GenerationSummary: React.FC<GenerationSummaryProps> = ({ summary }) => {
  if (summary.status !== 'SUCCESS' || !summary.score) {
    return null;
  }

  const { score } = summary;

  return (
    <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div>
          <h4 className="text-sm font-medium text-gray-500">Total Score</h4>
          <p className="text-2xl font-bold text-indigo-600">{score.total_score.toFixed(2)}</p>
        </div>
        <div>
          <h4 className="text-sm font-medium text-gray-500">Generated Entries</h4>
          <p className="text-2xl font-bold text-gray-900">{summary.generated_entries?.length || 0}</p>
        </div>
        <div>
          <h4 className="text-sm font-medium text-gray-500">Solve Time</h4>
          <p className="text-2xl font-bold text-gray-900">{summary.solve_time_seconds?.toFixed(2)}s</p>
        </div>
        <div>
          <h4 className="text-sm font-medium text-gray-500">Room Utilization</h4>
          <p className="text-2xl font-bold text-gray-900">{(score.room_utilization_pct * 100).toFixed(1)}%</p>
        </div>
        
        {/* Soft constraints breakdown */}
        <div>
          <h4 className="text-sm font-medium text-gray-500">Faculty Workload Balance</h4>
          <p className="text-lg font-semibold text-gray-800">{score.workload_balance_quality.toFixed(2)}</p>
        </div>
        <div>
          <h4 className="text-sm font-medium text-gray-500">Faculty Gap Quality</h4>
          <p className="text-lg font-semibold text-gray-800">{score.faculty_gap_quality.toFixed(2)}</p>
        </div>
        <div>
          <h4 className="text-sm font-medium text-gray-500">Student Gap Quality</h4>
          <p className="text-lg font-semibold text-gray-800">{score.student_gap_quality.toFixed(2)}</p>
        </div>
        <div>
          <h4 className="text-sm font-medium text-gray-500">Room Change Quality</h4>
          <p className="text-lg font-semibold text-gray-800">{score.room_change_quality.toFixed(2)}</p>
        </div>
      </div>
      
      {(score.hard_violations > 0 || score.soft_violations > 0) && (
        <div className="mt-4 pt-4 border-t border-gray-100 flex gap-6 text-sm">
          {score.hard_violations > 0 && (
            <span className="text-red-600 font-medium">Hard Violations: {score.hard_violations}</span>
          )}
          {score.soft_violations > 0 && (
            <span className="text-yellow-600 font-medium">Soft Violations: {score.soft_violations}</span>
          )}
        </div>
      )}
    </div>
  );
};
