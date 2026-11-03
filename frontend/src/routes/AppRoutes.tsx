/**
 * routes/AppRoutes.tsx
 * ----------------------
 * Central route definitions.
 *
 * Route structure:
 *  /login                   — public
 *  /unauthorized            — public
 *  /app                     — role-detection redirect (protected)
 *  /admin/*                 — ADMIN only
 *  /faculty/*               — FACULTY only
 *  /student/*               — STUDENT only
 *  *                        — 404
 *
 * Note: Frontend route guards are NOT a substitute for backend authorization.
 * The backend validates every request independently.
 */

import { Routes, Route, Navigate } from 'react-router-dom';
import { Clock } from 'lucide-react';
import { useAuth } from '@/auth/AuthProvider';
import { ProtectedRoute } from '@/auth/ProtectedRoute';
import { RoleRoute } from '@/auth/RoleRoute';
import { AppShell } from '@/components/layout/AppShell';
import { FacultyLayout } from '@/layouts/FacultyLayout';
import { StudentLayout } from '@/layouts/StudentLayout';
import { EmptyState, LoadingState } from '@/components/common';

import { Login } from '@/pages/Login';
import { Unauthorized } from '@/pages/Unauthorized';
import { NotFound } from '@/pages/NotFound';
import { AdminDashboard } from '@/pages/admin/AdminDashboard';
import { FacultyDashboard } from '@/pages/faculty/FacultyDashboard';
import { StudentDashboard } from '@/pages/student/StudentDashboard';

import { DepartmentsPage } from '@/pages/admin/academic/DepartmentsPage';
import { ProgramsPage } from '@/pages/admin/academic/ProgramsPage';
import { AcademicYearsPage } from '@/pages/admin/academic/AcademicYearsPage';
import { SemestersPage } from '@/pages/admin/academic/SemestersPage';
import { BatchesPage } from '@/pages/admin/academic/BatchesPage';
import { SectionsPage } from '@/pages/admin/academic/SectionsPage';
import { StudentsPage } from '@/pages/admin/people/StudentsPage';
import { FacultyPage } from '@/pages/admin/people/FacultyPage';
import { CoursesPage } from '@/pages/admin/courses/CoursesPage';
import { BuildingsPage } from '@/pages/admin/campus/BuildingsPage';
import { RoomsPage } from '@/pages/admin/campus/RoomsPage';
import { CalendarTimeSlotsPage } from '@/pages/admin/campus/CalendarTimeSlotsPage';
import { ImportValidationPage } from '@/pages/admin/data/ImportValidationPage';
import { ReportsPage } from '@/pages/admin/reports/ReportsPage';
import { UsersPage } from '@/pages/admin/system/UsersPage';
import { TimetableGenerationPage } from '@/pages/admin/timetable/TimetableGenerationPage';
import { AdminTimetableVersionsPage } from '@/pages/admin/timetable/AdminTimetableVersionsPage';
import { AdminTimetableReviewPage } from '@/pages/admin/timetable/AdminTimetableReviewPage';
import { ResourcesPage } from '@/pages/admin/resources/ResourcesPage';
import { AdminEventsPage } from '@/pages/admin/AdminEventsPage';
import { AdminPlacementsPage } from '@/pages/admin/AdminPlacementsPage';
import { AdminSubstitutionPage } from '@/pages/admin/AdminSubstitutionPage';
import { FacultySubstitutionPage } from '@/pages/faculty/FacultySubstitutionPage';
import { AdminNotificationsPage } from '@/pages/admin/AdminNotificationsPage';
import { AdminChangeRequestsPage } from '@/pages/admin/AdminChangeRequestsPage';
import { AdminAuditLogsPage } from '@/pages/admin/AdminAuditLogsPage';

import { SuperAdminLayout } from '@/layouts/SuperAdminLayout';
import { SuperAdminDashboard } from '@/pages/super_admin/SuperAdminDashboard';
import { SuperAdminRegulationsPage } from '@/pages/super_admin/SuperAdminRegulationsPage';
import { SuperAdminCohortsPage } from '@/pages/super_admin/SuperAdminCohortsPage';
import { SuperAdminCurriculumVersionsPage } from '@/pages/super_admin/SuperAdminCurriculumVersionsPage';
import { SuperAdminSemesterWorkspacePage } from '@/pages/super_admin/SuperAdminSemesterWorkspacePage';
import { SuperAdminPDFExtractionPage } from '@/pages/super_admin/SuperAdminPDFExtractionPage';
import { SuperAdminRequestsPage } from '@/pages/super_admin/SuperAdminRequestsPage';
import { SuperAdminAuditHistoryPage } from '@/pages/super_admin/SuperAdminAuditHistoryPage';

