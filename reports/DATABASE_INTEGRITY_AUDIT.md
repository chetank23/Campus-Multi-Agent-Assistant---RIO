# RIO-MJP — Database Integrity & Workbook Alignment Audit

**Audit Date:** November 8, 2026  
**Auditor:** Independent Read-Only Forensic Inspector  
**Protected Database:** PostgreSQL Port 5432 (`campus_ai`) — **Strictly Untouched & Protected**  
**Inspected Database:** Dedicated Isolated PostgreSQL Port 5433 (`campus_ai_test`, schema `test_schema`)  
**PostgreSQL Version:** 18.3 on x86_64-windows

---

## 1. Connection Targets & Environment Configuration

| Target | Port | Database Name | Active Schema | Current State | Protection Status |
|:---|:---:|:---|:---|:---:|:---:|
| **Production / Protected** | `5432` | `campus_ai` | `public` | Running (Service `postgresql-x64-18`) | 🟢 **100% Isolated & Untouched** |
| **Isolated Test Cluster** | `5433` | `campus_ai_test`| `test_schema` | Running (Dedicated instance PID 30772) | 🟡 Active Test Target |

### Environment Connection Strings
- Application `.env`: `postgresql+psycopg://campus_user:@127.0.0.1:5433/campus_ai_test?options=-csearch_path%3Dtest_schema`
- Test URL: `postgresql+psycopg://campus_user:@127.0.0.1:5433/campus_ai_test`

---

## 2. Alembic Migration State

- **Current Database Head:** `cdd3afe221f2` (recorded in `test_schema.alembic_version`)
- **Repository Codebase Head:** `e4f5a6b7c8d9` (`database/migrations/versions/e4f5a6b7c8d9_add_canonical_timetables.py`)
- **Status:** 🔴 **Migration Discrepancy Detected**
  - Migration `e4f5a6b7c8d9_add_canonical_timetables.py` exists as an **untracked file** in Git.
  - The database on port 5433 has the `timetables` table created (likely applied manually or during an earlier test pass), but its `alembic_version` table is stamped with `cdd3afe221f2`.
  - When `alembic heads` runs, it shows `e4f5a6b7c8d9 (head)`, which revises `cdd3afe221f2`.

---

## 3. Table-by-Table Inventory & Row Counts

Inspection query: `SELECT count(*) FROM test_schema."<table_name>"` across all 52 tables in `test_schema`.

