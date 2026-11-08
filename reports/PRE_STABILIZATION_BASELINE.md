# RIO-MJP — Pre-Stabilization Baseline Audit Report

**Date & Time:** November 7, 2026  
**Auditor Roles:** Senior Software Architect, Full-Stack Integration Engineer, QA & Database Specialist  
**Repository:** `RIO-MJP` (Main Branch)  
**Target Database:** `campus_ai_test` (Port 5433, Schema `test_schema`)  
**Protected Database:** `campus_ai` (Port 5432 — Strictly Untouched)  
**Primary Objective:** Comprehensive baseline audit of existing modules, API routes, database entities, frontend routes, static analysis diagnostics, and git status prior to complete codebase stabilization.

---

## 1. Executive Baseline Summary

| Dimension | Measured Metric | Baseline Status | Notes / Key Observations |
|:---|:---:|:---:|:---|
| **Database Schema Tables** | 53 tables | 🟢 Operational | Isolated port 5433 (`campus_ai_test` / `test_schema`); backup verified (313 KB) |
| **OpenAPI Registered Paths** | 175 paths | 🟢 Registered | 253 distinct HTTP operations across 36 route modules |
| **Frontend API Clients** | 29 client modules | 🟡 Needs Alignment | `frontend/src/api/*.ts` interfacing backend services |
| **Frontend Pages & Routes** | 58 pages | 🟢 Operational | Defined in `AppRoutes.tsx` with role guards (`SUPER_ADMIN`, `ADMIN`, `FACULTY`, `STUDENT`) |
| **Frontend TypeScript Build** | `tsc -b && vite build` | 🟢 0 errors | Production bundle built cleanly in 2.13s |
| **Frontend Linter (Oxlint)** | 4 warnings, 0 errors | 🟡 4 warnings | 3 Fast-refresh component exports, 1 `set-state-in-effect` in `AdminTimetableManagementPage.tsx` |
| **Backend Type Checker (Pyright)**| 26 errors | 🔴 26 diagnostics | Room dynamic attributes, missing `Semester` import in `section.py`, nullable field types |
| **Authoritative Workbook** | Complete (AIDS-A) | 🟢 In sync | 60 students, 10 faculty, 18 subjects, 1 building, 9 floors, 225 rooms, 18 labs |
| **Intended Test Accounts** | Exactly 72 accounts | 🟢 Verified | 1 SUPER_ADMIN, 1 ADMIN, 10 FACULTY, 60 STUDENT; all authenticating successfully |
| **Live Browser Verification** | Playwright Chromium | 🟢 100% Pass | Verified Admin, Faculty, and Student workflows with zero crashes (`reports/screenshots/`) |

---

## 2. Existing Database Entities & Table Inventory

Database: `campus_ai_test` (Port 5433) | Schema: `test_schema` | Total Tables: **53**

