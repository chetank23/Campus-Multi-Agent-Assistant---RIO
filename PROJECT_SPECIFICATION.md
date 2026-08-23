# Multi-Agent Campus Assistant & Automated Timetable Engine
## Complete End-to-End Capstone System Blueprint

**Innovation Center:** Center for Intelligent Enterprise Systems
**Faculty Mentor:** Srinivas P
**Center Lead:** Karthik Kashyap

> **Revision note (v2):** Roles simplified from five (Student/Faculty/HOD/Coordinator/Admin) to
> three (Student/Faculty/Admin). All multi-level departmental review chains (HOD review,
> Coordinator review) are removed — **Admin is the sole authority for generating, reviewing,
> validating, finalizing, and publishing timetables.** Full technical depth is retained
> everywhere else: complete DB schema, all four AI agents, OR-Tools optimizer, validator/scorer,
> resource allocation, notifications, audit logging, RAG, evaluation, and the full roadmap.
> `departments.hod_id` is removed (no HOD role to reference), and `timetable_version`/`timetable`
> are renamed to `timetable_versions`/`timetable_entries` for naming consistency. A student-facing
> **class status** concept (UPCOMING/ONGOING/COMPLETED/CANCELLED/RESCHEDULED) is added.

---

## TABLE OF CONTENTS

1. Problem, Objective, Research Outcome
2. System Architecture
3. Technology Stack
4. Repository Structure
5. Database Design (Full Schema + DDL)
6. Authentication & Authorization
7. Backend API Specification
8. AI Agent Architecture (LangGraph)
9. Timetable Optimization Engine (OR-Tools)
10. Deterministic Validator & Scorer
11. Resource Allocation Engine
12. Workflow State Machines
13. Notification & Audit System
14. Frontend Architecture
15. Optional RAG Module
16. Testing Strategy
17. Evaluation & Research Metrics
18. DevOps, Deployment & Observability
19. Security Checklist
20. Development Roadmap (Full, Phased)
21. Capstone Defense / Demo Script
22. Final Deliverables Checklist

---

# 1. PROBLEM, OBJECTIVE, RESEARCH OUTCOME

**Problem statement:** Campus operations — answering student/staff queries, scheduling classes, and allocating shared resources — run through disconnected manual processes, producing duplicated effort, scheduling conflicts, and slow responses. Timetable creation is a constraint-satisfaction problem (faculty availability × room capacity × course requirements × electives) that does not scale to manual solving without conflicts.

**Objective:** An autonomous multi-agent campus assistant that (a) resolves routine campus queries in natural language and (b) automatically produces conflict-free timetables and resource allocations, coordinated across five human roles: Student, Faculty, HOD, Timetable Coordinator, Admin.

**Required research outcome:** A working multi-agent assistant, a timetable generator producing provably conflict-free schedules, a resource allocation module, and evaluation results on **scheduling accuracy** and **query resolution rate**.

**Non-negotiable architectural principle**, carried through every section below:

```
LLM          → language understanding, intent detection, tool selection, response generation
PostgreSQL   → source of truth for all campus data
OR-Tools     → timetable generation (constraint satisfaction + optimization)
Validators   → deterministic, LLM-independent conflict/business-rule checking
Humans       → HOD review → Coordinator review → Admin approval/publish
```

The LLM never invents or directly writes a timetable slot. It calls tools; tools touch the database and solver; humans approve the result.

---

# 2. SYSTEM ARCHITECTURE

## 2.1 High-level component diagram

```
                              USERS
        Student   Faculty   HOD   Coordinator   Admin
                              │
                    React Web Application
                              │
                          FastAPI
                    (Auth · RBAC · Services)
                              │
              ┌───────────────┼────────────────┐
              │               │                │
        LangGraph        OR-Tools          PostgreSQL
      (Agent Runtime)     Optimizer         (Source of Truth)
              │               │                │
      ┌───────┴───────┐  Validator             │
  Supervisor        Tool Layer  │               │
      │               │      Scorer            │
  ┌───┼───┐           │        │                │
 Query Sched Resource─┴────────┴────────────────┘
 Agent Agent  Agent
```

## 2.2 Request-flow architecture (every request, regardless of type)

```
Client → JWT validated → role + department resolved →
  ├─ Direct CRUD request  → FastAPI route → service layer → SQLAlchemy → Postgres
  ├─ Chat / NL request    → Supervisor Agent → intent → authorized agent → tool → Postgres/Optimizer
  └─ Timetable generation → Scheduling Service → OR-Tools → Validator → Scorer → Draft → Postgres
```

## 2.3 Design rules (apply everywhere below)

1. Postgres is the only source of truth — no campus fact is ever answered from LLM memory.
2. OR-Tools produces the schedule; the LLM only parameterizes the request.
3. Every generated schedule passes through an independent Python validator before it is shown as a "candidate." A validator failure blocks the draft, full stop.
4. Every protected endpoint re-checks role + department server-side; the frontend's UI restrictions are cosmetic only.
5. Every state-changing action (approve, publish, reject, edit slot, book resource) writes an audit log row in the same transaction.
6. Long-running work (timetable generation) runs as a background job, not inline in a request/response cycle — see §18.4.

---

# 3. TECHNOLOGY STACK

```
Frontend      React 18 + TypeScript + Tailwind CSS + React Router + Axios + React Query
Backend       Python 3.11 + FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic (migrations)
Auth          JWT (access + refresh) + passlib/bcrypt
Database      PostgreSQL 16
Async jobs    Celery + Redis (timetable generation, notifications)
AI            LangGraph + Anthropic Claude API + structured tool calling
Optimization  Google OR-Tools (CP-SAT solver)
Testing       Pytest + pytest-asyncio, Postman/Newman for API contract tests
DevOps        Docker + Docker Compose, GitHub Actions CI
Observability Structured logging (structlog), request tracing IDs
```

