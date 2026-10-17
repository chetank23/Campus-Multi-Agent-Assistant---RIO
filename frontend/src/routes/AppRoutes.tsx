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
import { TimetableGenerationPage } from '@/pages/admin/timetable/TimetableGenerationPage';
import { AdminTimetableVersionsPage } from '@/pages/admin/timetable/AdminTimetableVersionsPage';
import { AdminTimetableReviewPage } from '@/pages/admin/timetable/AdminTimetableReviewPage';

import type { UserRole } from '@/auth/auth.types';

const roleHome: Record<UserRole, string> = {
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
          {/* Stage 6B Admin Pages */}
          <Route path="/admin/academic/departments" element={<DepartmentsPage />} />
          <Route path="/admin/academic/programs" element={<ProgramsPage />} />
          <Route path="/admin/academic/years" element={<AcademicYearsPage />} />
          <Route path="/admin/academic/semesters" element={<SemestersPage />} />
          <Route path="/admin/academic/batches" element={<BatchesPage />} />
          <Route path="/admin/academic/sections" element={<SectionsPage />} />
          <Route path="/admin/people/students" element={<StudentsPage />} />
          <Route path="/admin/people/faculty" element={<FacultyPage />} />
          <Route path="/admin/courses" element={<CoursesPage />} />
          <Route path="/admin/campus/buildings" element={<BuildingsPage />} />
          <Route path="/admin/campus/rooms" element={<RoomsPage />} />
          {/* Stage 6C/6D Timetable Route */}
          <Route path="/admin/timetable" element={<Navigate to="/admin/timetable/versions" replace />} />
          <Route path="/admin/timetable/versions" element={<AdminTimetableVersionsPage />} />
          <Route path="/admin/timetable/versions/:id" element={<AdminTimetableReviewPage />} />
          <Route path="/admin/timetable/generate" element={<TimetableGenerationPage />} />
          {/* Placeholder routes for future Stage 6B+ modules */}
          <Route path="/admin/resources" element={<PlaceholderPage label="Resources" />} />
          <Route path="/admin/requests" element={<PlaceholderPage label="Change Requests" />} />
          <Route path="/admin/notifications" element={<PlaceholderPage label="Notifications" />} />
          <Route path="/admin/audit" element={<PlaceholderPage label="Audit Logs" />} />
        </Route>
      </Route>

      {/* ── Protected: FACULTY ───────────────────────────────────────── */}
      <Route element={<ProtectedRoute />}>
        <Route
          element={
            <RoleRoute roles={['FACULTY']}>
              <AppShell title="Faculty Dashboard" />
            </RoleRoute>
          }
        >
          <Route path="/faculty" element={<FacultyDashboard />} />
          <Route path="/faculty/timetable" element={<PlaceholderPage label="My Timetable" />} />
          <Route path="/faculty/dept-timetable" element={<PlaceholderPage label="Department Timetable" />} />
        </Route>
      </Route>

      {/* ── Protected: STUDENT ───────────────────────────────────────── */}
      <Route element={<ProtectedRoute />}>
        <Route
          element={
            <RoleRoute roles={['STUDENT']}>
              <AppShell title="Student Dashboard" />
            </RoleRoute>
          }
        >
          <Route path="/student" element={<StudentDashboard />} />
          <Route path="/student/timetable" element={<PlaceholderPage label="My Timetable" />} />
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
function PlaceholderPage({ label }: { label: string }) {
  const getMessage = (name: string) => {
    switch (name) {
      case 'Audit Logs':
        return 'Audit log access is not available yet. System audit trails and event telemetry will be enabled in an upcoming release.';
      case 'Resources':
        return 'Resource allocation and campus asset tracking is not available yet. Physical and digital asset registers are being configured.';
      case 'Change Requests':
        return 'Change request workflow is not available yet. Administrative approval queues and delegation routing are pending release.';
      case 'Notifications':
        return 'Notification center is not available yet. Automated alert dispatches and announcement broadcast services are scheduled.';
      default:
        return `${label} management is not available yet. Module services will be activated once backend endpoints are deployed.`;
    }
  };

  return (
    <div className="py-12 max-w-xl mx-auto">
      <EmptyState
        icon={<Clock size={24} className="text-primary-600" />}
        title={`${label} Module`}
        description={getMessage(label)}
      />
    </div>
  );
}
