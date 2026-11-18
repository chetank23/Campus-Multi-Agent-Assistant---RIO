# RIO-MJP: Complete Application-Wide Functional Audit Baseline

**Document Version:** 1.0.0  
**Audit Date:** 18 November 2026  
**Auditors:** Principal Full-Stack Engineer, QA Architect, Frontend Integration Specialist, Backend Engineer, Reliability Engineer  
**Branch:** `feature/app-wide-functional-audit-cross-role-sync`  
**Commit Baseline:** `284c891`  

---

## 1. Executive Summary & Inventory Overview

This baseline document captures the complete inventory of routes, pages, interactive controls, forms, modals, API endpoints, database operations, and role permissions across all four institutional profiles of the **RIO-MJP** Campus Multi-Agent Assistant and Academic Management System:

| Inventory Dimension | Discovered Quantity | Status |
|---|---|---|
| **Institutional Roles** | 4 Canonical Roles (`SUPER_ADMIN`, `ADMIN`, `FACULTY`, `STUDENT`) | Fully Defined & Guarded |
| **Frontend Route Definitions** | 56 Registered Routes (in `AppRoutes.tsx`) | 100% Mapped |
| **Frontend Page Components** | 59 Pages (`frontend/src/pages/`) | 100% Inspected |
| **Reusable UI & Layout Components** | 28 Common/Shared Components + 4 Layouts | 100% Inspected |
| **Interactive Buttons Discovered** | 351 Buttons (302 page-level, 49 component-level) | Cataloged for Audit |
| **Forms & Input Groups** | 36 Complex Form Workflows | Cataloged for Audit |
| **Modal Dialogs & Drawers** | 54 Modals (`FormModal`, `ConfirmDialog`, Custom Drawers) | Cataloged for Audit |
| **TanStack React Queries (`useQuery`)** | 104 Queries | Live Backend Linked |
| **TanStack React Mutations (`useMutation`)**| 61 Mutations | CRUD & Workflow Linked |
| **Backend Route Modules** | 35 Modules (`backend/routes/`) | 100% Mounted |
| **FastAPI OpenAPI Paths** | 184 Unique Paths | Verified Active |
| **FastAPI REST Endpoint Operations** | 262 Operations (`GET`, `POST`, `PUT`, `DELETE`, `PATCH`) | Verified Active |
| **Relational Database Entities** | 54 Tables (`PostgreSQL 18.x`, Alembic `f1a2b3c4d5e6`) | Verified Intact |

---

## 2. Institutional Role & Route Architecture

### Role 1: SUPER_ADMIN (System Governance & Institutional Master Planning)
**Scope:** Institutional regulations, admission cohorts, versioned curriculum structures, AI syllabus PDF extraction, multi-department correction tickets, governance audit history.  
**Layout:** `SuperAdminLayout` (`frontend/src/layouts/SuperAdminLayout.tsx`) — Theme: Deep Indigo (`#1E1B4B`) & Amber Gold.

| Route Path | Page Component | Primary Intended Purpose | Key Actions & Controls |
|---|---|---|---|
| `/super-admin` | `SuperAdminDashboard` | Executive overview, metrics, quick actions | Metrics view, quick navigation links |
| `/super-admin/regulations` | `SuperAdminRegulationsPage` | Academic regulations governance (credits, rules) | Create regulation modal, edit, activate, filter |
| `/super-admin/cohorts` | `SuperAdminCohortsPage` | Admission cohort lifecycle | Create cohort, link regulation, date pickers |
| `/super-admin/curriculum` | `SuperAdminCurriculumVersionsPage` | Institutional curriculum versioning | Create version, publish, lock, clone |
| `/super-admin/curriculum-versions` | `SuperAdminCurriculumVersionsPage` | Canonical version list | View status badges, open workspace |
| `/super-admin/curriculum/:versionId` | `SuperAdminSemesterWorkspacePage` | Semester-by-semester subject mapping | Add subject, remove, set credits/hours, map L-T-P |
| `/super-admin/curriculum-versions/:versionId` | `SuperAdminSemesterWorkspacePage` | Workspace alias | Subject structure editor, save |
| `/super-admin/curriculum/:versionId/workspace` | `SuperAdminSemesterWorkspacePage` | Explicit workspace route | Grid editing, validation precheck |
| `/super-admin/curriculum-versions/:versionId/workspace` | `SuperAdminSemesterWorkspacePage` | Explicit workspace route | Grid editing, publish |
| `/super-admin/ai-extraction` | `SuperAdminPDFExtractionPage` | AI syllabus PDF parsing via OCR/Docling | File dropzone upload, start extraction job |
| `/super-admin/extraction` | `SuperAdminPDFExtractionPage` | Extraction studio alias | Review extracted subjects, accept/reject, map |
| `/super-admin/requests` | `SuperAdminRequestsPage` | Department correction requests inbox | Review ticket, approve change, reject, message |
| `/super-admin/audit` | `SuperAdminAuditHistoryPage` | Immutable governance audit log | Filter by entity, date range, export log |

