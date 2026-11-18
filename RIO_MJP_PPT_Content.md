# RIO-MJP: Final Capstone Defense Presentation Deck
## Multi-Agent Campus Assistant with Intelligent Timetable Generation Engine

**Presentation Duration:** 20–25 Minutes  
**Audience:** Academic Review Board, Project Evaluators, Faculty Mentors & University Leadership  
**Institutional Scope:** REVA University — Center for Intelligent Enterprise Systems  

---

### Slide 1: Title & Project Identity
- **Project Title:** RIO-MJP: Multi-Agent Campus Assistant with Intelligent Timetable Generation Engine
- **Short Name:** RIO-MJP (REVA Intelligent Operations — Multi-Agent Journey Platform)
- **Domain:** Artificial Intelligence, Constraint Programming & Autonomous Multi-Agent Systems
- **Center:** Center for Intelligent Enterprise Systems
- **Faculty Mentor:** Srinivas P | **Center Lead:** Karthik Kashyap
- **Student Team:** [Insert Team Member Names & SRNs]

---

### Slide 2: Problem Statement & Campus Challenges
- **Fragmented Campus Operations:** Campus administration operates through disconnected silos (standalone portals, manual Excel sheets, notice boards).
- **The Timetabling Bottleneck:** Constructing conflict-free college schedules is an NP-hard combinatorial problem (Faculty $\times$ Rooms $\times$ Student Cohorts $\times$ Time Intervals $\times$ Electives).
- **Operational Drag:** Routine student and faculty queries (exam schedules, room locations, CDC placement eligibility, substitute teachers) consume thousands of administrative hours each semester.
- **Human Error & Clashes:** Manual scheduling results in double-booked laboratories, uneven faculty workloads, and fragmented student timetables with long gaps.

---

### Slide 3: Conventional Systems vs. RIO-MJP
| Conventional ERP / College Chatbot | RIO-MJP Intelligent Campus Platform |
|:---|:---|
| Static, hardcoded database forms | Adaptive, role-aware reactive web applications (React 19 + TypeScript) |
| Manual trial-and-error timetable generation | Provably optimal mathematical CP-SAT constraint solver (Google OR-Tools) |
| Hallucinating, generic AI chatbots | Strictly grounded Multi-Agent AI (LangGraph + 18+ typed database tools) |
| Disconnected third-party booking tools | Real-time conflict-aware facility and laboratory resource allocation |
| Ad-hoc, unrecorded faculty leave | Deterministic qualification gating with student medical privacy barriers |

---

### Slide 4: Proposed Solution & Core Innovation
- **Dual-Path Architecture:**
  1. *Deterministic High-Performance Path:* FastAPI microsecond REST APIs, PostgreSQL source of truth, and Google OR-Tools CP-SAT constraint optimization.
  2. *Conversational Multi-Agent Path:* LangGraph StateGraph orchestrating Supervisor, Query, Scheduling, Resource, and Composite Coordinator agents.
- **Absolute Grounding Principle:** The LLM interprets natural language and explains outcomes; it **never** invents data or directly mutates database records without typed tools and human approval.
- **Canonical Preview-Publish Lifecycle:** Administrators can simulate and inspect candidate schedules in-memory with zero database pollution before one-click atomic publication.

---

### Slide 5: System Architecture & Data Flow
```
[React 19 SPA] ---> [FastAPI Gateway (OAuth2 + RBAC)]
                          |
         +----------------+----------------+
         |                                 |
         v                                 v
[LangGraph Multi-Agent]        [OR-Tools CP-SAT Optimizer]
  - Supervisor Node              - 7 Hard Constraints
  - Query / Sched / Res Nodes    - Multi-Objective Soft Weights
  - 18+ Typed Database Tools     - Validator & Quality Scorer
         |                                 |
         +----------------+----------------+
                          |
                          v
         [PostgreSQL 16/18 Relational Core]
               (52 Domain Tables)
```

---

### Slide 6: Comprehensive Technology Stack
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS, TanStack React Query, Lucide Icons, jsPDF.
- **Backend Framework:** FastAPI 0.110.0, Uvicorn ASGI Server, Python 3.13.
- **Database & Migration:** PostgreSQL 16/18, SQLAlchemy 2.0 ORM, psycopg v3 driver, Alembic.
- **AI & Multi-Agent:** LangGraph StateGraph, Anthropic Claude 3.5 Sonnet, 18+ typed tools.
- **Optimization Core:** Google OR-Tools CP-SAT (Constraint Programming - Satisfiability).
- **Quality & Testing:** Pytest, Playwright (Headless Chromium), Oxlint, Pyright.

---

