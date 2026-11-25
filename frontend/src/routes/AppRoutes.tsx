/**
 * routes/AppRoutes.tsx
 * ----------------------
 * Central route definitions with code splitting (React.lazy).
 *
 * Route structure:
 *  /login                   — public
 *  /unauthorized            — public
 *  /app                     — role-detection redirect (protected)
 *  /super-admin/*           — SUPER_ADMIN only
 *  /admin/*                 — ADMIN only
 *  /faculty/*               — FACULTY only
 *  /student/*               — STUDENT only
 *  *                        — 404
 *
 * Note: Frontend route guards are NOT a substitute for backend authorization.
 * The backend validates every request independently.
 */

import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Clock } from 'lucide-react';
import { useAuth } from '@/auth/useAuth';
import { ProtectedRoute } from '@/auth/ProtectedRoute';
import { RoleRoute } from '@/auth/RoleRoute';
import { AppShell } from '@/components/layout/AppShell';
import { FacultyLayout } from '@/layouts/FacultyLayout';
import { StudentLayout } from '@/layouts/StudentLayout';
import { SuperAdminLayout } from '@/layouts/SuperAdminLayout';
import { EmptyState, LoadingState } from '@/components/common';

import { Login } from '@/pages/Login';
import { Unauthorized } from '@/pages/Unauthorized';
import { NotFound } from '@/pages/NotFound';

import type { UserRole } from '@/auth/auth.types';

// Helper for typed lazy imports with named exports
const lazyPage = <T extends Record<string, any>>(
  importer: () => Promise<T>,
  namedExport: keyof T
) => lazy(() => importer().then((mod) => ({ default: mod[namedExport] })));

// ── Super Admin Pages (Lazy) ─────────────────────────────────────────────────
const SuperAdminDashboard = lazyPage(() => import('@/pages/super_admin/SuperAdminDashboard'), 'SuperAdminDashboard');
const SuperAdminRegulationsPage = lazyPage(() => import('@/pages/super_admin/SuperAdminRegulationsPage'), 'SuperAdminRegulationsPage');
const SuperAdminCohortsPage = lazyPage(() => import('@/pages/super_admin/SuperAdminCohortsPage'), 'SuperAdminCohortsPage');
const SuperAdminCurriculumVersionsPage = lazyPage(() => import('@/pages/super_admin/SuperAdminCurriculumVersionsPage'), 'SuperAdminCurriculumVersionsPage');
const SuperAdminSemesterWorkspacePage = lazyPage(() => import('@/pages/super_admin/SuperAdminSemesterWorkspacePage'), 'SuperAdminSemesterWorkspacePage');
const SuperAdminPDFExtractionPage = lazyPage(() => import('@/pages/super_admin/SuperAdminPDFExtractionPage'), 'SuperAdminPDFExtractionPage');
const SuperAdminRequestsPage = lazyPage(() => import('@/pages/super_admin/SuperAdminRequestsPage'), 'SuperAdminRequestsPage');
const SuperAdminAuditHistoryPage = lazyPage(() => import('@/pages/super_admin/SuperAdminAuditHistoryPage'), 'SuperAdminAuditHistoryPage');