---

# 4. REPOSITORY STRUCTURE

```
campus-ai-system/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py                # get_current_user, require_role, require_department
│   ├── routes/
│   │   ├── auth.py  students.py  faculty.py  hod.py  departments.py
│   │   ├── courses.py  rooms.py  labs.py  timetable.py  resources.py
│   │   ├── chat.py  admin.py  change_requests.py  notifications.py  audit.py
│   ├── models/                        # SQLAlchemy ORM models, one file per domain
│   ├── schemas/                       # Pydantic request/response schemas
│   ├── services/                      # business logic, orchestrates models + optimizer
│   ├── middleware/                    # auth, RBAC, request logging
│   ├── celery_app.py
│   └── utils/
│
├── agents/
│   ├── supervisor/agent.py
│   ├── query_agent/agent.py
│   ├── scheduling_agent/agent.py
│   ├── resource_agent/agent.py
│   ├── state/state.py                 # shared LangGraph state schema
│   └── tools/
│       ├── student_tools.py  faculty_tools.py  room_tools.py
│       ├── timetable_tools.py  resource_tools.py
│
├── optimizer/
│   ├── timetable_solver.py            # CP-SAT model construction + solve
│   ├── constraints.py                 # hard + soft constraint builders
│   ├── objectives.py                  # weighted objective function
│   ├── validator.py                   # independent post-solve validation
│   └── scorer.py                      # score calculation from validator output
│
├── database/
│   ├── schema.sql
│   ├── seed.sql
│   ├── migrations/                    # Alembic versions
│   └── seeds/                         # Dataset A/B/C generators
│
├── data/{raw,processed,sample}/
│
├── frontend/
│   ├── src/
│   │   ├── pages/{student,faculty,hod,coordinator,admin}/
│   │   ├── components/                # TimetableGrid, ChatWidget, ApprovalPanel, etc.
│   │   ├── layouts/  services/  hooks/  contexts/  routes/
│   └── package.json
│
├── tests/{api,agents,optimizer,database,integration}/
├── docs/{architecture,database,api,research,workflows}/
├── scripts/{seed_database.py, generate_sample_data.py, reset_database.py}
├── docker-compose.yml
├── .github/workflows/ci.yml
├── requirements.txt
├── .env.example
└── README.md
```

---

# 5. DATABASE DESIGN (FULL SCHEMA)

PostgreSQL is the sole source of truth. Every entity below is implemented — nothing deferred for a capstone build.

## 5.1 Entity relationship overview

```
Department ──< Programs ──< Semesters ──< Sections ──< Batches
Department ──< Faculty ──< Faculty_Availability
Department ──< Courses ──< Elective_Groups ──< Elective_Group_Courses
Section ──< Course_Assignments >── Faculty
Building ──< Rooms ──< Labs
Timetable_Version ──< Timetable ── (Section, Course, Faculty, Room, Slot)
Resources ──< Resource_Bookings
Users ──< Change_Requests, Notifications, Audit_Logs
```

## 5.2 Core DDL