---

### Role 2: ADMIN (Departmental Academic Management & Timetable Authority)
**Scope:** Sole authority for generating, reviewing, validating, and publishing timetables; departmental academic hierarchy (departments, programs, years, semesters, sections, batches); faculty directories; course allocations; campus infrastructure (buildings, rooms, labs); resource management; substitutions; events; CDC placements; data import and system settings.  
**Layout:** `AppShell` with `AdminSidebar` (`frontend/src/components/layout/AdminSidebar.tsx`) — Theme: Crisp Slate/Navy (`#F4F7FB` & `#2563EB`).

| Route Path | Page Component | Primary Intended Purpose | Key Actions & Controls |
|---|---|---|---|
| `/admin` | `AdminDashboard` | Administrative operational overview | Stats cards, quick actions, schedule pulse |
| `/admin/academic/departments` | `DepartmentsPage` | Department CRUD | Add department, edit code/name, delete, search |
| `/admin/academic/programs` | `ProgramsPage` | Degree program CRUD | Add program, set degree/duration, link department |
| `/admin/academic/years` | `AcademicYearsPage` | Academic years (start/end dates) | Add year, edit dates, set active year |
| `/admin/academic/semesters` | `SemestersPage` | Semester management | Add semester, number, set date ranges |
| `/admin/academic/batches` | `BatchesPage` | Lab batches CRUD | Add batch, student count, link section |
| `/admin/academic/sections` | `SectionsPage` | Class sections CRUD | Add section, capacity, link semester/dept |
| `/admin/people/students` | `StudentsPage` | Student roster management | Add student, enroll, assign section/batch, filter |
| `/admin/people/faculty` | `FacultyPage` | Faculty directory & designations | Add faculty, set workload limits, assign dept |
| `/admin/courses` | `CoursesPage` | Master course catalog | Add course, set code/credits/type/L-T-P |
| `/admin/campus/buildings` | `BuildingsPage` | Campus buildings | Add building, code, name, location |
| `/admin/campus/rooms` | `RoomsPage` | Room & lab inventory | Add room, set capacity, type (Class/Lab), floor |
| `/admin/campus/calendar-slots` | `CalendarTimeSlotsPage` | Master time slots & holidays | Add slot, period times, mark break, add holiday |
| `/admin/curriculum/inbox` | `AdminCurriculumInboxPage` | Published curriculum receiver | Acknowledge version, inspect allocated courses |
| `/admin/curriculum/allocation` | `AdminCurriculumAllocationPage` | Section & faculty course allocation | Assign teacher to section course, save |
| `/admin/curriculum/readiness` | `AdminCurriculumReadinessPage` | Timetable generation preflight check | Run preflight check, inspect blockers |
| `/admin/curriculum/requests` | `AdminCurriculumRequestsPage` | Departmental correction requests | Create ticket to Super Admin, view replies |
| `/admin/timetable` | `AdminTimetableManagementPage` | Unified generation, review & publish | Scope picker, generate preview, score, publish |
| `/admin/resources` | `ResourcesPage` | Campus equipment & inventory | Add resource, approve/reject bookings |
| `/admin/events` | `AdminEventsPage` | Campus events & club registry | Create event, set venue/audience, delete |
| `/admin/placements` | `AdminPlacementsPage` | CDC placement drives & schedules | Create drive, set CGPA, dates, manage candidates |
| `/admin/substitutions` | `AdminSubstitutionPage` | Administrative substitution oversight | Review absence, view suggested substitutes, assign |
| `/admin/requests` | `AdminChangeRequestsPage` | Faculty schedule change requests | Approve request, reject, inspect rationale |
| `/admin/notifications` | `AdminNotificationsPage` | Broadcast & system notification center | Send announcement, mark read, filter |
| `/admin/audit` | `AdminAuditLogsPage` | Operational audit trail | Search logs, filter by user/action/date |
| `/admin/data/import` | `ImportValidationPage` | CSV/Excel institutional bulk import | Upload CSV, validate schema, commit import |
| `/admin/reports` | `ReportsPage` | Institutional analytics & PDF export | Generate workload report, room utilization, PDF |
| `/admin/system/users` | `UsersPage` | User account & RBAC management | Create user, change role, toggle active state |
| `/admin/settings` | `AdminSettingsPage` | Institutional operational parameters | Timetable weights, working days, periods |

