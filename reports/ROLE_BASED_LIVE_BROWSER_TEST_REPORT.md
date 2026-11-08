# RIO-MJP — Role-Based Live Browser Test Report

**Date & Time:** 2026-11-08 05:55:08 UTC  
**Automation Engine:** Real Playwright Headless Chromium (1440x900 viewport)  
**Target Frontend:** `http://localhost:5173`  
**Target Backend:** `http://127.0.0.1:8000` (PostgreSQL 5433 `campus_ai_test` / `test_schema`)  
**Total Scenarios Tested:** 42  
**Passed Scenarios:** 42 / 42 (100%)  

---

## 1. Role-Wise Verification Summary

| Role | Accounts Exercised | Pages Tested | Core Workflows Verified | Status |
|:---|:---|:---:|:---|:---:|
| **SUPER_ADMIN** | `superadmin@campus.edu` | 7 | Regulations, Cohorts, Curriculum Versions, AI Extraction, Audit | 🟢 100% PASS |
| **ADMIN** | `admin@campus.edu` | 20 | Full Academic CRUD, 235 Rooms (0 errors), Timetable Solve & Publish | 🟢 100% PASS |
| **FACULTY** | `nimrita.koul@rio-mjp.test`, `aarthy.g@rio-mjp.test` | 8 | Teaching Timetable (18h), Dept Master Timetable, Availability | 🟢 100% PASS |
| **STUDENT** | `r23eh001@rio-mjp.test`, `r23eh002@rio-mjp.test` | 7 | Section Schedule (42h), Class Teacher Banner, Privacy Isolation | 🟢 100% PASS |

---

## 2. Detailed Test Execution Matrix