```sql
-- USERS & IDENTITY -----------------------------------------------------
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(30) NOT NULL CHECK (role IN
        ('STUDENT','FACULTY','ADMIN')),
    department_id INTEGER REFERENCES departments(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now()
);

-- ACADEMIC STRUCTURE ----------------------------------------------------
CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    department_code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL
    -- no hod_id: HOD role removed, department leadership is not modeled as a user FK
);

CREATE TABLE programs (
    id SERIAL PRIMARY KEY,
    department_id INTEGER REFERENCES departments(id),
    program_name VARCHAR(150),
    degree VARCHAR(50),
    duration INTEGER
);

CREATE TABLE academic_years (
    id SERIAL PRIMARY KEY,
    name VARCHAR(20),
    start_date DATE,
    end_date DATE
);

CREATE TABLE semesters (
    id SERIAL PRIMARY KEY,
    academic_year_id INTEGER REFERENCES academic_years(id),
    semester_number INTEGER,
    start_date DATE,
    end_date DATE
);

CREATE TABLE sections (
    id SERIAL PRIMARY KEY,
    department_id INTEGER REFERENCES departments(id),
    program_id INTEGER REFERENCES programs(id),
    semester_id INTEGER REFERENCES semesters(id),
    section_name VARCHAR(10),
    student_count INTEGER
);

CREATE TABLE batches (
    id SERIAL PRIMARY KEY,
    section_id INTEGER REFERENCES sections(id),
    batch_name VARCHAR(10),
    student_count INTEGER
);

CREATE TABLE students (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    student_id VARCHAR(30) UNIQUE,
    department_id INTEGER REFERENCES departments(id),
    program_id INTEGER REFERENCES programs(id),
    semester_id INTEGER REFERENCES semesters(id),
    section_id INTEGER REFERENCES sections(id),
    batch_id INTEGER REFERENCES batches(id)
);

CREATE TABLE faculty (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    faculty_id VARCHAR(30) UNIQUE,
    department_id INTEGER REFERENCES departments(id),
    designation VARCHAR(50),
    max_weekly_load INTEGER DEFAULT 16
);

-- COURSES & ASSIGNMENTS --------------------------------------------------
CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    course_code VARCHAR(20) UNIQUE,
    course_name VARCHAR(150),
    department_id INTEGER REFERENCES departments(id),
    course_type VARCHAR(20) CHECK (course_type IN
        ('THEORY','LAB','TUTORIAL','PROJECT','ELECTIVE')),
    credits INTEGER,
    lecture_hours INTEGER,
    tutorial_hours INTEGER,
    practical_hours INTEGER,
    requires_lab BOOLEAN DEFAULT FALSE
);

CREATE TABLE course_assignments (
    id SERIAL PRIMARY KEY,
    course_id INTEGER REFERENCES courses(id),
    faculty_id INTEGER REFERENCES faculty(id),
    section_id INTEGER REFERENCES sections(id),
    batch_id INTEGER REFERENCES batches(id)
);

CREATE TABLE elective_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    semester_id INTEGER REFERENCES semesters(id),
    department_id INTEGER REFERENCES departments(id)
);

CREATE TABLE elective_group_courses (
    id SERIAL PRIMARY KEY,
    group_id INTEGER REFERENCES elective_groups(id),
    course_id INTEGER REFERENCES courses(id)
);

-- SPACE & TIME ------------------------------------------------------------
CREATE TABLE buildings (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100), code VARCHAR(20),
    location VARCHAR(150), number_of_floors INTEGER
);

CREATE TABLE rooms (
    id SERIAL PRIMARY KEY,
    building_id INTEGER REFERENCES buildings(id),
    room_number VARCHAR(20),
    capacity INTEGER,
    room_type VARCHAR(20) CHECK (room_type IN
        ('CLASSROOM','LAB','SEMINAR_HALL','AUDITORIUM','MEETING_ROOM')),
    department_id INTEGER REFERENCES departments(id),
    has_projector BOOLEAN DEFAULT FALSE,
    has_smart_board BOOLEAN DEFAULT FALSE,
    status VARCHAR(20) DEFAULT 'ACTIVE'
);

CREATE TABLE labs (
    id SERIAL PRIMARY KEY,
    room_id INTEGER REFERENCES rooms(id),
    lab_name VARCHAR(100),
    department_id INTEGER REFERENCES departments(id),
    computer_count INTEGER,
    equipment TEXT,
    software TEXT
);

CREATE TABLE time_slots (
    id SERIAL PRIMARY KEY,
    day VARCHAR(10),
    start_time TIME, end_time TIME,
    slot_type VARCHAR(10) CHECK (slot_type IN ('CLASS','BREAK','LUNCH'))
);

CREATE TABLE faculty_availability (
    id SERIAL PRIMARY KEY,
    faculty_id INTEGER REFERENCES faculty(id),
    slot_id INTEGER REFERENCES time_slots(id),
    availability VARCHAR(15) CHECK (availability IN
        ('AVAILABLE','UNAVAILABLE','PREFERRED')),
    preference INTEGER DEFAULT 0
);

CREATE TABLE academic_calendar (
    id SERIAL PRIMARY KEY,
    academic_year_id INTEGER REFERENCES academic_years(id),
    date DATE,
    event_type VARCHAR(20) CHECK (event_type IN
        ('HOLIDAY','WORKING_DAY','EXAM','EVENT','VACATION')),
    description TEXT
);

-- TIMETABLE ----------------------------------------------------------------
CREATE TABLE timetable_versions (
    id SERIAL PRIMARY KEY,
    academic_year_id INTEGER REFERENCES academic_years(id),
    version_number VARCHAR(10),
    status VARCHAR(20) CHECK (status IN
        ('DRAFT','GENERATED','REVIEWED','VALIDATED','FINALIZED','PUBLISHED',
         'REJECTED','ARCHIVED')),
    created_by INTEGER REFERENCES users(id),      -- always an ADMIN
    approved_by INTEGER REFERENCES users(id),     -- always an ADMIN
    created_at TIMESTAMP DEFAULT now(),
    published_at TIMESTAMP,
    reason TEXT
);

CREATE TABLE timetable_entries (
    id SERIAL PRIMARY KEY,
    version_id INTEGER REFERENCES timetable_versions(id),
    department_id INTEGER REFERENCES departments(id),
    program_id INTEGER REFERENCES programs(id),
    semester_id INTEGER REFERENCES semesters(id),
    section_id INTEGER REFERENCES sections(id),
    batch_id INTEGER REFERENCES batches(id),
    course_id INTEGER REFERENCES courses(id),
    faculty_id INTEGER REFERENCES faculty(id),
    room_id INTEGER REFERENCES rooms(id),
    slot_id INTEGER REFERENCES time_slots(id),
    status VARCHAR(20) DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT','ACTIVE','CANCELLED','RESCHEDULED'))
    -- CANCELLED/RESCHEDULED support the student-facing class-status logic (§8.4a)
);

-- RESOURCES ------------------------------------------------------------------
CREATE TABLE resources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    resource_type VARCHAR(30) CHECK (resource_type IN
        ('LAB','SEMINAR_HALL','PROJECTOR','AUDITORIUM','EQUIPMENT')),
    location VARCHAR(150), capacity INTEGER, status VARCHAR(20) DEFAULT 'ACTIVE'
);

CREATE TABLE resource_bookings (
    id SERIAL PRIMARY KEY,
    resource_id INTEGER REFERENCES resources(id),
    requested_by INTEGER REFERENCES users(id),
    date DATE, start_time TIME, end_time TIME,
    purpose TEXT,
    status VARCHAR(20) CHECK (status IN ('PENDING','APPROVED','REJECTED','CANCELLED')),
    approved_by INTEGER REFERENCES users(id)
);

-- WORKFLOW, NOTIFICATIONS, AUDIT ------------------------------------------
CREATE TABLE change_requests (
    id SERIAL PRIMARY KEY,
    requested_by INTEGER REFERENCES users(id),
    request_type VARCHAR(30) CHECK (request_type IN
        ('TIMETABLE_CHANGE','RESOURCE_REQUEST','FACULTY_AVAILABILITY_CHANGE','ROOM_CHANGE')),
    related_entity_id INTEGER,
    reason TEXT,
    status VARCHAR(20) DEFAULT 'PENDING',
    reviewed_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title VARCHAR(150), message TEXT, type VARCHAR(30),
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(150),
    entity_type VARCHAR(50), entity_id INTEGER,
    old_value JSONB, new_value JSONB,
    timestamp TIMESTAMP DEFAULT now()
);
```