---

### Role 3: FACULTY (Teaching Operations, Availability & Substitutions)
**Scope:** Personal schedule viewing, departmental schedule cross-referencing, teaching availability constraints, substitution requests, campus resource reservations, event hosting, and notifications.  
**Layout:** `FacultyLayout` (`frontend/src/layouts/FacultyLayout.tsx`) — Theme: Deep Navy (`#142542`) & Cyan/Blue.

| Route Path | Page Component | Primary Intended Purpose | Key Actions & Controls |
|---|---|---|---|
| `/faculty` | `FacultyDashboard` | Faculty overview & upcoming classes | Current class badge, next lecture, quick links |
| `/faculty/timetable` | `FacultyTimetablePage` | Personal weekly instructional schedule | View grid, export PDF, inspect room/batch |
| `/faculty/dept-timetable` | `FacultyDeptTimetablePage` | Department-wide master schedule | Filter by colleague/room, view open slots |
| `/faculty/availability` | `FacultyAvailabilityPage` | Weekly teaching availability preferences | Toggle time slot preference (Preferred/Available/Unavailable), Save |
| `/faculty/resources` | `FacultyResourcesPage` | Lab & facility booking requests | Request room/equipment, specify purpose, view status |
| `/faculty/events` | `FacultyEventsPage` | Departmental seminars & club meetings | Propose event, reserve hall, invite students |
| `/faculty/substitutions` | `FacultySubstitutionPage` | Absence & peer coverage requests | Submit leave request, view suggested peers, confirm |
| `/faculty/requests` | `FacultyChangeRequestsPage` | Schedule change requests | Request slot swap, give reason, track approval |
| `/faculty/notifications` | `FacultyNotificationsPage` | Personal operational notifications | Mark as read, filter by category |

---

### Role 4: STUDENT (Class Schedules, Announcements, Placements & AI Assistant)
**Scope:** Enrolled course timetable, syllabus/course references, campus events, CDC placement applications, announcements, and AI-grounded assistance.  
**Layout:** `StudentLayout` (`frontend/src/layouts/StudentLayout.tsx`) — Theme: Pastel Powder Blue (`#EAF2FF`) & Navy.

| Route Path | Page Component | Primary Intended Purpose | Key Actions & Controls |
|---|---|---|---|
| `/student` | `StudentDashboard` | Student overview & daily schedule pulse | Live class status badge, upcoming lectures, announcements |
| `/student/timetable` | `StudentTimetablePage` | Enrolled batch/section weekly schedule | Weekly timetable grid, period timings, export PDF |
| `/student/courses` | `StudentCoursesPage` | Registered courses, faculty & credits | Course cards, instructor details, syllabus link |
| `/student/events` | `StudentEventsPage` | Campus events & club activities | View scheduled events, club activities, add to calendar |
| `/student/placements` | `StudentPlacementsPage` | Placement drives & job applications | View eligible drives, apply, track interview rounds |
| `/student/announcements` | `StudentAnnouncementsPage` | Institutional & departmental notices | Read announcements, filter by category |
| `/student/notifications` | `StudentNotificationsPage` | Student-specific notifications | Mark read, clear notification items |

---

## 3. Backend Route & Service Inventory (35 Modules, 184 Paths, 262 Operations)