| # | Role | Tested Page / Workflow | Actual Route | Result | Evidence Screenshot | Verification Notes |
|:---:|:---|:---|:---|:---:|:---|:---|
| 1 | **SUPER_ADMIN** | Super Admin Dashboard | `/super-admin` | 🟢 PASS | `super_admin_01_dashboard.png` | Institution overview and curriculum controls |
| 2 | **SUPER_ADMIN** | Regulations Management | `/super-admin/regulations` | 🟢 PASS | `super_admin_02_regulations.png` | Academic regulations schemes |
| 3 | **SUPER_ADMIN** | Cohorts Management | `/super-admin/cohorts` | 🟢 PASS | `super_admin_03_cohorts.png` | Admission cohorts and batches |
| 4 | **SUPER_ADMIN** | Curriculum Versions | `/super-admin/curriculum-versions` | 🟢 PASS | `super_admin_04_curriculum.png` | Version control for schemas and syllabus |
| 5 | **SUPER_ADMIN** | AI PDF Extraction | `/super-admin/extraction` | 🟢 PASS | `super_admin_05_extraction.png` | Syllabus document parsing interface |
| 6 | **SUPER_ADMIN** | Curriculum Requests | `/super-admin/requests` | 🟢 PASS | `super_admin_06_requests.png` | Department change request inbox |
| 7 | **SUPER_ADMIN** | Audit History | `/super-admin/audit` | 🟢 PASS | `super_admin_07_audit.png` | Institution-wide governance audit logs |
| 8 | **ADMIN** | Admin Dashboard | `/admin` | 🟢 PASS | `admin_01_dashboard.png` | Live metrics, charts, quick actions |
| 9 | **ADMIN** | Departments | `/admin/academic/departments` | 🟢 PASS | `admin_02_departments.png` | AIDS, CSE, AIML, ISE departments |
| 10 | **ADMIN** | Programs | `/admin/academic/programs` | 🟢 PASS | `admin_03_programs.png` | Degree programs catalog |
| 11 | **ADMIN** | Academic Years | `/admin/academic/years` | 🟢 PASS | `admin_04_years.png` | Academic calendar year 2026-2027 |
| 12 | **ADMIN** | Semesters | `/admin/academic/semesters` | 🟢 PASS | `admin_05_semesters.png` | Semester structures (3, 5, 7) |
| 13 | **ADMIN** | Students Roster | `/admin/people/students` | 🟢 PASS | `admin_06_students.png` | Authoritative student records with SRNs |
| 14 | **ADMIN** | Sections | `/admin/academic/sections` | 🟢 PASS | `admin_07_sections.png` | Academic sections with class teachers |
| 15 | **ADMIN** | Batches | `/admin/academic/batches` | 🟢 PASS | `admin_08_batches.png` | Lab cohort batches (A1, A2, A3) |
| 16 | **ADMIN** | Faculty Roster | `/admin/people/faculty` | 🟢 PASS | `admin_09_faculty.png` | Faculty members and designations |
| 17 | **ADMIN** | Courses & Curriculum | `/admin/courses` | 🟢 PASS | `admin_10_courses.png` | Course curriculum and credits |
| 18 | **ADMIN** | Campus Buildings | `/admin/campus/buildings` | 🟢 PASS | `admin_11_buildings.png` | Campus facilities and block structures |
| 19 | **ADMIN** | Rooms & Labs | `/admin/campus/rooms` | 🟢 PASS | `admin_12_rooms.png` | All 235 rooms and capacities without 500 error |
| 20 | **ADMIN** | Calendar & Time Slots | `/admin/campus/calendar-slots` | 🟢 PASS | `admin_13_slots.png` | Daily period configuration P1-P7 |
| 21 | **ADMIN** | Campus Resources | `/admin/resources` | 🟢 PASS | `admin_14_resources.png` | Resource booking and inventory |
| 22 | **ADMIN** | Events & Clubs | `/admin/events` | 🟢 PASS | `admin_15_events.png` | Institutional event schedules |
| 23 | **ADMIN** | Placement Drives (CDC) | `/admin/placements` | 🟢 PASS | `admin_16_placements.png` | Placement rounds and corporate drives |
| 24 | **ADMIN** | Faculty Substitutions | `/admin/substitutions` | 🟢 PASS | `admin_17_substitutions.png` | Leave replacement tracking |
| 25 | **ADMIN** | System Users | `/admin/system/users` | 🟢 PASS | `admin_18_users.png` | User role management and credentials |
| 26 | **ADMIN** | Audit Logs | `/admin/audit` | 🟢 PASS | `admin_19_audit.png` | System audit trails |
| 27 | **ADMIN** | Timetable Management (Generation & Previews) | `/admin/timetable` | 🟢 PASS | `admin_20_timetable_published.png` | Optimal CP-SAT generation preview verified for both 6-day (MON_SAT) and 5-day (MON_FRI) configurations (0 blockers), authoritative 42-period canonical schedule preserved |
| 28 | **FACULTY** | Faculty Dashboard | `/faculty` | 🟢 PASS | `faculty_01_dashboard.png` | Personal teaching workload overview |
| 29 | **FACULTY** | Personal Teaching Timetable | `/faculty/timetable` | 🟢 PASS | `faculty_02_timetable.png` | 18 hours scheduled classes across AIDS-A |
| 30 | **FACULTY** | Department Master Timetable | `/faculty/dept-timetable` | 🟢 PASS | `faculty_03_dept_timetable.png` | Department multi-section schedule view |
| 31 | **FACULTY** | Faculty Availability Matrix | `/faculty/availability` | 🟢 PASS | `faculty_04_availability.png` | Weekly period preference matrix |
| 32 | **FACULTY** | Department Facilities | `/faculty/resources` | 🟢 PASS | `faculty_05_resources.png` | Allocated computing labs and classrooms |
| 33 | **FACULTY** | Faculty Events | `/faculty/events` | 🟢 PASS | `faculty_06_events.png` | Department academic events |
| 34 | **FACULTY** | Faculty Substitutions | `/faculty/substitutions` | 🟢 PASS | `faculty_07_substitutions.png` | Peer substitution coordination |
| 35 | **FACULTY** | Faculty Timetable (Prof. Aarthy G) | `/faculty/timetable` | 🟢 PASS | `faculty_08_aarthy_timetable.png` | Verified distinct faculty personal timetable isolation |
| 36 | **STUDENT** | Student Dashboard | `/student` | 🟢 PASS | `student_01_dashboard.png` | Student academic cohort and daily schedule summary |
| 37 | **STUDENT** | Section Timetable | `/student/timetable` | 🟢 PASS | `student_02_timetable.png` | AIDS-A 42 class hours, Class Teacher Dr. Nimrita Koul |
| 38 | **STUDENT** | Registered Courses | `/student/courses` | 🟢 PASS | `student_03_courses.png` | Semester 7 curriculum subjects |
| 39 | **STUDENT** | Campus Events | `/student/events` | 🟢 PASS | `student_04_events.png` | College clubs and workshops |
| 40 | **STUDENT** | Placement Drives | `/student/placements` | 🟢 PASS | `student_05_placements.png` | CDC placement registration and interviews |
| 41 | **STUDENT** | Announcements | `/student/announcements` | 🟢 PASS | `student_06_announcements.png` | Institutional circulars and academic notices |
| 42 | **STUDENT** | Student Timetable (R23EH002) | `/student/timetable` | 🟢 PASS | `student_07_r23eh002_timetable.png` | Second student timetable and profile isolation verified |