Indexing (add in a migration once tables exist): composite indexes on `(faculty_id, slot_id)`, `(room_id, slot_id)`, `(section_id, slot_id)` on `timetable_entries` — these are the exact lookups the validator and solver hit hardest.

---

# 6. AUTHENTICATION & AUTHORIZATION

## 6.1 Auth flow

```
POST /auth/login {email, password}
  → verify bcrypt hash
  → issue access token (JWT, 15–30 min expiry) + refresh token (7 days, httpOnly cookie)
  → client stores access token in memory, refresh token in httpOnly cookie
  → every protected request: Authorization: Bearer <access_token>
  → FastAPI dependency decodes JWT → loads user → attaches role + department_id to request context
  → POST /auth/refresh rotates access token using refresh token
  → POST /auth/logout invalidates refresh token (server-side denylist or short-lived rotation)
```

## 6.2 RBAC dependency pattern (FastAPI)

```python
def require_role(*allowed_roles):
    def checker(user = Depends(get_current_user)):
        if user.role not in allowed_roles:
            raise HTTPException(403, "Insufficient permissions")
        return user
    return checker

def require_department_scope(user, requested_department_id):
    if user.role in ("ADMIN", "TIMETABLE_COORDINATOR"):
        return True
    if user.department_id != requested_department_id:
        raise HTTPException(403, "Out of department scope")
```

Every route that touches department-scoped data calls `require_department_scope` explicitly — it is never inferred from the frontend request.

## 6.3 Full role → data scope matrix

```
Faculty  → WHERE department_id = user.department_id   (read own department; write own availability/requests only)
Admin    → all departments (full read/write, sole authority on timetable lifecycle)
Student  → WHERE section_id = student.section_id
```

## 6.4 Full permission matrix

| Function | Student | Faculty | Admin |
|---|---:|---:|---:|
| View own timetable | ✅ | ✅ | ✅ |
| View department timetable | ❌ | ✅ (own dept) | ✅ (all) |
| View all departments | ❌ | ❌ | ✅ |
| View current class status | ✅ | ✅ | ✅ |
| Submit faculty availability | ❌ | ✅ | ✅ |
| View faculty availability | ❌ | Own | All |
| Raise timetable issue / change request | Optional | ✅ | ✅ (reviews) |
| Request resource | Optional | ✅ | ✅ |
| Approve resource booking | ❌ | ❌ | ✅ |
| Manage courses / faculty assignment | ❌ | ❌ | ✅ |
| Manage rooms / labs / buildings | ❌ | ❌ | ✅ |
| Generate timetable | ❌ | ❌ | ✅ (only role that can trigger) |
| Edit timetable draft | ❌ | ❌ | ✅ |
| Validate / finalize / publish timetable | ❌ | ❌ | ✅ |
| User management | ❌ | ❌ | ✅ |
| Audit logs | ❌ | ❌ | ✅ |

Faculty and students never get a path to timetable generation, editing, or publishing — even indirectly through the AI assistant. A faculty member asking the chat to "generate the timetable" must be rejected at the Supervisor Agent's authorization check (§8.3), not merely hidden in the UI.

---

# 7. BACKEND API SPECIFICATION

```
Auth
  POST   /auth/login
  POST   /auth/refresh
  POST   /auth/logout
  GET    /auth/me

Users (Admin)
  GET/POST/PUT/DELETE  /users, /users/{id}

Departments
  GET/POST/PUT/DELETE  /departments, /departments/{id}

Faculty
  GET  /faculty  /faculty/{id}  /faculty/{id}/schedule  /faculty/{id}/availability
  PUT  /faculty/{id}/availability

Students
  GET  /students  /students/{id}  /students/{id}/timetable

Courses
  GET/POST/PUT/DELETE  /courses, /courses/{id}

Rooms & Labs
  GET/POST/PUT  /rooms, /rooms/{id}, /rooms/{id}/availability
  GET/POST/PUT  /labs, /labs/{id}, /labs/{id}/availability

Timetable
  POST  /timetable/generate            → enqueues Celery job, returns job_id
  GET   /timetable/jobs/{job_id}        → poll generation status
  GET   /timetable  /timetable/{id}
  POST  /timetable/{id}/validate
  PUT   /timetable/{id}                 (edit a slot — triggers immediate re-validation)
  POST  /timetable/{id}/approve
  POST  /timetable/{id}/publish
  POST  /timetable/{id}/reject

Resources
  GET   /resources  /resources/availability
  POST  /resources/book
  GET   /resources/bookings
  PUT   /resources/bookings/{id}

Change Requests
  GET/POST/PUT  /change-requests, /change-requests/{id}

Notifications
  GET   /notifications
  PUT   /notifications/{id}/read

Audit
  GET   /audit-logs   (Coordinator: filtered; Admin: full)

Chat
  POST  /chat
  GET   /chat/history
```

Every mutating endpoint (`POST`/`PUT`/`DELETE`) writes to `audit_logs` inside the same DB transaction as the mutation — never as a fire-and-forget afterthought.

---

# 8. AI AGENT ARCHITECTURE (LANGGRAPH)

## 8.1 Shared state schema

