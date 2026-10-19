# RIO-MJP Campus Assistant — Authoritative Behaviour Contract

## 1. Overview and Purpose

The RIO-MJP Campus Assistant is an authenticated, role-scoped conversational interface providing operational access to academic timetables, campus facilities, and directory records. It is designed around deterministic server-side tool execution, explicit state machines, and authoritative backend domain services.

The assistant is not an unconstrained chatbot. All factual claims are grounded directly in PostgreSQL database records. Consequential operations require explicit user authorization and confirmation before execution.

---

## 2. Capability Registry and Agent Responsibilities

The system routes user messages through an acyclic LangGraph supervisor to one of three specialized agents or a deterministic greeting/fallback handler:

### 2.1. Query Agent (`query_agent`)
- **Domain**: Read-only campus information retrieval.
- **Capabilities**:
  - Published personal timetable lookup for students and faculty.
  - Real-time class status (current ongoing class and upcoming class).
  - Academic directory search for faculty profiles, contact details, and specializations.
  - Course catalog exploration including credits, core/elective designation, and departments.
  - Facility location and room information lookup.
  - Academic calendar events, examination dates, and university holidays.
- **Authoritative Services & Tools**:
  - `backend.models.timetable` (published versions only).
  - `backend.models.academic` (faculty, student, department, course records).
  - `backend.models.space_time` (rooms, buildings, calendar events).
- **Guarantees**:
  - Only published timetables (`status = 'PUBLISHED'`) are visible. Draft and generated timetables are strictly invisible.
  - Department scoping and role boundaries are enforced server-side.
  - If a queried entity does not exist, the agent returns an explicit "not found" statement and never invents records.

### 2.2. Scheduling Agent (`scheduling_agent`)
- **Domain**: Academic timetable generation advisory, readiness analysis, and proposal execution.
- **Capabilities**:
  - Scope resolution from natural language (Department, Program, Semester, Academic Year).
  - Data readiness pre-flight checks (faculty availability, room capacities, course assignments).
  - Optimization strategy explanation (`BALANCED`, `FACULTY_COMFORT`, `ROOM_EFFICIENCY`, `LAB_PREFERENCE`).
  - Single-use, time-bounded proposal generation (`prop_<uuid>`).
  - Solver execution via Google OR-Tools CP-SAT engine.
  - Solver diagnostic explanations on infeasibility.
- **Authoritative Services & Tools**:
  - `backend.services.timetable_service.execute_timetable_generation`.
  - `backend.optimizer.timetable_solver.TimetableSolver`.
  - `backend.optimizer.timetable_scorer.TimetableScorer`.
- **Role Restrictions**:
  - Strictly restricted to `ADMIN` users. Faculty and Students receive an authorization restriction response.
- **Guarantees**:
  - Generated timetables are saved exclusively in `DRAFT` or `GENERATED` status.
  - AI agents cannot publish a timetable. Publication requires deliberate Administrator action in the Admin Workspace.
  - Proposals expire after 15 minutes and can be confirmed only once by the originating user.

### 2.3. Resource Agent (`resource_agent`)
- **Domain**: Campus facility and equipment discovery, availability verification, booking proposals, status tracking, and cancellation.
- **Capabilities**:
  - Facility discovery by type, capacity, building, and keywords.
  - Authoritative availability checks under the Global Resource Lock policy.
  - Single-use, time-bounded booking proposal creation (`res_prop_<hex>`).
  - Booking submission in `PENDING` state for administrative review.
  - Booking request status lookup and cancellation by the booking owner.
- **Authoritative Services & Tools**:
  - `backend.services.resource_booking_service.create_booking_request`.
  - `backend.services.resource_booking_service.cancel_booking_request`.
  - `backend.services.resource_booking_service.check_resource_conflicts`.
- **Role Restrictions**:
  - Any authenticated role (`STUDENT`, `FACULTY`, `ADMIN`) may discover resources, check availability, request bookings, and cancel their own bookings.
  - Administrative approval and rejection (`approve`, `reject`) are restricted to `ADMIN` users through the Admin Resource Management portal.
- **Guarantees**:
  - Enforces the Global Resource Lock policy (see Section 4).
  - Replays of consumed proposal tokens are rejected.
  - Cross-user confirmation is blocked.

---

## 3. Role and Authorization Matrix