| Table Name | Row Count | Domain Responsibility |
|:---|:---:|:---|
| `academic_calendar` | 8 | Academic milestones, semester terms, and operational events |
| `academic_years` | 1 | Academic year lifecycle (2026–2027) |
| `admission_cohorts` | 0 | Super Admin admission cohort groupings |
| `agent_proposals` | 0 | AI agent change proposals and recommendations |
| `alembic_version` | 1 | Database migration head marker (`e4f5a6b7c8d9`) |
| `audit_logs` | 10 | Security, authentication, and administrative audit trails |
| `batches` | 11 | Section student batch divisions (e.g. A1, A2, A3) |
| `buildings` | 3 | Campus building infrastructure (SIR M VISHWESH BLOCK, etc.) |
| `campus_events` | 0 | Institutional and departmental calendar events |
| `change_requests` | 0 | Administrative and faculty change request tickets |
| `chat_conversations` | 0 | Multi-turn campus assistant conversation threads |
| `chat_messages` | 0 | Campus assistant conversation messages |
| `clubs` | 0 | Student club and chapter registries |
| `coordinator_capabilities` | 0 | Department coordinator role and capability grants |
| `course_assignments` | 44 | Faculty-to-subject workload allocations |
| `courses` | 33 | Course master definitions (Theory, Practical, Elective) |
| `curriculum_documents` | 0 | Uploaded syllabus and curriculum regulation PDFs |
| `curriculum_extraction_jobs` | 0 | Background PDF extraction processing jobs |
| `curriculum_releases` | 0 | Published curriculum release snapshots |
| `curriculum_request_messages` | 0 | Curriculum inquiry conversation messages |
| `curriculum_requests` | 0 | Department curriculum revision requests |
| `curriculum_semesters` | 0 | Curriculum regulation semester structures |
| `curriculum_subject_mappings` | 0 | Curriculum subject equivalency mappings |
| `curriculum_versions` | 0 | Curriculum version governance records |
| `departments` | 4 | Academic departments (AIDS, CSE, AIML, ISE) |
| `elective_group_courses` | 14 | Mapping courses into elective elective buckets |
| `elective_groups` | 9 | Professional and open elective grouping containers |
| `faculty` | 20 | Faculty profiles, designations, and department affiliations |
| `faculty_availability` | 1,260 | Day-by-day and period-by-period faculty availability matrix |
| `faculty_course_offerings` | 0 | Semester course offering preferences |
| `faculty_substitutions` | 0 | Temporary faculty leave substitution assignments |
| `labs` | 19 | Department computing and specialized laboratories |
| `login_rate_limits` | 3 | IP and user authentication throttling tracking |
| `notification_outbox` | 66 | Asynchronous notification delivery queue |
| `notifications` | 66 | In-app user notifications across roles |
| `placement_drives` | 0 | Career Development Centre corporate drives |
| `placement_schedules` | 0 | Interview and written assessment rounds |
| `programs` | 4 | Degree programs (B.Tech AI & DS, etc.) |
| `refresh_sessions` | 16 | Active JWT refresh token session states |
| `regulations` | 0 | Academic regulations (e.g. 2022 Scheme, 2026 Scheme) |
| `resource_bookings` | 0 | Room, hall, and lab reservation bookings |
| `resources` | 2 | Specialized equipment and venue resource catalog |
| `rooms` | 235 | Campus classrooms, lecture halls, and facilities |
| `section_course_offerings` | 0 | Section-level elective course choices |
| `sections` | 6 | Department cohort sections (AIDS-A, etc.) |
| `semesters` | 3 | Semester structures (Semester 3, 5, 7) |
| `student_academic_records` | 0 | Student GPA, credits, and historical marks |
| `students` | 294 | Student records (includes authoritative 60 AIDS-A cohort) |
| `time_slots` | 108 | Weekly instructional and break interval definitions |
| `timetable_entries` | 42 | Canonical scheduled class sessions |
| `timetable_versions` | 3 | Legacy reference versions (retained for backward compatibility) |
| `timetables` | 1 | Canonical Timetable (Academic Year 1, Semester 3, Section 6) |
| `users` | 315 | System authentication accounts |

---

## 3. Existing Modules & Architectural Layers

The application comprises 7 primary business domains, structured cleanly across:
`Database (PostgreSQL 5433)` $\rightarrow$ `SQLAlchemy Models` $\rightarrow$ `Domain Services` $\rightarrow$ `FastAPI Routes` $\rightarrow$ `Axios Clients` $\rightarrow$ `React Pages`.

1. **Identity & RBAC:**
   - Routes: `backend/routes/auth.py`, `backend/routes/users.py`, `backend/routes/audit_logs.py`
   - Client: `frontend/src/api/auth.ts`, `frontend/src/api/users.ts`
   - UI: `Login.tsx`, `UsersPage.tsx`, `AdminAuditLogsPage.tsx`
2. **Academic Structure & Governance:**
   - Routes: `academic_year.py`, `semester.py`, `department.py`, `program.py`, `section.py`, `batch.py`, `course.py`, `course_assignment.py`, `curriculum.py`
   - Clients: `departments.ts`, `programs.ts`, `academicYears.ts`, `semesters.ts`, `sections.ts`, `batches.ts`, `courses.ts`, `courseAssignments.ts`, `curriculum.ts`
   - UI: `DepartmentsPage.tsx`, `ProgramsPage.tsx`, `AcademicYearsPage.tsx`, `SemestersPage.tsx`, `BatchesPage.tsx`, `SectionsPage.tsx`, `CoursesPage.tsx`, `SuperAdminRegulationsPage.tsx`, `SuperAdminCurriculumVersionsPage.tsx`
3. **People (Faculty & Students):**
   - Routes: `backend/routes/faculty.py`, `backend/routes/student.py`, `backend/routes/faculty_availability.py`
   - Clients: `faculty.ts`, `students.ts`, `facultyAvailability.ts`
   - UI: `FacultyPage.tsx`, `StudentsPage.tsx`, `FacultyAvailabilityPage.tsx`, `StudentCoursesPage.tsx`
4. **Campus Infrastructure & Resources:**
   - Routes: `backend/routes/buildings.py`, `backend/routes/rooms.py`, `backend/routes/labs.py`, `backend/routes/resources.py`
   - Clients: `buildings.ts`, `rooms.ts`, `resources.ts`
   - UI: `BuildingsPage.tsx`, `RoomsPage.tsx`, `ResourcesPage.tsx`, `FacultyResourcesPage.tsx`