// ── Admin Pages (Lazy) ───────────────────────────────────────────────────────
const AdminDashboard = lazyPage(() => import('@/pages/admin/AdminDashboard'), 'AdminDashboard');
const DepartmentsPage = lazyPage(() => import('@/pages/admin/academic/DepartmentsPage'), 'DepartmentsPage');
const ProgramsPage = lazyPage(() => import('@/pages/admin/academic/ProgramsPage'), 'ProgramsPage');
const AcademicYearsPage = lazyPage(() => import('@/pages/admin/academic/AcademicYearsPage'), 'AcademicYearsPage');
const SemestersPage = lazyPage(() => import('@/pages/admin/academic/SemestersPage'), 'SemestersPage');
const BatchesPage = lazyPage(() => import('@/pages/admin/academic/BatchesPage'), 'BatchesPage');
const SectionsPage = lazyPage(() => import('@/pages/admin/academic/SectionsPage'), 'SectionsPage');
const StudentsPage = lazyPage(() => import('@/pages/admin/people/StudentsPage'), 'StudentsPage');
const FacultyPage = lazyPage(() => import('@/pages/admin/people/FacultyPage'), 'FacultyPage');
const CoursesPage = lazyPage(() => import('@/pages/admin/courses/CoursesPage'), 'CoursesPage');
const BuildingsPage = lazyPage(() => import('@/pages/admin/campus/BuildingsPage'), 'BuildingsPage');
const RoomsPage = lazyPage(() => import('@/pages/admin/campus/RoomsPage'), 'RoomsPage');
const CalendarTimeSlotsPage = lazyPage(() => import('@/pages/admin/campus/CalendarTimeSlotsPage'), 'CalendarTimeSlotsPage');
const AdminCurriculumInboxPage = lazyPage(() => import('@/pages/admin/curriculum/AdminCurriculumInboxPage'), 'AdminCurriculumInboxPage');
const AdminCurriculumAllocationPage = lazyPage(() => import('@/pages/admin/curriculum/AdminCurriculumAllocationPage'), 'AdminCurriculumAllocationPage');
const AdminCurriculumReadinessPage = lazyPage(() => import('@/pages/admin/curriculum/AdminCurriculumReadinessPage'), 'AdminCurriculumReadinessPage');
const AdminCurriculumRequestsPage = lazyPage(() => import('@/pages/admin/curriculum/AdminCurriculumRequestsPage'), 'AdminCurriculumRequestsPage');
const AdminTimetableManagementPage = lazyPage(() => import('@/pages/admin/timetable/AdminTimetableManagementPage'), 'AdminTimetableManagementPage');
const AdminTimetableReviewPage = lazyPage(() => import('@/pages/admin/timetable/AdminTimetableReviewPage'), 'AdminTimetableReviewPage');
const ResourcesPage = lazyPage(() => import('@/pages/admin/resources/ResourcesPage'), 'ResourcesPage');
const AdminEventsPage = lazyPage(() => import('@/pages/admin/AdminEventsPage'), 'AdminEventsPage');
const AdminPlacementsPage = lazyPage(() => import('@/pages/admin/AdminPlacementsPage'), 'AdminPlacementsPage');
const AdminSubstitutionPage = lazyPage(() => import('@/pages/admin/AdminSubstitutionPage'), 'AdminSubstitutionPage');
const AdminChangeRequestsPage = lazyPage(() => import('@/pages/admin/AdminChangeRequestsPage'), 'AdminChangeRequestsPage');
const AdminNotificationsPage = lazyPage(() => import('@/pages/admin/AdminNotificationsPage'), 'AdminNotificationsPage');
const AdminAuditLogsPage = lazyPage(() => import('@/pages/admin/AdminAuditLogsPage'), 'AdminAuditLogsPage');
const ImportValidationPage = lazyPage(() => import('@/pages/admin/data/ImportValidationPage'), 'ImportValidationPage');
const ReportsPage = lazyPage(() => import('@/pages/admin/reports/ReportsPage'), 'ReportsPage');
const UsersPage = lazyPage(() => import('@/pages/admin/system/UsersPage'), 'UsersPage');
const AdminSettingsPage = lazyPage(() => import('@/pages/admin/AdminSettingsPage'), 'AdminSettingsPage');

