# RIO-MJP — Complete API Route & Operation Inventory

**Audit Date:** November 8, 2026  
**Backend Framework:** FastAPI / Uvicorn  
**Total Registered Paths:** 175  
**Total HTTP Operations:** 253  
**Target Environment:** Isolated Test Environment (`http://127.0.0.1:8000` / PostgreSQL port 5433 `campus_ai_test`)  
**Protected Database:** Port 5432 `campus_ai` (Strictly Untouched)

---

## 1. Executive Summary of API Surface

The RIO-MJP backend exposes 253 distinct HTTP operations across 36 modular router files registered in `backend/main.py`.  
Authentication is managed via OAuth2 Password Bearer (`/auth/login`) with role-based access control (`SUPER_ADMIN`, `ADMIN`, `FACULTY`, `STUDENT`) enforced using FastAPI dependencies (`require_role`, `get_current_user`).

| Domain | Route Module | Prefix / Scope | Operations | Required Roles | Frontend Client |
|:---|:---|:---|:---:|:---|:---|
| **System** | `backend/main.py` | `/health` | 1 | Public | None (Probe) |
| **Auth & Identity** | `backend/routes/auth.py` | `/auth` | 4 | Public / All | `src/api/auth.ts` |
| **Audit Logs** | `backend/routes/audit_logs.py` | `/admin/audit-logs` | 1 | `ADMIN`, `SUPER_ADMIN` | `src/api/auditLogs.ts` |
| **User Management** | `backend/routes/users.py` | `/users` | 6 | `ADMIN` | `src/api/users.ts` |
| **Academic Years** | `backend/routes/academic_year.py` | `/academic-years` | 5 | `ADMIN` | `src/api/academicYears.ts` |
| **Semesters** | `backend/routes/semester.py` | `/semesters` | 5 | `ADMIN` | `src/api/semesters.ts` |
| **Departments** | `backend/routes/department.py` | `/departments` | 5 | `ADMIN` | `src/api/departments.ts` |
| **Programs** | `backend/routes/program.py` | `/programs` | 5 | `ADMIN` | `src/api/programs.ts` |
| **Sections** | `backend/routes/section.py` | `/sections` | 6 | `ADMIN` | `src/api/sections.ts` |
| **Batches** | `backend/routes/batch.py` | `/batches` | 5 | `ADMIN` | `src/api/batches.ts` |
| **Students (Admin)** | `backend/routes/student.py` | `/students` | 5 | `ADMIN` | `src/api/students.ts` |
| **Students (Portal)** | `backend/routes/student.py` | `/student` | 4 | `STUDENT` | `src/api/students.ts` |
| **Faculty (Admin/Portal)** | `backend/routes/faculty.py` | `/faculty` | 10 | `ADMIN`, `FACULTY` | `src/api/faculty.ts` |
| **Faculty Availability** | `backend/routes/faculty_availability.py` | `/faculty-availability` | 6 | `ADMIN`, `FACULTY` | `src/api/facultyAvailability.ts` |
| **Courses** | `backend/routes/course.py` | `/courses` | 5 | `ADMIN` | `src/api/courses.ts` |
| **Course Allocations** | `backend/routes/course_assignment.py` | `/course-assignments` | 6 | `ADMIN` | `src/api/courseAssignments.ts` |
| **Elective Groups** | `backend/routes/elective_group.py` | `/elective-groups` | 5 | `ADMIN` | `src/api/electiveGroups.ts` |
| **Elective Mapping** | `backend/routes/elective_group_course.py` | `/elective-group-courses` | 5 | `ADMIN` | `src/api/electiveGroupCourses.ts` |
| **Buildings** | `backend/routes/buildings.py` | `/buildings` | 5 | `ADMIN` | `src/api/buildings.ts` |
| **Rooms** | `backend/routes/rooms.py` | `/rooms` | 5 | `ADMIN` | `src/api/rooms.ts` |
| **Labs** | `backend/routes/labs.py` | `/labs` | 5 | `ADMIN` | `src/api/labs.ts` |
| **Time Slots** | `backend/routes/time_slot.py` | `/time-slots` | 5 | `ADMIN` | `src/api/timeSlots.ts` |
| **Academic Calendar** | `backend/routes/academic_calendar.py` | `/academic-calendar` | 5 | `ADMIN` | `src/api/academicCalendar.ts` |
| **Campus Resources** | `backend/routes/resources.py` | `/resources` | 7 | `ADMIN`, `FACULTY` | `src/api/resources.ts` |
| **Events** | `backend/routes/events.py` | `/events` | 7 | All Roles | `src/api/events.ts` |
| **Clubs** | `backend/routes/clubs.py` | `/clubs` | 5 | All Roles | `src/api/clubs.ts` |
| **Placements (CDC)** | `backend/routes/placements.py` | `/placements` | 10 | `ADMIN`, `STUDENT` | `src/api/placements.ts` |
| **Faculty Substitution**| `backend/routes/substitutions.py` | `/substitutions` | 8 | `ADMIN`, `FACULTY` | `src/api/substitutions.ts` |
| **Timetable (Legacy)** | `backend/routes/timetable.py` | `/timetable` (versions) | 12 | `ADMIN` | `src/api/timetable.ts` |
| **Timetable (Canonical)**| `backend/routes/timetable.py` | `/timetable` (preview/publish)| 6 | `ADMIN`, `FACULTY`, `STUDENT` | `src/api/timetable.ts` |
| **Curriculum Core** | `backend/routes/curriculum.py` | `/curriculum` | 12 | `ADMIN`, `SUPER_ADMIN` | `src/api/curriculum.ts` |
| **Super Admin Governance**| `backend/routes/curriculum.py` | `/super-admin` | 14 | `SUPER_ADMIN` | `src/api/curriculum.ts` |
| **Department Curriculum**| `backend/routes/curriculum.py` | `/admin/curriculum` | 6 | `ADMIN` | `src/api/curriculum.ts` |
| **Campus Assistant (AI)** | `backend/routes/chat.py` | `/chat` | 4 | All Roles | `src/api/chat.ts` |
| **Notifications** | `backend/routes/notifications.py` | `/notifications` | 5 | All Roles | `src/api/notifications.ts` |
| **Disruptions** | `backend/routes/disruptions.py` | `/disruptions` | 4 | `ADMIN` | `src/api/disruptions.ts` |
| **Analytics** | `backend/routes/analytics.py` | `/analytics` | 4 | `ADMIN` | `src/api/analytics.ts` |
| **Data Import** | `backend/routes/data_import.py` | `/data-import` | 3 | `ADMIN` | `src/api/dataImport.ts` |
| **Change Requests** | `backend/routes/change_requests.py` | `/change-requests` | 5 | `ADMIN`, `FACULTY` | `src/api/changeRequests.ts` |

