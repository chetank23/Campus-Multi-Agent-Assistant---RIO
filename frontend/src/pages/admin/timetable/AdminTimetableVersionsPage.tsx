import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { Calendar, Plus, ChevronRight, Loader2, AlertCircle } from 'lucide-react';
import { getTimetableVersions } from '@/api/timetable';

export const AdminTimetableVersionsPage: React.FC = () => {
  const navigate = useNavigate();
  const { data: versions, isLoading, isError, error } = useQuery({
    queryKey: ['timetable', 'versions'],
    queryFn: () => getTimetableVersions(),
  });

  const getStatusBadge = (status: string | null) => {
    switch (status) {
      case 'GENERATED':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">Generated</span>;
      case 'REVIEWED':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">Reviewed</span>;
      case 'VALIDATED':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">Validated</span>;
      case 'FINALIZED':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">Finalized</span>;
      case 'PUBLISHED':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">Published</span>;
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">{status || 'Draft'}</span>;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Calendar className="h-6 w-6 text-indigo-600" />
          Timetable Versions
        </h1>
        <Link
          to="/admin/timetable/generate"
          className="inline-flex items-center justify-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
        >
          <Plus className="h-4 w-4 mr-2" />
          Generate New Timetable
        </Link>
      </div>

      {isLoading ? (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 flex flex-col items-center justify-center text-center">
          <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mb-4" />
          <p className="text-gray-500">Loading timetable versions...</p>
        </div>
      ) : isError ? (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 flex items-start gap-4">
          <AlertCircle className="w-6 h-6 text-red-600 shrink-0 mt-0.5" />
          <div>
            <h3 className="text-sm font-medium text-red-800">Failed to load versions</h3>
            <p className="mt-1 text-sm text-red-700">
              {error instanceof Error ? error.message : 'An unknown error occurred'}
            </p>
          </div>
        </div>
      ) : !versions || versions.length === 0 ? (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
          <Calendar className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No Timetables Generated</h3>
          <p className="text-gray-500 max-w-md mx-auto mb-6">
            There are no timetable versions saved in the system yet. Click the button above to start generating a new timetable.
          </p>
        </div>
      ) : (
        <div className="bg-white shadow-sm border border-gray-200 rounded-lg overflow-hidden">
          <ul className="divide-y divide-gray-200">
            {versions.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).map((version) => (
              <li key={version.id}>
                <div 
                  className="block hover:bg-gray-50 cursor-pointer transition-colors"
                  onClick={() => navigate(`/admin/timetable/versions/${version.id}`)}
                >
                  <div className="px-4 py-4 sm:px-6 flex items-center justify-between">
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-medium text-indigo-600 truncate">
                          Version V{version.id}
                        </span>
                        {getStatusBadge(version.status)}
                      </div>
                      <div className="flex items-center gap-4 text-sm text-gray-500">
                        <span>Created: {new Date(version.created_at).toLocaleString()}</span>
                        {version.published_at && (
                          <span>Published: {new Date(version.published_at).toLocaleString()}</span>
                        )}
                      </div>
                    </div>
                    <div className="ml-5 shrink-0">
                      <ChevronRight className="h-5 w-5 text-gray-400" />
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