5. **Timetable System (Simplified Canonical):**
   - Routes: `backend/routes/timetable.py`, `backend/routes/time_slot.py`
   - Engine: `backend/optimizer/timetable_solver.py` (OR-Tools CP-SAT) & `backend/optimizer/validator.py`
   - Service: `backend/services/timetable_service.py`, `backend/services/timetable_input_loader.py`
   - Clients: `timetable.ts`, `timeSlots.ts`
   - UI: `AdminTimetableManagementPage.tsx`, `FacultyTimetablePage.tsx`, `FacultyDeptTimetablePage.tsx`, `StudentTimetablePage.tsx`
6. **Campus Operations & Student Life:**
   - Routes: `backend/routes/events.py`, `backend/routes/clubs.py`, `backend/routes/placements.py`, `backend/routes/substitutions.py`, `backend/routes/change_requests.py`
   - Clients: `events.ts`, `placements.ts`, `substitutions.ts`
   - UI: `AdminEventsPage.tsx`, `AdminPlacementsPage.tsx`, `AdminSubstitutionPage.tsx`, `FacultyEventsPage.tsx`, `FacultySubstitutionPage.tsx`, `StudentEventsPage.tsx`, `StudentPlacementsPage.tsx`
7. **Assistant, Communication & Reporting:**
   - Routes: `backend/routes/chat.py`, `backend/routes/notifications.py`, `backend/routes/analytics.py`, `backend/routes/data_import.py`
   - Clients: `chat.ts`, `notifications.ts`, `analytics.ts`, `dataImport.ts`
   - UI: `CampusAssistantDrawer.tsx`, `AdminNotificationsPage.tsx`, `FacultyNotificationsPage.tsx`, `StudentNotificationsPage.tsx`, `ReportsPage.tsx`, `ImportValidationPage.tsx`

---

## 4. Current Diagnostics & Issues Identified for Stabilization

### 4.1 Backend Pyright Diagnostics (26 errors)
1. **Dynamic Attribute Assignment in SQLAlchemy Models (`backend/routes/rooms.py`):**
   - Lines 23, 24, 41, 42: Assigning `r.building_name = ...` and `r.building_code = ...` directly to SQLAlchemy `Room` instances.
   - *Fix:* Construct response dictionaries or Pydantic instances cleanly instead of mutating ORM entities.
2. **Missing Model Import (`backend/routes/section.py`):**
   - Lines 37, 38: Reference to `Semester` in query filter without importing `Semester` from `backend.models.academic`.
   - *Fix:* Add `Semester` to imports from `backend.models.academic`.
3. **Optional / Nullable Type Incompatibilities (`backend/services/timetable_service.py`):**
   - Lines 268, 269, 307, 330, 333, 334, 335, 341, 344, 347, 361, 362: Nullable strings and integers passed where non-nullable types are required by schemas.
   - *Fix:* Provide safe fallback defaults (`name or ""` or `val or 0`) or update Pydantic models to `Optional[str]`.
4. **Playwright Script Type Nullability (`scripts/live_browser_dom_verification.py`):**
   - Lines 133, 138: Missing `assert` or check before calling `.click()` on nullable element handles.
5. **Test Assertions Nullability (`tests/api/test_canonical_timetable_workflow.py`):**
   - Lines 120, 129, 130, 131, 132: Calling `.id` on query result that could be `None`.

### 4.2 Frontend Oxlint Warnings (4 warnings)
1. **State Update in Effect (`frontend/src/pages/admin/timetable/AdminTimetableManagementPage.tsx`):**
   - Line 118: Calling `setActiveSectionId(...)` synchronously inside `useEffect`.
   - *Fix:* Guard or derive active section cleanly.
2. **Fast-Refresh Non-Component Exports (`AuthProvider.tsx` & `NotificationContext.tsx`):**
   - Fast refresh warning on helper/hook exports co-located in context provider files.

---

## 5. Git Status & Uncommitted Working State

The local working copy contains uncommitted improvements from the canonical timetable refactoring and live reproduction fixes:
- **Modified Backend:** `academic.py`, `timetable.py`, `rooms.py`, `section.py`, `timetable.py`, `timetable_solver.py`, `validator.py`, `timetable_service.py`, `timetable_input_loader.py`.
- **Modified Frontend:** `AdminTimetableManagementPage.tsx`, `RoomsPage.tsx`, `BuildingsPage.tsx`, `AppRoutes.tsx`, `PersonalTimetableGrid.tsx`, `AdminSidebar.tsx`.
- **Untracked Additions:** `reports/`, `scripts/live_browser_dom_verification.py`, `tests/api/test_canonical_timetable_workflow.py`.

Zero git commits or pushes have been performed. All changes will be stabilized in place without resetting or discarding user work.