---

## 2. Detailed Route Inventory by Subsystem

### 2.1 Authentication & User Identity (`/auth`, `/users`)

| Method | Endpoint Path | Handler Function | Auth / Role | Database Model | Frontend Consumer | Status |
|:---:|:---|:---|:---:|:---|:---|:---:|
| `POST` | `/auth/login` | `login()` | Public | `User`, `LoginRateLimit` | `auth.ts` -> `login()` | 🟢 Working |
| `POST` | `/auth/refresh` | `refresh_token()` | Refresh Cookie | `RefreshSession`, `User` | `client.ts` interceptor | 🟢 Working |
| `POST` | `/auth/logout` | `logout()` | Authenticated | `RefreshSession` | `auth.ts` -> `logout()` | 🟢 Working |
| `GET` | `/auth/me` | `get_current_user_profile()` | All Roles | `User`, `Student`, `Faculty` | `auth.ts` -> `getCurrentUser()` | 🟢 Working |
| `GET` | `/users` | `get_users()` | `ADMIN` | `User`, `Department` | `users.ts` -> `getUsers()` | 🟢 Working |
| `POST` | `/users` | `create_user()` | `ADMIN` | `User` | `users.ts` -> `createUser()` | 🟢 Working |
| `GET` | `/users/{id}` | `get_user()` | `ADMIN` | `User` | `users.ts` -> `getUserById()` | 🟢 Working |
| `PUT` | `/users/{id}` | `update_user()` | `ADMIN` | `User` | `users.ts` -> `updateUser()` | 🟢 Working |
| `DELETE`| `/users/{id}` | `delete_user()` | `ADMIN` | `User` | `users.ts` -> `deleteUser()` | 🟢 Working |
| `POST` | `/users/{id}/reset-password` | `reset_user_password()` | `ADMIN` | `User`, `AuditLog` | `users.ts` -> `resetPassword()` | 🟢 Working |