// ── Faculty Pages (Lazy) ─────────────────────────────────────────────────────
const FacultyDashboard = lazyPage(() => import('@/pages/faculty/FacultyDashboard'), 'FacultyDashboard');
const FacultyTimetablePage = lazyPage(() => import('@/pages/faculty/FacultyTimetablePage'), 'FacultyTimetablePage');
const FacultyDeptTimetablePage = lazyPage(() => import('@/pages/faculty/FacultyDeptTimetablePage'), 'FacultyDeptTimetablePage');
const FacultyAvailabilityPage = lazyPage(() => import('@/pages/faculty/FacultyAvailabilityPage'), 'FacultyAvailabilityPage');
const FacultyResourcesPage = lazyPage(() => import('@/pages/faculty/FacultyResourcesPage'), 'FacultyResourcesPage');
const FacultyEventsPage = lazyPage(() => import('@/pages/faculty/FacultyEventsPage'), 'FacultyEventsPage');
const FacultySubstitutionPage = lazyPage(() => import('@/pages/faculty/FacultySubstitutionPage'), 'FacultySubstitutionPage');
const FacultyChangeRequestsPage = lazyPage(() => import('@/pages/faculty/FacultyChangeRequestsPage'), 'FacultyChangeRequestsPage');
const FacultyNotificationsPage = lazyPage(() => import('@/pages/faculty/FacultyNotificationsPage'), 'FacultyNotificationsPage');

// ── Student Pages (Lazy) ─────────────────────────────────────────────────────
const StudentDashboard = lazyPage(() => import('@/pages/student/StudentDashboard'), 'StudentDashboard');
const StudentTimetablePage = lazyPage(() => import('@/pages/student/StudentTimetablePage'), 'StudentTimetablePage');
const StudentCoursesPage = lazyPage(() => import('@/pages/student/StudentCoursesPage'), 'StudentCoursesPage');
const StudentEventsPage = lazyPage(() => import('@/pages/student/StudentEventsPage'), 'StudentEventsPage');
const StudentPlacementsPage = lazyPage(() => import('@/pages/student/StudentPlacementsPage'), 'StudentPlacementsPage');
const StudentAnnouncementsPage = lazyPage(() => import('@/pages/student/StudentAnnouncementsPage'), 'StudentAnnouncementsPage');
const StudentNotificationsPage = lazyPage(() => import('@/pages/student/StudentNotificationsPage'), 'StudentNotificationsPage');

const roleHome: Record<UserRole, string> = {
  SUPER_ADMIN: '/super-admin',
  ADMIN: '/admin',
  FACULTY: '/faculty',
  STUDENT: '/student',
};

/** Suspense Boundary Wrapper for Lazy Loaded Routes */
function SuspenseWrapper() {
  return (
    <Suspense
      fallback={
        <div className="min-h-[50vh] flex items-center justify-center p-8">
          <LoadingState message="Loading application module..." />
        </div>
      }
    >
      <Outlet />
    </Suspense>
  );
}

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
          <Route element={<SuspenseWrapper />}>
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
          <Route element={<SuspenseWrapper />}>
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

            {/* Timetable Management */}
            <Route path="/admin/timetable" element={<AdminTimetableManagementPage />} />
            <Route path="/admin/timetable/versions" element={<Navigate to="/admin/timetable" replace />} />
            <Route path="/admin/timetable/versions/:id" element={<AdminTimetableReviewPage />} />
            <Route path="/admin/timetable/generate" element={<Navigate to="/admin/timetable" replace />} />
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
            <Route path="/admin/settings" element={<AdminSettingsPage />} />
          </Route>
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
          <Route element={<SuspenseWrapper />}>
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
          <Route element={<SuspenseWrapper />}>
            <Route path="/student" element={<StudentDashboard />} />
            <Route path="/student/timetable" element={<StudentTimetablePage />} />
            <Route path="/student/courses" element={<StudentCoursesPage />} />
            <Route path="/student/events" element={<StudentEventsPage />} />
            <Route path="/student/placements" element={<StudentPlacementsPage />} />
            <Route path="/student/announcements" element={<StudentAnnouncementsPage />} />
            <Route path="/student/notifications" element={<StudentNotificationsPage />} />
          </Route>
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