### Slide 7: Relational Database Design (52+ Tables)
- **Identity & Security (3 tables):** `users`, `refresh_sessions`, `login_rate_limits`.
- **Academic Hierarchy (8 tables):** `departments`, `programs`, `academic_years`, `semesters`, `sections`, `batches`, `students`, `faculty`.
- **Space-Time & Infrastructure (6 tables):** `buildings`, `rooms` (235 items), `labs`, `time_slots`, `faculty_availability`, `academic_calendar`.
- **Curriculum & Workload (4 tables):** `courses`, `course_assignments`, `elective_groups`, `elective_group_courses`.
- **Timetables (3 tables):** `timetables` (Canonical header), `timetable_entries` (42 periods), `timetable_versions`.
- **Resources, Events, Placements & Substitutions (10 tables):** Facilities, bookings, clubs, events, CDC drives, faculty leave coverage.
- **Super Admin Governance (12 tables):** Regulations, cohorts, curriculum versions, syllabus PDF extraction.
- **Workflow & Audit (6 tables):** Change requests, proposals, notifications, audit logs, chat messages.

---

### Slide 8: Timetable Optimization Engine (Google OR-Tools CP-SAT)
- **Mathematical Modeling:** Boolean decision variables $x_{a, h, r, t} \in \{0, 1\}$ representing assignment $a$, hour type $h$, room $r$, and time slot $t$.
- **7 Hard Constraints (Zero-Tolerance Feasibility):**
  1. *Curriculum Hours:* Exact lecture, tutorial, and practical period fulfillment.
  2. *Faculty Conflict:* $\le 1$ class per faculty member per slot.
  3. *Section Conflict:* $\le 1$ class per student section per slot.
  4. *Batch Conflict:* $\le 1$ lab session per batch per slot.
  5. *Room Double-Booking:* $\le 1$ class per room per slot.
  6. *Temporal Interval Non-Overlap:* Eliminates clashes across multi-period intervals.
  7. *Calendar Exclusions:* Strict blackout for holidays, exam slots, and lunch breaks.

---

### Slide 9: Multi-Objective Soft Weights & Optimization Profiles
- **Soft Objective Criteria:**
  - Faculty Gap Minimization (Weight = 10)
  - Student Idle Gap Minimization (Weight = 10)
  - Faculty Preferred Slot Maximization (Weight = 5)
  - Unnecessary Room Hopping Reduction (Weight = 5)
  - Late Lab Avoidance after 14:00 (Weight = 20)
  - Daily Workload Variance Balancing (Weight = 15)
  - Minimal Perturbation Rescheduling Penalties ($P_{slot}=500, P_{room}=200$)
- **4 Optimization Profiles:**
  - `BALANCED`: Standard institutional trade-off.
  - `FACULTY_COMFORT`: Maximizes teacher satisfaction and minimizes commute breaks.
  - `ROOM_EFFICIENCY`: Maximizes room utilization and minimizes student travel.
  - `LAB_PREFERENCE`: Schedules practical labs in optimal morning blocks.

---

### Slide 10: Independent Deterministic Validator & Scorer
- **Double-Check Safeguard:** Independent Python validator evaluates both solver outputs and manual edits.
- **Severity Classification:**
  - **BLOCKER:** Hard violation (e.g. room double-booking) $\rightarrow$ Blocks publication immediately.
  - **WARNING:** Soft advisory (e.g. room capacity near threshold).
  - **INFO:** Informational match (e.g. preferred slot assigned).
- **Deterministic Quality Scoring:**
  - Overall score is normalized $[0, 100]$.
  - $\text{Score} = 0.0$ if any Blocker exists.
  - Feasible schedules receive a calculated score based on gap, room, and preference adherence.

---

### Slide 11: Multi-Agent Conversational AI Architecture
- **LangGraph StateGraph Engine:** Cyclic, stateful agent workflow managing request context.
- **Supervisor Agent:** High-accuracy intent detection, scope verification, and RBAC authorization guard.
- **Specialist Subagents:**
  - *Query Agent:* Reads verified database records for student profiles, faculty schedules, and exam calendars.
  - *Scheduling Agent:* Analyzes timetable readiness, diagnoses solver infeasibility, and explains bottlenecks.
  - *Resource Agent:* Discovers available rooms, evaluates projector requirements, and prepares booking proposals.
  - *Composite Coordinator:* Simultaneously coordinates venue booking and faculty supervision.
- **Two-Phase Human-in-the-Loop:** Actions generating state changes (booking rooms, regenerating timetables) produce cryptographic proposal tokens (`op_prop_*`, `res_prop_*`) requiring explicit confirmation.

---