### 2.2 Academic Structure (`/academic-years`, `/semesters`, `/departments`, `/programs`, `/sections`, `/batches`, `/students`, `/faculty`)

| Method | Endpoint Path | Handler Function | Auth / Role | Database Model | Frontend Consumer | Status |
|:---:|:---|:---|:---:|:---|:---|:---:|
| `GET` | `/academic-years` | `get_academic_years()` | `ADMIN` | `AcademicYear` | `academicYears.ts` | 🟢 Working |
| `POST` | `/academic-years` | `create_academic_year()`| `ADMIN` | `AcademicYear` | `academicYears.ts` | 🟢 Working |
| `GET` | `/academic-years/{id}`| `get_academic_year()` | `ADMIN` | `AcademicYear` | `academicYears.ts` | 🟢 Working |
| `PUT` | `/academic-years/{id}`| `update_academic_year()`| `ADMIN` | `AcademicYear` | `academicYears.ts` | 🟢 Working |
| `DELETE`| `/academic-years/{id}`| `delete_academic_year()`| `ADMIN` | `AcademicYear` | `academicYears.ts` | 🟢 Working |
| `GET` | `/semesters` | `get_semesters()` | `ADMIN` | `Semester` | `semesters.ts` | 🟢 Working |
| `POST` | `/semesters` | `create_semester()` | `ADMIN` | `Semester` | `semesters.ts` | 🟢 Working |
| `GET` | `/semesters/{id}` | `get_semester()` | `ADMIN` | `Semester` | `semesters.ts` | 🟢 Working |
| `PUT` | `/semesters/{id}` | `update_semester()` | `ADMIN` | `Semester` | `semesters.ts` | 🟢 Working |
| `DELETE`| `/semesters/{id}` | `delete_semester()` | `ADMIN` | `Semester` | `semesters.ts` | 🟢 Working |
| `GET` | `/departments` | `get_departments()` | `ADMIN` | `Department` | `departments.ts` | 🟢 Working |
| `POST` | `/departments` | `create_department()` | `ADMIN` | `Department` | `departments.ts` | 🟢 Working |
| `GET` | `/departments/{id}` | `get_department()` | `ADMIN` | `Department` | `departments.ts` | 🟢 Working |
| `PUT` | `/departments/{id}` | `update_department()` | `ADMIN` | `Department` | `departments.ts` | 🟢 Working |
| `DELETE`| `/departments/{id}` | `delete_department()` | `ADMIN` | `Department` | `departments.ts` | 🟢 Working |
| `GET` | `/sections` | `get_sections()` | `ADMIN` | `Section` | `sections.ts` | 🟢 Working |
| `POST` | `/sections` | `create_section()` | `ADMIN` | `Section` | `sections.ts` | 🟢 Working |
| `GET` | `/sections/{id}` | `get_section()` | `ADMIN` | `Section` | `sections.ts` | 🟢 Working |
| `PUT` | `/sections/{id}` | `update_section()` | `ADMIN` | `Section` | `sections.ts` | 🟢 Working |
| `DELETE`| `/sections/{id}` | `delete_section()` | `ADMIN` | `Section` | `sections.ts` | 🟢 Working |
| `GET` | `/sections/{id}/students` | `get_section_students()` | `ADMIN` | `Student` | `sections.ts` | 🟢 Working |
| `GET` | `/students` | `get_students()` | `ADMIN` | `Student` | `students.ts` | 🟢 Working |
| `POST` | `/students` | `create_student()` | `ADMIN` | `Student`, `User` | `students.ts` | 🟢 Working |
| `GET` | `/students/{id}` | `get_student()` | `ADMIN` | `Student` | `students.ts` | 🟢 Working |
| `PUT` | `/students/{id}` | `update_student()` | `ADMIN` | `Student` | `students.ts` | 🟢 Working |
| `DELETE`| `/students/{id}` | `delete_student()` | `ADMIN` | `Student` | `students.ts` | 🟢 Working |
| `GET` | `/student/my-timetable` | `get_my_student_timetable()` | `STUDENT` | `Timetable`, `TimetableEntry` | `students.ts` -> `getMyTimetable()` | 🟢 Working (42 entries) |
| `GET` | `/student/my-section` | `get_my_section()` | `STUDENT` | `Section`, `Faculty` | `students.ts` | 🟢 Working |
| `GET` | `/student/class-teacher` | `get_class_teacher()` | `STUDENT` | `Faculty`, `Section` | `students.ts` | 🟢 Working |
| `GET` | `/faculty` | `get_faculty_list()` | `ADMIN` | `Faculty` | `faculty.ts` | 🟢 Working |
| `POST` | `/faculty` | `create_faculty()` | `ADMIN` | `Faculty`, `User` | `faculty.ts` | 🟢 Working |
| `GET` | `/faculty/{id}` | `get_faculty_member()` | `ADMIN` | `Faculty` | `faculty.ts` | 🟢 Working |
| `GET` | `/faculty/me/timetable` | `get_my_teaching_timetable()`| `FACULTY`| `TimetableEntry`, `Course` | `faculty.ts` -> `getMyFacultyTimetable()`| 🟢 Working |
| `GET` | `/faculty/me/department-timetable`| `get_my_department_timetable()`| `FACULTY`| `TimetableEntry`, `Section`| `faculty.ts` | 🟢 Working |