```python
class AgentState(TypedDict):
    user_id: int
    role: str
    department_id: int | None
    message: str
    intent: str | None
    selected_agent: str | None
    tool_calls: list[dict]
    tool_results: list[dict]
    final_response: str | None
```

## 8.2 Graph topology

```
             ┌──────────────┐
  input ───► │  Supervisor  │
             └──────┬───────┘
        intent + authorization check
                    │
      ┌─────────────┼──────────────┐
      ▼             ▼              ▼
 Query Agent   Scheduling Agent  Resource Agent
      │             │              │
   Tool Layer    OR-Tools        Tool Layer
      │             │              │
      └─────────────┼──────────────┘
                    ▼
             Response Synthesizer
                    │
                 output
```

## 8.3 Supervisor Agent

Responsibilities: intent classification, role/department authorization pre-check (a second check on top of the FastAPI middleware — belt and suspenders), agent routing.

```
Intent taxonomy:
  STUDENT_QUERY          → Query Agent
  FACULTY_QUERY          → Query Agent
  DEPARTMENT_QUERY       → Query Agent
  CLASS_STATUS_QUERY     → Query Agent   (§8.4a — "is my class ongoing/cancelled")
  TIMETABLE_GENERATION   → Scheduling Agent   (role check: ADMIN ONLY — no exceptions)
  TIMETABLE_APPROVAL     → Scheduling Agent   (role check: ADMIN ONLY)
  RESOURCE_AVAILABILITY  → Resource Agent
  RESOURCE_BOOKING       → Resource Agent
  UNKNOWN                → clarifying response, no tool call
```

If the Supervisor cannot map a request to an authorized intent for the requesting role, it returns a permission-denied response **before** any agent or tool executes — this is enforced in code, not left to agent judgement.

## 8.4 Query Agent — tool layer (never invents campus facts)

```python
get_student_profile(student_id)
get_student_timetable(student_id)
get_faculty_profile(faculty_id)
get_faculty_schedule(faculty_id)
get_department_timetable(department_id)
get_course_details(course_id)
get_room_details(room_id)
get_room_availability(room_id, date, slot)
get_lab_details(lab_id)
get_exam_schedule(department_id)
get_academic_calendar(academic_year_id)
get_class_status(section_id, date, current_time)   # see §8.4a
search_campus_information(query)   # RAG-backed, see §15
```

## 8.4a Class status logic (student-facing)

Derived purely from current time vs. a published `timetable_entries` row — never inferred by the LLM:

```python
def get_class_status(entry, now):
    if entry.status == "CANCELLED":
        return "CANCELLED"
    if entry.status == "RESCHEDULED":
        return "RESCHEDULED"
    if now < entry.slot.start_time:
        return "UPCOMING"
    if entry.slot.start_time <= now < entry.slot.end_time:
        return "ONGOING"
    return "COMPLETED"
```

This only ever reads the currently `PUBLISHED` `timetable_version` — draft/unpublished versions never surface to students, regardless of what the Query Agent is asked.

## 8.5 Scheduling Agent

```
generate_timetable(department_id, program_id, semester_id, section_ids[])
  Precondition: requesting_user.role == "ADMIN" — enforced independently at
  FastAPI middleware, Supervisor routing, AND inside this tool (§8.7). No
  other role can reach this function under any phrasing of a chat request.

  1. fetch: sections, courses, course_assignments, faculty, faculty_availability,
            rooms, labs, time_slots, academic_calendar, elective_groups
  2. build CP-SAT model (§9)
  3. solve
  4. run independent validator (§10) — if hard violations > 0, discard and report cause
  5. compute score (§10)
  6. persist as timetable_versions(status=GENERATED) + timetable_entries rows
  7. return version_id + score summary
```

The LLM's role here is exactly: parse the natural-language request into `(department_id, program_id, semester_id, section_ids)`, call the tool, and phrase the result back in natural language. It never touches the CP-SAT model or slot assignment directly.

## 8.6 Resource Agent

```
check_resource_availability(resource_id, date, start_time, end_time)
create_resource_booking(resource_id, requested_by, date, start_time, end_time, purpose)
find_alternative_resources(resource_type, capacity, date, slot)
approve_resource_booking(booking_id, approver_id)
```

## 8.7 Authorization enforcement point

Every tool function above takes `requesting_user` as an argument and re-validates role + department scope inside the tool itself — this is the third and final enforcement layer (FastAPI middleware → Supervisor → tool-level check). A tool must never trust that the LLM only called it in an authorized context.

---

# 9. TIMETABLE OPTIMIZATION ENGINE (OR-TOOLS / CP-SAT)

## 9.1 Decision variables

```python
# x[c, f, s, r, t] = 1 if course c, taught by faculty f, for section s,
#                    is scheduled in room r during time slot t
x = {}
for c in courses:
    for f in eligible_faculty(c):
        for s in sections_needing(c):
            for r in eligible_rooms(c):
                for t in valid_slots:
                    x[c, f, s, r, t] = model.NewBoolVar(f"x_{c}_{f}_{s}_{r}_{t}")
```

## 9.2 Hard constraints (violations must equal zero — no exceptions)