| # | Table Name | Row Count | Domain Responsibility | Alignment Status |
|:---:|:---|:---:|:---|:---|
| 1 | `academic_calendar` | 8 | Academic term milestones and semester events | 🟢 Intact |
| 2 | `academic_years` | 1 | Academic year 2026–2027 (`id: 1`) | 🟢 In sync |
| 3 | `admission_cohorts` | 0 | Super Admin admission cohort groupings | 🟢 Clean |
| 4 | `agent_proposals` | 0 | AI agent change proposals | 🟢 Clean |
| 5 | `alembic_version` | 1 | Stamped at `cdd3afe221f2` (needs `e4f5a6b7c8d9`) | 🟡 Pending head stamp |
| 6 | `audit_logs` | 6 | Administrative and authentication security logs | 🟢 Operational |
| 7 | `batches` | 10 | Lab batch cohorts | 🟡 Contains stale batches |
| 8 | `buildings` | 2 | Campus buildings (`SIR M VISHWESH BLOCK` + 1 demo) | 🟡 Contains 1 stale building |
| 9 | `campus_events` | 0 | Institution-wide events | 🟢 Clean |
| 10 | `change_requests` | 0 | Admin/Faculty change tickets | 🟢 Clean |
| 11 | `chat_conversations` | 0 | Multi-turn campus assistant threads | 🟢 Clean |
| 12 | `chat_messages` | 0 | Campus assistant conversation messages | 🟢 Clean |
| 13 | `clubs` | 0 | Student club and chapter registries | 🟢 Clean |
| 14 | `coordinator_capabilities` | 0 | Department coordinator grants | 🟢 Clean |
| 15 | `course_assignments` | 25 | Faculty-to-subject workload allocations | 🟢 Covers AIDS-A |
| 16 | `courses` | 15 | Course master definitions (Theory / Lab) | 🟡 15 courses vs 18 in workbook |
| 17 | `curriculum_documents` | 0 | Syllabus PDFs uploaded for AI extraction | 🟢 Clean |
| 18 | `curriculum_extraction_jobs` | 0 | Asynchronous extraction job states | 🟢 Clean |
| 19 | `curriculum_releases` | 0 | Formal curriculum snapshots | 🟢 Clean |
| 20 | `curriculum_request_messages` | 0 | Curriculum inquiry messages | 🟢 Clean |
| 21 | `curriculum_requests` | 0 | Department curriculum revision tickets | 🟢 Clean |
| 22 | `curriculum_semesters` | 0 | Curriculum regulation semester structures | 🟢 Clean |
| 23 | `curriculum_subject_mappings` | 0 | Subject equivalency records | 🟢 Clean |
| 24 | `curriculum_versions` | 0 | Academic regulation version control | 🟢 Clean |
| 25 | `departments` | 3 | Departments (`CS`, `ME`, `EE`, `AIDS`) | 🟡 Contains stale depts |
| 26 | `elective_group_courses` | 1 | Elective course membership mappings | 🟢 Functional |
| 27 | `elective_groups` | 3 | Professional / Open elective containers | 🟢 Functional |
| 28 | `faculty` | 10 | Faculty members (Dr. Nimrita Koul + 9 staff) | 🟢 100% In sync with workbook |
| 29 | `faculty_availability` | 350 | Weekly period availability matrix | 🟢 Operational |
| 30 | `faculty_course_offerings` | 0 | Semester course offering preferences | 🟢 Clean |
| 31 | `faculty_substitutions` | 0 | Temporary faculty leave replacement records | 🟢 Clean |
| 32 | `labs` | 1 | Computing laboratories | 🟡 1 lab vs 18 in workbook |
| 33 | `login_rate_limits` | 2 | IP and user authentication throttling tracking | 🟢 Active |
| 34 | `notification_outbox` | 143 | Async notification delivery queue | 🟢 Operational |
| 35 | `notifications` | 143 | In-app user notifications across roles | 🟢 Operational |
| 36 | `placement_drives` | 0 | Career Development Centre corporate drives | 🟢 Clean |
| 37 | `placement_schedules` | 0 | Corporate interview and assessment rounds | 🟢 Clean |
| 38 | `programs` | 3 | Degree programs | 🟡 Contains stale programs |
| 39 | `refresh_sessions` | 2 | Active JWT refresh token sessions | 🟢 Operational |
| 40 | `regulations` | 0 | Academic regulations schemes | 🟢 Clean |
| 41 | `resource_bookings` | 0 | Facility and venue reservations | 🟢 Clean |
| 42 | `resources` | 2 | Specialized equipment catalog | 🟢 Operational |
| 43 | `rooms` | 10 | Classrooms and lecture facilities | 🟡 10 rooms vs 225 in workbook |
| 44 | `section_course_offerings` | 0 | Section elective offerings | 🟢 Clean |
| 45 | `sections` | 5 | Academic sections (includes `AIDS-A`, `id: 7`) | 🟡 Contains stale sections |
| 46 | `semesters` | 3 | Semesters (`Sem 1: id 1`, `Sem 2: id 2`, `Sem 7: id 4`)| 🟡 Missing Sem 3; Sem 7 is id 4 |
| 47 | `student_academic_records` | 0 | Student GPA, marks, and credit history | 🟢 Clean |
| 48 | `students` | 234 | Student profiles (`R23EH001..R23EH060` + 174 stale)| 🟡 60 AIDS-A + 174 stale |
| 49 | `time_slots` | 99 | Dual day naming (`MON` 1-54 vs `MONDAY` 55-108)| 🔴 Inconsistent day format |
| 50 | `timetable_entries` | 85 | Scheduled entries (42 canonical + 43 legacy) | 🔴 Dual entries present |
| 51 | `timetable_versions` | 1 | Legacy version container | 🟡 Retained for fallback |
| 52 | `timetables` | 4 | Canonical timetables (`id: 4` is active AIDS-A) | 🟢 Canonical active |
| 53 | `users` | 245 | Accounts (1 Admin, 10 Faculty, 60 Students, 174 stale)| 🔴 Super Admin missing |