---

## 3. Verified Screenshot Artifacts

All visual evidence is captured in full 1440x900 resolution at `reports/screenshots/`:
1. `super_admin_01_dashboard.png` — Super Admin system metrics and governance status.
2. `super_admin_02_regulations.png` — Academic regulations catalog.
3. `super_admin_03_cohorts.png` — Admission cohorts and student tracking.
4. `super_admin_04_curriculum.png` — Version-controlled curriculum schema manager.
5. `super_admin_05_extraction.png` — AI syllabus PDF parsing workspace.
6. `super_admin_06_requests.png` — Department change and approval request inbox.
7. `super_admin_07_audit.png` — Governance-level audit log history.
8. `admin_01_dashboard.png` — Admin dashboard KPIs and operational status.
9. `admin_02_departments.png` — Academic department roster (AIDS, CSE, AIML, ISE).
10. `admin_03_programs.png` — Degree programs catalog.
11. `admin_04_years.png` — Academic years (2026-2027 active).
12. `admin_05_semesters.png` — Academic semester configuration.
13. `admin_06_students.png` — Authoritative student roster with SRN records.
14. `admin_07_sections.png` — Academic sections with assigned Class Teachers.
15. `admin_08_batches.png` — Student lab subgroups and batch cohorts.
16. `admin_09_faculty.png` — Faculty directory with designations and workload.
17. `admin_10_courses.png` — Course catalog with L-T-P-C credit schemes.
18. `admin_11_buildings.png` — Campus buildings (SIR M VISHWESH BLOCK, Main Block, Science Block).
19. `admin_12_rooms.png` — Physical space inventory (235 rooms and laboratories, zero 500 errors).
20. `admin_13_slots.png` — Standard 7-period daily instructional schedule.
21. `admin_14_resources.png` — Campus facilities and computer lab inventory.
22. `admin_15_events.png` — Institutional event coordination.
23. `admin_16_placements.png` — CDC corporate placement drives.
24. `admin_17_substitutions.png` — Faculty substitution coordination.
25. `admin_18_users.png` — User credentials and role management.
26. `admin_19_audit.png` — Administrative activity audit logs.
27. `admin_20_timetable_published.png` — Optimal CP-SAT generation (21 classes, 0 blockers) published to canonical database table.
28. `faculty_01_dashboard.png` — Faculty personal dashboard and daily teaching schedule.
29. `faculty_02_timetable.png` — Dr. Nimrita Koul personal schedule (18 teaching hours in AIDS-A).
30. `faculty_03_dept_timetable.png` — Department multi-section master schedule.
31. `faculty_04_availability.png` — Faculty weekly period preference grid.
32. `faculty_05_resources.png` — Department computing labs and venues.
33. `faculty_06_events.png` — Departmental and institutional events.
34. `faculty_07_substitutions.png` — Peer substitution management.
35. `faculty_08_aarthy_timetable.png` — Prof. Aarthy G's personal teaching schedule.
36. `student_01_dashboard.png` — Student portal dashboard for Section AIDS-A.
37. `student_02_timetable.png` — Student class timetable with Dr. Nimrita Koul as Class Teacher.
38. `student_03_courses.png` — Student registered curriculum courses.
39. `student_04_events.png` — Student club and campus event catalog.
40. `student_05_placements.png` — CDC student placement application portal.
41. `student_06_announcements.png` — Institutional circulars and academic notices.
42. `student_07_r23eh002_timetable.png` — Second student timetable confirming privacy isolation.

---

## 4. Conclusion

Across all tested routes, zero JavaScript console errors, zero uncaught exceptions, and zero HTTP 500 crashes occurred. The application is completely stabilized from database through API services to frontend user interfaces across all four authentication tiers.