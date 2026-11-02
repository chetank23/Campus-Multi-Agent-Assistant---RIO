import { useQuery } from '@tanstack/react-query';
import {
  BookOpen,
  GraduationCap,
  Award,
  RefreshCw,
} from 'lucide-react';
import { getStudentCourses } from '@/api/timetable';
import { LoadingState, ErrorState } from '@/components/common';

export function StudentCoursesPage() {
  const { data: courses, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['student-courses'],
    queryFn: getStudentCourses,
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <div className="py-12">
        <LoadingState message="Loading your enrolled academic courses…" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="py-12">
        <ErrorState
          title="Could Not Load Courses"
          message="Failed to retrieve enrolled course catalog for your section."
          onRetry={refetch}
        />
      </div>
    );
  }

  const totalCredits = (courses || []).reduce((acc, c) => acc + (c.credits || 0), 0);

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto pb-10">
      {/* Top Banner Header */}
      <div className="bg-[#172554] text-white p-6 rounded-2xl shadow-sm border border-[#1E3A8A] flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <BookOpen size={20} className="text-[#60A5FA]" />
            <h1 className="text-xl font-black tracking-tight">My Enrolled Courses</h1>
          </div>
          <p className="text-xs text-[#93C5FD] mt-1">
            Authoritative course curriculum assigned to your enrolled section for the current semester.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="px-3.5 py-1.5 rounded-xl bg-[#1E3A8A] border border-[#2563EB] text-xs font-bold text-white flex items-center gap-2">
            <Award size={16} className="text-amber-400" />
            <span>{totalCredits} Total Credits</span>
          </div>

          <button
            onClick={() => refetch()}
            className="flex items-center gap-2 px-3.5 py-1.5 bg-[#1E3A8A] hover:bg-[#2563EB] text-white text-xs font-semibold rounded-xl border border-[#2563EB] transition-colors"
          >
            <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Courses Grid */}
      {!courses || courses.length === 0 ? (
        <div className="p-12 bg-white rounded-2xl border border-slate-200 text-center space-y-2">
          <div className="w-12 h-12 rounded-xl bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
            <BookOpen size={24} />
          </div>
          <h3 className="text-sm font-bold text-slate-900">No Courses Assigned</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Your section does not have any active course assignments registered in the academic directory.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {courses.map((course) => (
            <div
              key={course.id}
              className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs hover:border-blue-400 transition-all flex flex-col justify-between space-y-4"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold px-2.5 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-200">
                    {course.course_code}
                  </span>
                  <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                    {course.course_type}
                  </span>
                </div>

                <div>
                  <h3 className="text-base font-bold text-slate-900 line-clamp-2">
                    {course.course_name}
                  </h3>
                  <div className="flex items-center gap-2 text-xs text-slate-500 mt-1">
                    <Award size={14} className="text-amber-500" />
                    <span>{course.credits} Credits</span>
                    {course.section_name && <span>· Section {course.section_name}</span>}
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
                <div className="flex items-center gap-2 text-slate-700">
                  <GraduationCap size={16} className="text-slate-400 shrink-0" />
                  <div>
                    <div className="font-bold">{course.faculty_name || 'Department Faculty'}</div>
                    <div className="text-[10px] text-slate-400">{course.faculty_designation || 'Instructor'}</div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