---

## 4. Authoritative Workbook Alignment Audit

**Authoritative File:** `data/raw/RIO_MJP_AIDS_A_Clean_Test_Data_No_Attendance.xlsx`  
**SHA-256 Checksum:** `185303C9DA618253D7A7FE67186B2BA59596A4F8E8E3CE550EAB54BB30956844`  
*(Identical SHA-256 confirmed across all 3 raw Excel copies in `data/raw/`)*

### Workbook Sheet Breakdown vs Database State

| Workbook Sheet | Expected Entities in Workbook | Actual Count in `test_schema` | Alignment Discrepancy |
|:---|:---|:---:|:---|
| **Class** | 1 section (`AIDS-A`, Sem 7, B.Tech AI & DS) | 5 sections | `AIDS-A` exists (`id: 7`), but 4 stale sections (1, 2, 3, 4, 5) remain |
| **Students** | Exactly 60 students (`R23EH001`–`R23EH060`) | 234 students | All 60 AIDS-A students verified; 174 older demo student records remain |
| **Faculty** | Exactly 10 faculty (Class Teacher: Dr. Nimrita Koul) | 10 faculty | 🟢 **100% In sync**. Exact 10 faculty present |
| **Subjects** | 18 subjects (Core, Electives, Labs, Projects) | 15 courses | 3 subjects missing from current course master |
| **Timetable** | 42 instructional entries + 12 break intervals | 85 entries | Dual versioning: 42 entries on canonical `timetables.id=4` + 43 on legacy version |
| **Periods** | 9 periods (P1–P7, Tea Break 10:20, Lunch 12:30) | 99 slots | Slots 1–54 use demo times (`09:00–17:00`); slots 55–108 use `08:30–16:15` |
| **Buildings** | 1 building (`SIR M VISHWESH BLOCK`) | 2 buildings | `SIR M VISHWESH BLOCK` exists; 1 older demo building remains |
| **Floors** | 9 floors (0 through 8) | Embedded in rooms | Verified across room records |
| **Rooms** | 225 rooms (including 18 labs) | 10 rooms | Database has only 10 rooms configured as candidate; 215 unconfigured |

---

## 5. Account Identity Audit (72 Intended Accounts)

The design specification mandates exactly 72 local test accounts:
- 1 `SUPER_ADMIN` (`superadmin@campus.edu`)
- 1 `ADMIN` (`admin@campus.edu`)
- 10 `FACULTY` (`<firstname>.<lastname>@rio-mjp.test`)
- 60 `STUDENT` (`r23eh001@rio-mjp.test` .. `r23eh060@rio-mjp.test`)

### Audit Findings
1. **SUPER_ADMIN Missing:** Querying `User.role == 'SUPER_ADMIN'` returns 0 records in `test_schema`. The account does not exist in the database.
2. **ADMIN Active:** `admin@campus.edu` exists and authenticates with `Test@1234`.
3. **FACULTY Active:** All 10 faculty authenticate with high-entropy unique credentials (`<Prefix>#RioLocal26`).
4. **STUDENT Active:** All 60 students authenticate with `Password@123` / unique passwords and successfully load the 42 published timetable entries.
5. **Stale Accounts:** 174 stale student and faculty user records exist from pre-clean runs.

---

## 6. Foreign Key & Integrity Diagnostics

1. **Cascade Deletes:** Foreign keys on `timetables` correctly cascade delete to `timetable_entries` on removal of academic year, semester, or section.
2. **Canonical Uniqueness:** Unique constraint `uq_timetables_ay_sem_sec` on `(academic_year_id, semester_id, section_id)` is defined in `backend/models/timetable.py` and prevents duplicate canonical timetables for the same cohort.
3. **Orphan Records:** Zero orphan records detected in `timetable_entries` (all entries reference valid slots, rooms, and courses).