```python
# 1. Faculty cannot teach two classes in the same slot
for f in faculty:
    for t in slots:
        model.Add(sum(x[c,f,s,r,t] for c,s,r in combos_for(f,t)) <= 1)

# 2. Section cannot attend two classes in the same slot
for s in sections:
    for t in slots:
        model.Add(sum(x[c,f,s,r,t] for c,f,r in combos_for(s,t)) <= 1)

# 3. Room cannot host two classes in the same slot
for r in rooms:
    for t in slots:
        model.Add(sum(x[c,f,s,r,t] for c,f,s in combos_for(r,t)) <= 1)

# 4. Room capacity >= section size            → filtered at eligible_rooms(c,s) construction
# 5. No class when faculty unavailable         → excluded from valid_slots per faculty
# 6. Lab courses only in LAB-type rooms        → eligible_rooms(c) filters by room_type
# 7. Weekly required hours per course met      → sum(x[c,f,s,r,t] for all r,t) == required_hours(c)
# 8. No class on holiday/exam calendar dates   → excluded from valid_slots globally
# 9. Elective groups: no two courses in the same elective group overlap in slot,
#    for any section that offers that group
```

## 9.3 Soft constraints (objective, weighted — tune weights empirically and report them)

```python
objective_terms = [
    W_FACULTY_GAP     * faculty_gap_penalty,
    W_STUDENT_GAP     * student_gap_penalty,
    W_PREFERRED_SLOT  * (-1) * preferred_slot_bonus,
    W_ROOM_CHANGE     * unnecessary_room_change_penalty,
    W_LATE_LAB        * late_lab_penalty,
    W_WORKLOAD_BALANCE* faculty_workload_variance,
]
model.Minimize(sum(objective_terms))
```

## 9.4 Solve invocation

```python
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 60
solver.parameters.num_search_workers = 8
status = solver.Solve(model)

if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    return {
        "feasible": False,
        "message": "No feasible timetable exists with the current constraints.",
        "diagnostics": diagnose_infeasibility(...)  # see §9.5
    }
```

## 9.5 Infeasibility diagnosis (never fabricate a timetable)

```
Checks run when solver reports infeasible:
  - room supply vs. required room-hours per department
  - faculty availability hours vs. required teaching hours
  - lab room count vs. lab-course demand
  - elective group overlap count vs. available parallel slots
Return a ranked list of likely causes + a suggested relaxation
  (e.g. "add 2 more slots" / "faculty F102 has only 4 available slots but needs 6").
```

---

# 10. DETERMINISTIC VALIDATOR & SCORER

## 10.1 Validator (independent of the solver — re-checks from scratch)

```python
def validate(timetable_rows) -> ValidationResult:
    violations = []
    violations += check_faculty_collisions(timetable_rows)
    violations += check_room_collisions(timetable_rows)
    violations += check_section_collisions(timetable_rows)
    violations += check_capacity(timetable_rows)
    violations += check_faculty_availability(timetable_rows)
    violations += check_lab_requirements(timetable_rows)
    violations += check_course_hours(timetable_rows)
    violations += check_elective_conflicts(timetable_rows)
    violations += check_calendar_conflicts(timetable_rows)
    hard = [v for v in violations if v.severity == "HARD"]
    assert len(hard) == 0, "Hard constraint violation reached validator — solver bug"
    return ValidationResult(hard_violations=hard, soft_violations=[...])
```

The validator is intentionally redundant with the solver's own constraints — it is the safety net that catches solver/model bugs before a draft ever reaches a human reviewer.

## 10.2 Scorer

```python
def compute_score(validation_result, timetable_rows) -> dict:
    return {
        "total_score": weighted_composite(validation_result),
        "hard_violations": len(validation_result.hard_violations),
        "soft_violations": len(validation_result.soft_violations),
        "room_utilization_pct": room_utilization(timetable_rows),
        "faculty_workload_balance": workload_stddev(timetable_rows),
        "student_gap_minutes_avg": avg_student_gaps(timetable_rows),
    }
```

Never hard-code a score value anywhere — it must always be computed from the actual generated timetable.

---

# 11. RESOURCE ALLOCATION ENGINE

```
Faculty/Admin request
  → Resource Agent
  → check_resource_availability(resource_id, date, slot)
     - query resource_bookings for overlap
     - query timetable for room-based resource conflicts
     - check capacity vs. requested group size
  → available?
       YES → create_resource_booking() → status=PENDING → HOD/Admin approval → status=APPROVED
       NO  → find_alternative_resources() → return ranked alternatives to requester
```

---

# 12. WORKFLOW STATE MACHINES

## 12.1 Timetable version lifecycle

Admin performs every stage below — there is no departmental hand-off. The states still exist separately (rather than collapsing to just DRAFT/PUBLISHED) because each one is a genuinely distinct, auditable checkpoint an Admin can pause at:

```
DRAFT → GENERATED → REVIEWED → VALIDATED → FINALIZED → PUBLISHED
(at REVIEWED or VALIDATED) → REJECTED → back to DRAFT with reason, regenerate
Old PUBLISHED versions → ARCHIVED (never deleted)
```

```
GENERATED   solver produced a candidate; validator already ran once automatically
REVIEWED    Admin has opened and inspected the grid (manual edits allowed here)
VALIDATED   validator re-run after any manual edits; 0 hard violations confirmed
FINALIZED   Admin has locked the version — no further edits without a new version
PUBLISHED   live version visible to students/faculty
```

## 12.2 Change request workflow

```
Faculty submits change request ("unavailable Wed 10AM")
  → Admin reviews
  → Scheduling Agent regenerates only the affected section/faculty slice
  → Validator re-checks (VALIDATED)
  → Admin finalizes and publishes new version
  → affected students/faculty notified automatically
```

## 12.3 Resource booking workflow

Covered in §11 — booking creation always ends in `PENDING`, `APPROVED`, or `REJECTED` (Admin approves), with the transition recorded in `audit_logs`.

---

# 13. NOTIFICATION & AUDIT SYSTEM

**Notify on:** timetable published/updated, change request approved/rejected, resource booking approved/rejected. Delivered via `notifications` table + polled or pushed to frontend (WebSocket optional enhancement).

