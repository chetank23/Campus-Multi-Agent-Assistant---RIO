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
import { useAuth } from '@/auth/AuthProvider';
import { ProtectedRoute } from '@/auth/ProtectedRoute';
import { RoleRoute } from '@/auth/RoleRoute';
import { AppShell } from '@/components/layout/AppShell';

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
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
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
          {/* Stage 6C Timetable Route */}
          <Route path="/admin/timetable" element={<TimetableGenerationPage />} />
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

/** Generic placeholder for unimplemented Stage 6B+ pages. */
function PlaceholderPage({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[40vh] text-center gap-3">
      <div className="w-14 h-14 rounded-2xl bg-gray-100 flex items-center justify-center">
        <span className="text-2xl">🚧</span>
      </div>
      <h3 className="text-base font-semibold text-gray-700">{label}</h3>
      <p className="text-sm text-gray-400 max-w-xs">
        This page will be implemented in Stage 6B. It is listed in navigation for structural completeness.
      </p>
    </div>
  );
}