### Slide 12: Role-Based Portals & User Experience
1. **Super Admin Governance Portal:** Institution-wide academic regulations, version-controlled curriculum releases, syllabus PDF extraction.
2. **Admin Operational Portal:** Campus infrastructure, 235 rooms catalog, user provisioning, CP-SAT timetable generation, preview & publish.
3. **Faculty Portal:** Personal teaching schedule (18 hours for AIDS-A), department master timetable, weekly availability matrix, peer substitution requests.
4. **Student Portal:** Personal section timetable (42 hours), Class Teacher banner, enrolled courses, CDC placement drives, club events.

---

### Slide 13: Specialized Campus Engines
- **Faculty Substitution Engine:**
  - Hard qualification gating: substitute must have verified teaching qualification for the specific course.
  - Workload headroom checks prevent violating weekly teaching limits.
  - Master timetable immutability: temporary coverages layer dynamically over date-specific queries.
  - Student privacy barrier: medical/personal absence reasons are strictly masked.
- **CDC Placement Management Engine:**
  - Automated eligibility checking: filters student applications based on CGPA and active backlogs.
  - Multi-round recruitment scheduling (Online Tests, Tech Interviews, HR Rounds).

---

### Slide 14: Quality Assurance & Test Verification Rigor
- **GitHub Actions CI Pipeline:**
  - **479 Passed, 0 Failed, 0 Errors** in 6m 37s (Run ID `42456104581`).
  - Python 3.13 compile check: 100% clean across all modules.
- **Static Code Analysis:**
  - Pyright Type Safety: **0 errors, 0 warnings, 0 info**.
  - IDE Pyrefly Diagnostics: **0 diagnostics** (all 31 resolved without type ignores).
  - Oxlint Frontend Linting: **0 errors** across 131 files.
- **Playwright Live Browser Test Suite:**
  - **42 / 42 Scenarios Passed (100%)** on live running instances.
  - 42 authentic PNG screenshots captured in `reports/screenshots/`.

---

### Slide 15: Authoritative Benchmark Dataset (AIDS-A)
- Grounded in official REVA University School of CSE & AIDS academic data:
  - **1 Department:** AI & DS | **1 Program:** B.Tech AI & DS
  - **1 Academic Year:** 2026–2027 | **1 Semester:** Semester VII
  - **1 Active Section:** AIDS-A | **3 Batches:** A1, A2, A3
  - **60 Matched Students:** `R23EH001` through `R23EH060` with individual accounts
  - **10 Faculty Members:** Led by Dr. Nimrita Koul (Associate Professor & Class Teacher)
  - **18 Courses:** Comprehensive L-T-P-C theory, practical labs, and electives
  - **235 Physical Rooms & Labs:** 9 floors of SIR M VISHWESH BLOCK
  - **42 Instructional Periods:** Optimal CP-SAT solve in **0.40 seconds**.

---

### Slide 16: Security, Compliance & Governance
- **Zero Hardcoded Secrets:** Strictly configured via `.env` with separate application and isolated test databases.
- **Bcrypt Password Security:** High-entropy salted hashes; credentials never logged.
- **SQL Injection Prevention:** 100% parameterized queries via SQLAlchemy 2.0 ORM.
- **Access Control (RBAC):** Token-based dependency injection on every protected endpoint.
- **Tamper-Evident Audit Logs:** All critical mutations recorded with IP address, timestamp, and actor ID.

---

### Slide 17: Project Limitations & Future Scope
- **Current Limitations:**
  - Timetable updates currently utilize polling rather than real-time WebSocket push notifications.
  - Student elective selection requires administrative entry rather than open student bidding.
- **Future Enhancements:**
  - Native mobile application for Android and iOS using React Native.
  - Real-time WebSocket event bus for live schedule disruption broadcasts.
  - Voice-driven conversational assistant interface for campus kiosks.
  - Multi-campus horizontal scaling with distributed PostgreSQL partitioning.

---

### Slide 18: Conclusion & Key Contributions
1. **Academic Automation:** Transformed timetable creation from a multi-day manual ordeal into an automated 0.4-second mathematical optimization.
2. **Deterministic Reliability:** Proved that LLMs can be safely integrated into mission-critical campus ERPs by pairing conversational agents with strict database tools and independent validators.
3. **Enterprise Architecture:** Delivered a production-ready, type-safe full-stack system with 253 API operations, 52 relational tables, and 479 passing automated tests.
4. **Real Campus Impact:** Fully validated against authentic REVA University curriculum data, ready for institutional deployment.

---

### Slide 19: Q&A / Demonstration
**Thank You!**  
*The RIO-MJP demonstration is now open for questions and live system evaluation.*