**Audit on:** every generate/approve/reject/publish/edit action, every faculty availability change, every resource booking decision, every admin master-data edit. Format: `{user, action, entity_type, entity_id, old_value, new_value, timestamp}` — queryable by Coordinator (filtered) and Admin (full).

---

# 14. FRONTEND ARCHITECTURE

## 14.1 Role-based dashboards (three roles, full depth retained in Admin)

```
Student:  Dashboard · My Timetable · Class Status (live) · My Courses ·
          Announcements · AI Assistant
Faculty:  Dashboard · Department Timetable (read-only) · My Schedule ·
          Availability · Resource Requests · Change Requests · Notifications ·
          AI Assistant
Admin:    Dashboard · Users · Departments · Programs · Faculty · Students ·
          Courses · Rooms · Labs · Resources · Academic Calendar ·
          Timetable (Generate → Review → Validate → Finalize → Publish) ·
          Versions · Change Requests · Resource Approvals · Audit Logs ·
          System Settings · AI Assistant
```

Everything the old HOD/Coordinator dashboards did (department-scoped generation, cross-department conflict resolution) is folded into the Admin dashboard as department/program filters on the same screens — no functionality is lost, it's just no longer gated behind a separate role.

## 14.2 Key shared components

```
TimetableGrid          — Mon–Fri × slot grid, editable cell, inline conflict display
GenerationProgressPanel— polls /timetable/jobs/{id}, shows solver stage progress
ApprovalPanel          — approve/reject/regenerate with reason capture
ChatWidget             — POST /chat, streams agent response, shows tool-call trace (dev mode)
ResourceBookingForm
ChangeRequestForm
NotificationBell
AuditLogTable          (Coordinator/Admin only)
```

## 14.3 Data flow

```
React → Axios/React Query → FastAPI → Service Layer → SQLAlchemy → PostgreSQL
React → POST /chat → FastAPI → LangGraph → Agent → Tool → DB/Optimizer → Response → React
React → POST /timetable/generate → Celery job → OR-Tools → Validator → Postgres → poll → React
```

---

# 15. OPTIONAL RAG MODULE

For unstructured institutional documents (academic regulations, attendance policy, exam rules, handbook, lab rules, leave policy).

```
Document → Chunk → Embedding → Vector Store (e.g. pgvector or FAISS)
         → Retriever → Query Agent (search_campus_information tool) → LLM → response
```

Timetable and operational facts never go through RAG — they always come from PostgreSQL via structured tools. RAG is strictly for policy/handbook-style text.

---

# 16. TESTING STRATEGY

```
tests/optimizer/    — solver correctness on Datasets A/B/C; validator catches
                      deliberately-broken fixtures (hand-crafted conflicts)
tests/api/          — CRUD, auth, RBAC boundary tests (e.g. faculty cannot read
                      another department's availability — assert 403)
tests/agents/       — intent classification accuracy, tool-selection correctness,
                      authorization short-circuit tests
tests/integration/  — full request→response flows: chat query end-to-end,
                      generate→validate→approve→publish end-to-end
tests/database/     — migration correctness, constraint/FK integrity
```

Postman/Newman collection covers the full API spec in §7 for contract testing in CI.

---

# 17. EVALUATION & RESEARCH METRICS

## 17.1 Query system

```
Intent accuracy               = correct intents / total test queries
Tool selection accuracy       = correct tool called / total queries requiring a tool
Query resolution rate         = correctly answered / total queries
Response latency               (p50/p95, end-to-end)
```
Build a labeled test set of 100–300 queries across categories: student timetable, faculty timetable, room/lab availability, course info, faculty info, campus info, resource requests, admin queries.

## 17.2 Scheduling engine

```
Hard constraint violations     (must be 0 on every published version)
Soft constraint violations
Generation time
Room utilization %
Faculty workload balance (stddev across faculty)
Student timetable gaps (avg idle minutes/day)
Elective clash count
```
Run against three datasets to test scalability:

```
Dataset A (small):  3 departments, 10 faculty, 15 courses, 10 rooms, 5 sections
Dataset B (medium): 5 departments, 50 faculty, 80 courses, 30 rooms, 20 sections
Dataset C (large):  8+ departments, 100+ faculty, 100+ courses, 50+ rooms, 40+ sections
```

## 17.3 Resource allocation

```
Conflict detection accuracy
Alternative recommendation rate
Booking success rate
```

## 17.4 Research experiment

Compare manual/baseline scheduling vs. the OR-Tools system on: time required, conflict count, resource utilization, faculty gaps, student gaps. This comparison is the strongest evidence for your capstone defense — automate it so it's reproducible, not a one-off manual exercise.

---

# 18. DEVOPS, DEPLOYMENT & OBSERVABILITY

## 18.1 Docker Compose (full multi-service)

```yaml
services:
  db:
    image: postgres:16
    environment: [POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  redis:
    image: redis:7
  backend:
    build: ./backend
    depends_on: [db, redis]
    env_file: .env
  celery_worker:
    build: ./backend
    command: celery -A celery_app worker --loglevel=info
    depends_on: [backend, redis]
  frontend:
    build: ./frontend
    depends_on: [backend]
volumes:
  pgdata:
```

## 18.2 CI (GitHub Actions)

```
on: [push, pull_request]
jobs:
  test:
    - spin up Postgres service container
    - install backend deps, run pytest (optimizer, api, agents)
    - run Alembic migration check
    - lint (ruff/black), type-check (mypy)
    - run Postman/Newman contract tests against a running instance
```

## 18.3 Environment variables