| Action / Entity | STUDENT | FACULTY | ADMIN | Authoritative Enforcement |
|---|---|---|---|---|
| View own published schedule | Allowed | Allowed | Allowed | `get_student_timetable` / `get_faculty_schedule` |
| View other users' private schedule | Denied | Denied | Allowed | Database filter by session user ID |
| Search course, room, calendar directory | Allowed | Allowed | Allowed | Read-only database queries |
| Discover active resources & equipment | Allowed | Allowed | Allowed | `discover_resources_data` |
| Check resource availability | Allowed | Allowed | Allowed | `check_resource_availability_data` |
| Request / Propose resource booking | Allowed | Allowed | Allowed | `create_booking_request` (`PENDING`) |
| Cancel own resource booking | Allowed | Allowed | Allowed | Verified `requested_by == current_user.id` |
| Cancel another user's booking | Denied | Denied | Allowed | `cancel_booking_request` (HTTP 403) |
| Approve or Reject resource booking | Denied | Denied | Allowed | `approve_booking_request` (HTTP 403) |
| Inquire timetable strategies & readiness | Denied | Denied | Allowed | `scheduling_agent` role check |
| Create timetable generation proposal | Denied | Denied | Allowed | `scheduling_agent` role check |
| Execute timetable solver | Denied | Denied | Allowed | `execute_timetable_generation` |
| Finalize / Publish timetable version | Denied | Denied | Allowed | Admin Timetable Review API |

---

## 4. Global Resource Lock Policy

### 4.1. The Policy
A campus resource (facility, seminar hall, auditorium, lab, or equipment) with an active booking is reported as unavailable for all new bookings and availability inquiries, regardless of the requested purpose, date, or time.

1. **Active Lock Definition**:
   Any booking record in `PENDING` or `APPROVED` status constitutes an active global lock on that resource.
2. **Lock Release Conditions**:
   A resource becomes eligible for new booking requests or availability confirmation only when all active bookings on that resource have transitioned to a terminal state (`CANCELLED` or `REJECTED`) committed in the database.
3. **Scope of Lock**:
   The lock is resource-global. It prevents reuse on different days or different hours while any prior booking remains in `PENDING` or `APPROVED` status.
4. **Mandatory Plain-English Lock Response**:
   When an inquiry or booking attempt targets a locked resource:
   `Resource already booked. <Resource Name> has an active booking and is not available for another booking. Please select another resource.`

### 4.2. Concurrency and Transaction Safety
- Booking creation and approval operations utilize PostgreSQL row locking (`SELECT ... FOR UPDATE` on the parent `Resource` row).
- Two concurrent requests targeting the same resource serialize on the resource lock; exactly one will successfully acquire the lock, while the competing request receives an HTTP 409 Conflict.

---

## 5. Plain-English Communication Standard

Every user-facing response from every agent adheres strictly to the following standards:

### 5.1. Permitted Style
- Direct, clear, professional English.
- Short, grammatically complete sentences.
- Real entity names, dates, times, statuses, and identifiers.
- Clear action summaries and next steps.

### 5.2. Prohibited Formatting
- **No emojis or Unicode pictograms**: Icons such as 👋, 📅, 🔒, ⚠️, 🛑, 📋, 🎉, ❌, etc., are strictly prohibited.
- **No markdown headings**: Strings starting with `#`, `##`, `###`, etc., are prohibited.
- **No bold or italic asterisks**: Text enclosed in `**bold**` or `*italic*` is prohibited.
- **No raw tool outputs or stack traces**: Technical JSON errors must be translated into direct plain English.

---

## 6. Confirmation and Lifecycle Guardrails

1. **Explicit User Intent for Writes**:
   No mutating action (timetable solver execution, facility reservation creation) executes on an ambiguous message. The system presents a validated proposal and requires deliberate confirmation (`confirm <token>` or plain-text confirmation `"yes"`/`"confirm"`).
2. **Single-Use Tokens**:
   Proposal stores enforce single-use consumption. Duplicate submissions or replay attacks return `Confirmation Blocked: Proposal has already been confirmed.`
3. **Cross-Agent Isolation**:
   Resource proposal tokens (`res_prop_*`) cannot trigger timetable generation. Scheduling proposal tokens (`prop_*`) cannot trigger resource bookings.
4. **Freshness Re-Validation**:
   At the instant of confirmation, the backend re-validates data prerequisites and resource availability against the live database before committing.