import { AdminCurriculumInboxPage } from '@/pages/admin/curriculum/AdminCurriculumInboxPage';
import { AdminCurriculumAllocationPage } from '@/pages/admin/curriculum/AdminCurriculumAllocationPage';
import { AdminCurriculumReadinessPage } from '@/pages/admin/curriculum/AdminCurriculumReadinessPage';
import { AdminCurriculumRequestsPage } from '@/pages/admin/curriculum/AdminCurriculumRequestsPage';

import { FacultyTimetablePage } from '@/pages/faculty/FacultyTimetablePage';
import { FacultyDeptTimetablePage } from '@/pages/faculty/FacultyDeptTimetablePage';
import { FacultyAvailabilityPage } from '@/pages/faculty/FacultyAvailabilityPage';
import { FacultyResourcesPage } from '@/pages/faculty/FacultyResourcesPage';
import { FacultyEventsPage } from '@/pages/faculty/FacultyEventsPage';
import { FacultyChangeRequestsPage } from '@/pages/faculty/FacultyChangeRequestsPage';
import { FacultyNotificationsPage } from '@/pages/faculty/FacultyNotificationsPage';

import { StudentTimetablePage } from '@/pages/student/StudentTimetablePage';
import { StudentCoursesPage } from '@/pages/student/StudentCoursesPage';
import { StudentEventsPage } from '@/pages/student/StudentEventsPage';
import { StudentPlacementsPage } from '@/pages/student/StudentPlacementsPage';
import { StudentAnnouncementsPage } from '@/pages/student/StudentAnnouncementsPage';
import { StudentNotificationsPage } from '@/pages/student/StudentNotificationsPage';

import type { UserRole } from '@/auth/auth.types';

const roleHome: Record<UserRole, string> = {
  SUPER_ADMIN: '/super-admin',
  ADMIN: '/admin',
  FACULTY: '/faculty',
  STUDENT: '/student',
};

/**
 * After login the user is redirected to /app.
 * This component reads the user role from context and redirects to the
 * appropriate dashboard without re-fetching.
 */