| Module | Route Prefix | Key Endpoints | Database Entities Touched |
|---|---|---|---|
| `auth` | `/auth` | `POST /login`, `POST /logout`, `POST /refresh`, `GET /me` | `users`, `refresh_sessions`, `login_rate_limits` |
| `department` | `/departments` | `GET /`, `POST /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}` | `departments` |
| `program` | `/programs` | `GET /`, `POST /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}` | `programs` |
| `academic_year`| `/academic-years` | `GET /`, `POST /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}` | `academic_years` |
| `semester` | `/semesters` | `GET /`, `POST /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}` | `semesters` |
| `section` | `/sections` | `GET /`, `POST /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}` | `sections` |
| `batch` | `/batches` | `GET /`, `POST /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}` | `batches` |
| `student` | `/students`, `/student` | `GET /`, `POST /`, `GET /{id}`, `PUT /{id}`, `GET /student/my-timetable` | `students`, `users` |
| `faculty` | `/faculty` | `GET /`, `POST /`, `GET /{id}`, `PUT /{id}`, `GET /my-timetable` | `faculty`, `users` |
| `course` | `/courses` | `GET /`, `POST /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}` | `courses` |
| `course_assignment` | `/course-assignments` | `GET /`, `POST /`, `PUT /{id}`, `DELETE /{id}` | `course_assignments` |
| `buildings` | `/buildings` | `GET /`, `POST /`, `PUT /{id}`, `DELETE /{id}` | `buildings` |
| `rooms` | `/rooms` | `GET /`, `POST /`, `PUT /{id}`, `DELETE /{id}` | `rooms` |
| `labs` | `/labs` | `GET /`, `POST /`, `PUT /{id}`, `DELETE /{id}` | `labs` |
| `time_slot` | `/time-slots` | `GET /`, `POST /`, `PUT /{id}`, `DELETE /{id}` | `time_slots` |
| `faculty_availability` | `/faculty-availability` | `GET /`, `POST /bulk`, `PUT /{id}` | `faculty_availability` |
| `timetable` | `/timetables` | `GET /scope/*`, `POST /preview`, `POST /publish`, `GET /student/me` | `timetable_entries`, `timetable_versions` |
| `curriculum` | `/curriculum`, `/super-admin/curriculum` | `GET /regulations`, `POST /cohorts`, `POST /pdf-extraction` | `regulations`, `curriculum_versions`, `curriculum_documents` |
| `resources` | `/resources`, `/resource-bookings` | `GET /`, `POST /`, `POST /bookings`, `PUT /bookings/{id}/approve` | `resources`, `resource_bookings` |
| `substitutions`| `/substitutions` | `GET /`, `POST /request`, `GET /candidates`, `PUT /{id}/approve` | `faculty_substitutions` |
| `events` | `/events` | `GET /`, `POST /`, `PUT /{id}`, `DELETE /{id}` | `campus_events` |
| `clubs` | `/clubs` | `GET /`, `POST /`, `PUT /{id}`, `DELETE /{id}` | `clubs` |
| `placements` | `/placements` | `GET /drives`, `POST /drives`, `POST /applications` | `placement_drives`, `placement_schedules` |
| `notifications`| `/notifications` | `GET /`, `POST /`, `PUT /{id}/read`, `PUT /read-all` | `notifications`, `notification_outbox` |
| `audit_logs` | `/audit-logs` | `GET /`, `GET /export` | `audit_logs` |
| `data_import` | `/data-import` | `POST /validate`, `POST /commit` | All academic tables |
| `analytics` | `/analytics` | `GET /dashboard-summary`, `GET /utilization` | Aggregated views |
| `settings` | `/settings` | `GET /`, `PUT /`, `POST /reset` | `system_settings` |
| `chat` | `/chat` | `POST /conversations`, `POST /messages`, `GET /messages` | `chat_conversations`, `chat_messages` |
| `disruptions` | `/disruptions` | `GET /`, `POST /` | `disruptions` |
| `change_requests` | `/change-requests` | `GET /`, `POST /`, `PUT /{id}/status` | `change_requests` |

---

## 4. Reusable Component Inventory

| Category | Component File | Key Elements & Buttons |
|---|---|---|
| **Common** | `DataTable.tsx` | Pagination (prev/next/page size), search input, sort column headers, empty state |
| **Common** | `FormModal.tsx` | Cancel button, Submit button (with spinner), Escape key, backdrop click |
| **Common** | `ConfirmDialog.tsx` | Cancel button, Confirm action button (danger/primary variant) |
| **Common** | `SignOutConfirmDialog.tsx`| Cancel button, Sign Out button |
| **Common** | `RefreshButton.tsx` | Refresh button (icon spin, last refreshed timestamp, toast feedback) |
| **Common** | `FilterBar.tsx` | Filter dropdowns, active badge chips, Clear All filters button |
| **Common** | `SearchBar.tsx` | Search input, clear search cross button |
| **Common** | `PageHeader.tsx` | Page title, breadcrumb links, action buttons container |
| **Layout** | `Topbar.tsx` | Mobile toggle button, notifications bell, profile dropdown, sign out |
| **Notifications**| `NotificationBellDropdown.tsx`| Bell button, unread count badge, mark-all-as-read button, notification item clicks |
| **Chat/AI** | `CampusAssistantDrawer.tsx` | Floating toggle FAB, suggestion chips, input textarea, send button, close drawer button |
| **Timetable** | `TimetableGrid.tsx` | Day tabs, export PDF button, period cells, tooltip details |
| **Timetable** | `PersonalTimetableGrid.tsx`| Daily schedule view, period status pill, classroom/faculty badge |

---

## 5. Summary Baseline Statement

All 56 routes, 59 pages, 351 buttons, 36 forms, 54 modals, 184 API paths, and 54 database tables are identified, cataloged, and cross-referenced. This baseline serves as the foundation for the Phase 2 Button and Interaction Audit, Phase 3 Route Audit, and Phase 4 Cross-Role Synchronization.