### 2.3 Campus Infrastructure (`/buildings`, `/rooms`, `/labs`, `/time-slots`, `/resources`)

| Method | Endpoint Path | Handler Function | Auth / Role | Database Model | Frontend Consumer | Status |
|:---:|:---|:---|:---:|:---|:---|:---:|
| `GET` | `/buildings` | `get_buildings()` | `ADMIN` | `Building`, `Room` | `buildings.ts` | 🟢 Working |
| `POST` | `/buildings` | `create_building()` | `ADMIN` | `Building` | `buildings.ts` | 🟢 Working |
| `GET` | `/buildings/{id}` | `get_building()` | `ADMIN` | `Building` | `buildings.ts` | 🟢 Working |
| `PUT` | `/buildings/{id}` | `update_building()` | `ADMIN` | `Building` | `buildings.ts` | 🟢 Working |
| `DELETE`| `/buildings/{id}` | `delete_building()` | `ADMIN` | `Building` | `buildings.ts` | 🟢 Working |
| `GET` | `/rooms` | `get_rooms()` | `ADMIN` | `Room`, `Building` | `rooms.ts` | 🟢 Working (Fixed 500) |
| `POST` | `/rooms` | `create_room()` | `ADMIN` | `Room` | `rooms.ts` | 🟢 Working |
| `GET` | `/rooms/{id}` | `get_room()` | `ADMIN` | `Room` | `rooms.ts` | 🟢 Working |
| `PUT` | `/rooms/{id}` | `update_room()` | `ADMIN` | `Room` | `rooms.ts` | 🟢 Working |
| `DELETE`| `/rooms/{id}` | `delete_room()` | `ADMIN` | `Room` | `rooms.ts` | 🟢 Working |
| `GET` | `/labs` | `get_labs()` | `ADMIN` | `Lab`, `Room` | `labs.ts` | 🟢 Working |
| `GET` | `/time-slots` | `get_time_slots()` | `ADMIN` | `TimeSlot` | `timeSlots.ts` | 🟡 Dual formats |
| `GET` | `/resources` | `get_resources()` | All Roles | `Resource` | `resources.ts` | 🟢 Working |
| `POST` | `/resources/bookings` | `create_booking()` | `ADMIN`, `FACULTY` | `ResourceBooking` | `resources.ts` | 🟢 Working |

### 2.4 Timetable Subsystem (`/timetable`)