```
DATABASE_URL=postgresql://user:pass@db:5432/campus_ai
REDIS_URL=redis://redis:6379/0
JWT_SECRET=
JWT_ACCESS_EXPIRY_MIN=20
JWT_REFRESH_EXPIRY_DAYS=7
ANTHROPIC_API_KEY=
ENV=production|development
```

## 18.4 Why Celery/Redis for generation

Timetable generation on Dataset B/C can take tens of seconds to minutes. Running it inline in a FastAPI request blocks a worker and risks client timeouts. `/timetable/generate` enqueues a Celery job and returns a `job_id` immediately; the frontend polls `/timetable/jobs/{job_id}` and renders the `GenerationProgressPanel` (§14.2) with live stage updates (loading data → building model → solving → validating → scoring).

## 18.5 Logging & tracing

Structured JSON logs (structlog) with a `request_id` propagated from FastAPI middleware through service calls, Celery tasks, and agent tool calls — essential for debugging a multi-agent, multi-service system during your defense demo if something misbehaves live.

---

# 19. SECURITY CHECKLIST

```
[ ] Passwords stored as bcrypt hashes only, never plaintext
[ ] Short-lived access tokens, rotated refresh tokens, logout invalidates refresh token
[ ] Every protected endpoint enforces role check server-side (never trust frontend)
[ ] Every department-scoped endpoint enforces department check server-side
[ ] Agent tools re-validate authorization independently of Supervisor routing
[ ] SQL access exclusively through SQLAlchemy (parameterized) — no raw string interpolation
[ ] Audit log entry written for every state-changing action
[ ] Rate limiting on /auth/login and /chat endpoints
[ ] CORS restricted to known frontend origin(s)
[ ] Secrets in .env, never committed; .env.example only in repo
```

---

# 20. DEVELOPMENT ROADMAP (FULL, PHASED)

Sequence — do not start LLM/agent work before Stage 5 is solid:

```
Stage 1   Database: full schema (§5), migrations, indexes
Stage 2   Seed data: synthetic generator for Datasets A/B/C
Stage 3   CRUD APIs + Auth/RBAC (§6, §7) for all entities
Stage 4   Timetable engine: CP-SAT model (§9), all hard constraints, one soft constraint
Stage 5   Full soft-constraint set + Validator + Scorer (§10) — zero hard violations proven on A/B/C
Stage 6   Admin timetable UI: generate → review grid → edit → approve → publish
Stage 7   Resource engine: availability → booking → approval (§11)
Stage 8   Role-based dashboards: Student / Faculty / HOD / Coordinator / Admin (§14)
Stage 9   LangGraph agents: Supervisor + Query + Scheduling + Resource (§8)
Stage 10  AI chat wired end-to-end, tool-call tracing visible in dev mode
Stage 11  Notifications, audit log viewer, change-request workflow (§12, §13)
Stage 12  Optional RAG module (§15)
Stage 13  Full evaluation run (§17) + research write-up
Stage 14  CI/CD, deployment, security pass (§18, §19), defense rehearsal
```

Suggested capstone pacing (adjust to your actual academic calendar): Stages 1–3 ≈ weeks 1–3, Stage 4–5 ≈ weeks 4–6, Stage 6–8 ≈ weeks 7–9, Stage 9–11 ≈ weeks 10–12, Stage 12–14 ≈ weeks 13–15, buffer/defense prep ≈ week 16.

---

# 21. CAPSTONE DEFENSE / DEMO SCRIPT

```
1. Problem framing (30s)          — manual scheduling doesn't scale; siloed query handling
2. Architecture walkthrough (2m)  — the five-layer diagram in §2.1, emphasize LLM-never-invents-data rule
3. Live demo — query flow (2m)    — student asks "where is my next class" → trace through
                                     Supervisor → Query Agent → tool → DB → response
4. Live demo — generation (3m)    — HOD requests generation → progress panel → review grid →
                                     show 0 hard violations, actual computed score
5. Live demo — conflict handling  — deliberately create an infeasible scenario, show honest
                                     "no feasible timetable" + diagnosis, not a fabricated result
6. Live demo — approval chain     — HOD approve → Coordinator review → Admin publish →
                                     show notification landing on student/faculty views
7. Evaluation results (2m)        — query resolution rate, scheduling accuracy numbers from §17,
                                     manual-vs-OR-Tools comparison chart
8. Q&A                            — be ready to defend: why CP-SAT over greedy/genetic algorithms,
                                     why validator is independent of solver, how RBAC is enforced
                                     at three separate layers
```

---

# 22. FINAL DELIVERABLES CHECKLIST

```
[ ] Full PostgreSQL schema deployed with migrations
[ ] Seed generators for Datasets A/B/C
[ ] Complete REST API (§7) with auth + RBAC enforced and tested
[ ] CP-SAT timetable engine with all 9 hard constraints + weighted soft constraints
[ ] Independent validator + scorer, both computed (never hardcoded)
[ ] Resource allocation engine with booking + alternative-suggestion
[ ] All five role-based dashboards
[ ] LangGraph multi-agent system (Supervisor, Query, Scheduling, Resource) wired to real tools
[ ] Chat interface with visible tool-call trace for demo/debug
[ ] Notification + audit log system
[ ] Timetable versioning + full approval workflow (HOD→Coordinator→Admin→Publish)
[ ] Change-request workflow with re-optimization loop
[ ] (Optional) RAG module for institutional documents
[ ] Full test suite (optimizer, API, agents, integration) passing in CI
[ ] Evaluation report with real computed metrics for query resolution rate + scheduling accuracy
[ ] Docker Compose deployment (db, redis, backend, celery worker, frontend)
[ ] Security checklist (§19) verified
[ ] Defense demo script rehearsed against a seeded, realistic dataset
```