function RoleRedirect() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <LoadingState message="Detecting user permissions & active portal session…" />
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;

  return <Navigate to={roleHome[user.role]} replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      {/* ── Public routes ────────────────────────────────────────────── */}
      <Route path="/login" element={<Login />} />
      <Route path="/unauthorized" element={<Unauthorized />} />

      {/* ── Protected: role-detection redirect ───────────────────────── */}
      <Route element={<ProtectedRoute />}>
        <Route path="/app" element={<RoleRedirect />} />
      </Route>

      {/* ── Protected: SUPER_ADMIN ─────────────────────────────────── */}
      <Route element={<ProtectedRoute />}>
        <Route
          element={
            <RoleRoute roles={['SUPER_ADMIN']}>
              <SuperAdminLayout />
            </RoleRoute>
          }
        >
          <Route path="/super-admin" element={<SuperAdminDashboard />} />
          <Route path="/super-admin/regulations" element={<SuperAdminRegulationsPage />} />
          <Route path="/super-admin/cohorts" element={<SuperAdminCohortsPage />} />
          <Route path="/super-admin/curriculum" element={<SuperAdminCurriculumVersionsPage />} />
          <Route path="/super-admin/curriculum-versions" element={<SuperAdminCurriculumVersionsPage />} />
          <Route path="/super-admin/curriculum/:versionId" element={<SuperAdminSemesterWorkspacePage />} />
          <Route path="/super-admin/curriculum-versions/:versionId" element={<SuperAdminSemesterWorkspacePage />} />
          <Route path="/super-admin/curriculum/:versionId/workspace" element={<SuperAdminSemesterWorkspacePage />} />
          <Route path="/super-admin/curriculum-versions/:versionId/workspace" element={<SuperAdminSemesterWorkspacePage />} />
          <Route path="/super-admin/ai-extraction" element={<SuperAdminPDFExtractionPage />} />
          <Route path="/super-admin/extraction" element={<SuperAdminPDFExtractionPage />} />
          <Route path="/super-admin/requests" element={<SuperAdminRequestsPage />} />
          <Route path="/super-admin/audit" element={<SuperAdminAuditHistoryPage />} />
        </Route>
      </Route>

      {/* ── Protected: ADMIN ─────────────────────────────────────────── */}
      <Route element={<ProtectedRoute />}>
        <Route
          element={
            <RoleRoute roles={['ADMIN']}>
              <AppShell title="Admin Dashboard" />
            </RoleRoute>
          }
        >
          <Route path="/admin" element={<AdminDashboard />} />
          {/* Academic Management */}
          <Route path="/admin/academic/departments" element={<DepartmentsPage />} />
          <Route path="/admin/academic/programs" element={<ProgramsPage />} />
          <Route path="/admin/academic/years" element={<AcademicYearsPage />} />
          <Route path="/admin/academic/semesters" element={<SemestersPage />} />
          <Route path="/admin/academic/batches" element={<BatchesPage />} />
          <Route path="/admin/academic/sections" element={<SectionsPage />} />
          {/* People & Courses */}
          <Route path="/admin/people/students" element={<StudentsPage />} />
          <Route path="/admin/people/faculty" element={<FacultyPage />} />
          <Route path="/admin/courses" element={<CoursesPage />} />
          {/* Campus Infrastructure */}
          <Route path="/admin/campus/buildings" element={<BuildingsPage />} />
          <Route path="/admin/campus/rooms" element={<RoomsPage />} />
          <Route path="/admin/campus/calendar-slots" element={<CalendarTimeSlotsPage />} />
          {/* Curriculum & Academic Operations */}
          <Route path="/admin/curriculum" element={<Navigate to="/admin/curriculum/inbox" replace />} />
          <Route path="/admin/curriculum/inbox" element={<AdminCurriculumInboxPage />} />
          <Route path="/admin/curriculum/allocation" element={<AdminCurriculumAllocationPage />} />
          <Route path="/admin/curriculum/readiness" element={<AdminCurriculumReadinessPage />} />
          <Route path="/admin/curriculum/requests" element={<AdminCurriculumRequestsPage />} />

          {/* Timetable Engine */}
          <Route path="/admin/timetable" element={<Navigate to="/admin/timetable/versions" replace />} />
          <Route path="/admin/timetable/versions" element={<AdminTimetableVersionsPage />} />
          <Route path="/admin/timetable/versions/:id" element={<AdminTimetableReviewPage />} />
          <Route path="/admin/timetable/generate" element={<TimetableGenerationPage />} />
          {/* Resource & Operational Administration */}
          <Route path="/admin/resources" element={<ResourcesPage />} />
          <Route path="/admin/events" element={<AdminEventsPage />} />
          <Route path="/admin/placements" element={<AdminPlacementsPage />} />
            <Route path="/admin/substitutions" element={<AdminSubstitutionPage />} />
          <Route path="/admin/requests" element={<AdminChangeRequestsPage />} />
          <Route path="/admin/notifications" element={<AdminNotificationsPage />} />
          <Route path="/admin/audit" element={<AdminAuditLogsPage />} />
          {/* Data & Analytics */}
          <Route path="/admin/data/import" element={<ImportValidationPage />} />
          <Route path="/admin/reports" element={<ReportsPage />} />
          {/* System Administration */}
          <Route path="/admin/system/users" element={<UsersPage />} />
        </Route>
      </Route>

      {/* ── Protected: FACULTY ───────────────────────────────────────── */}
      <Route element={<ProtectedRoute />}>
        <Route
          element={
            <RoleRoute roles={['FACULTY']}>
              <FacultyLayout />
            </RoleRoute>
          }
        >
          <Route path="/faculty" element={<FacultyDashboard />} />
          <Route path="/faculty/timetable" element={<FacultyTimetablePage />} />
          <Route path="/faculty/dept-timetable" element={<FacultyDeptTimetablePage />} />
          <Route path="/faculty/availability" element={<FacultyAvailabilityPage />} />
          <Route path="/faculty/resources" element={<FacultyResourcesPage />} />
          <Route path="/faculty/events" element={<FacultyEventsPage />} />
            <Route path="/faculty/substitutions" element={<FacultySubstitutionPage />} />
          <Route path="/faculty/requests" element={<FacultyChangeRequestsPage />} />
          <Route path="/faculty/notifications" element={<FacultyNotificationsPage />} />
        </Route>
      </Route>

      {/* ── Protected: STUDENT ───────────────────────────────────────── */}
      <Route element={<ProtectedRoute />}>
        <Route
          element={
            <RoleRoute roles={['STUDENT']}>
              <StudentLayout />
            </RoleRoute>
          }
        >
          <Route path="/student" element={<StudentDashboard />} />
          <Route path="/student/timetable" element={<StudentTimetablePage />} />
          <Route path="/student/courses" element={<StudentCoursesPage />} />
          <Route path="/student/events" element={<StudentEventsPage />} />
          <Route path="/student/placements" element={<StudentPlacementsPage />} />
          <Route path="/student/announcements" element={<StudentAnnouncementsPage />} />
          <Route path="/student/notifications" element={<StudentNotificationsPage />} />
        </Route>
      </Route>

      {/* ── Root redirect ─────────────────────────────────────────────── */}
      <Route path="/" element={<Navigate to="/app" replace />} />

      {/* ── 404 ──────────────────────────────────────────────────────── */}
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

/** Professional placeholder for future academic ERP modules. */
export function PlaceholderPage({ label }: { label: string }) {
  return (
    <div className="py-12 max-w-xl mx-auto">
      <EmptyState
        icon={<Clock size={24} className="text-primary-600" />}
        title={`${label} Module`}
        description={`${label} management is currently undergoing scheduled updates.`}
      />
    </div>
  );
}