| Method | Endpoint Path | Handler Function | Auth / Role | Database Model | Frontend Consumer | Status |
|:---:|:---|:---|:---:|:---|:---|:---:|
| `GET` | `/timetable/academic-years` | `get_timetable_academic_years()` | `ADMIN` | `AcademicYear` | `AdminTimetableManagementPage.tsx` | 🟢 Working |
| `GET` | `/timetable/semesters` | `get_timetable_semesters()` | `ADMIN` | `Semester` | `AdminTimetableManagementPage.tsx` | 🟢 Working |
| `GET` | `/timetable/departments` | `get_timetable_departments()` | `ADMIN` | `Department` | `AdminTimetableManagementPage.tsx` | 🟢 Working (`department_code`) |
| `GET` | `/timetable/sections` | `get_timetable_sections()` | `ADMIN` | `Section` | `AdminTimetableManagementPage.tsx` | 🟢 Working |
| `GET` | `/timetable/canonical` | `get_canonical_timetables_route()`| `ADMIN` | `Timetable`, `TimetableEntry` | `AdminTimetableManagementPage.tsx` | 🟢 Working |
| `POST` | `/timetable/generate-preview` | `generate_timetable_preview_route()`| `ADMIN`| None (In-Memory Solver) | `AdminTimetableManagementPage.tsx` | 🟡 Working (Uses slot 1-54) |
| `POST` | `/timetable/publish` | `publish_canonical_timetable_route()`| `ADMIN`| `Timetable`, `TimetableEntry` | `AdminTimetableManagementPage.tsx` | 🟢 Working |
| `GET` | `/timetable/canonical/section/{sec_id}` | `get_canonical_timetable_by_section()`| All | `Timetable`, `TimetableEntry` | Student / Faculty portals | 🟢 Working |
| `GET` | `/timetable/versions` | `get_timetable_versions()` | `ADMIN` | `TimetableVersion` | Legacy Timetable pages | 🟡 Legacy preserved |
| `POST` | `/timetable/generate` | `generate_timetable_endpoint()` | `ADMIN` | `TimetableVersion` (legacy draft) | Legacy solver endpoint | 🟡 Legacy draft |

### 2.5 Placements (CDC), Substitutions, Events, Clubs, Assistant

| Method | Endpoint Path | Handler Function | Auth / Role | Database Model | Frontend Consumer | Status |
|:---:|:---|:---|:---:|:---|:---|:---:|
| `GET` | `/placements/drives` | `get_placement_drives()` | All Roles | `PlacementDrive` | `placements.ts` | 🟢 Working |
| `POST` | `/placements/drives` | `create_placement_drive()` | `ADMIN` | `PlacementDrive` | `placements.ts` | 🟢 Working |
| `GET` | `/substitutions` | `get_substitutions()` | `ADMIN`, `FACULTY` | `FacultySubstitution` | `substitutions.ts` | 🟢 Working |
| `POST` | `/substitutions` | `create_substitution()` | `FACULTY` | `FacultySubstitution` | `substitutions.ts` | 🟢 Working |
| `PUT` | `/substitutions/{id}/approve` | `approve_substitution()` | `ADMIN` | `FacultySubstitution` | `substitutions.ts` | 🟢 Working |
| `GET` | `/events` | `get_events()` | All Roles | `CampusEvent` | `events.ts` | 🟢 Working |
| `POST` | `/events` | `create_event()` | `ADMIN`, `FACULTY` | `CampusEvent` | `events.ts` | 🟢 Working |
| `GET` | `/clubs` | `get_clubs()` | All Roles | `Club` | `clubs.ts` | 🟢 Working |
| `POST` | `/chat/send` | `send_chat_message()` | Authenticated | `ChatConversation`, `ChatMessage` | `CampusAssistantDrawer.tsx` | 🟢 Working (LangGraph fallback) |
| `GET` | `/notifications` | `get_notifications()` | Authenticated | `Notification` | `NotificationContext.tsx` | 🟢 Working |
| `PUT` | `/notifications/{id}/read` | `mark_notification_read()`| Authenticated | `Notification` | `NotificationContext.tsx` | 🟢 Working |

---

## 3. Discrepancies & Alignment Observations

1. **Department Code Key Name:**  
   `/timetable/departments` returns `"department_code": d.department_code`. In `scripts/inspect_preview_entries.py`, the script attempted `x['code']` instead of `x['department_code']`, triggering a `KeyError`. The frontend client (`src/api/timetable.ts`) defines `department_code?: string; code?: string;` and correctly handles both.
2. **Working Days Configuration Gap:**  
   Neither `GenerationScope` nor `/timetable/generate-preview` accepts a `working_days` parameter. All generation defaults strictly to 6 days.
3. **Time Slot Scope Discrepancy:**  
   `backend/services/timetable_input_loader.py` filters `TimeSlot.day.in_(["MON", "TUE", "WED", "THU", "FRI", "SAT"])`. The authoritative workbook inserts full day names (`MONDAY`, `TUESDAY`, etc.). Consequently, the solver only schedules into slots 1–54 (legacy 09:00–17:00 demo slots) instead of slots 55–108 (authoritative 08:30–16:15 period slots).

