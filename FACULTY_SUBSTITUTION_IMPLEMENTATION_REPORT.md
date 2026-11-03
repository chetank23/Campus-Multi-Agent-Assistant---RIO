# RIO-MJP — Faculty Substitution & Leave Coverage Implementation Report

**Milestone:** Faculty Substitution Engine, Hard Qualification Gating & Authentic Browser Acceptance  
**Repository:** `chetank23/Campus-Multi-Agent-Assistant---RIO`  
**Target Branch:** `main` (Strict Single-Branch Protocol)  
**Parent Baseline Commit:** `555e2e1`  
**Current Checkpoint Commit:** `a151d1b`  
**Execution Date:** November 3, 2026  
**Status:** COMPLETE, ACCEPTED, FULLY QUALIFIED & VERIFIED  

---

## 1. Executive Summary

The **Faculty Substitution and Leave Coverage** subsystem delivers end-to-end management of temporary faculty absences, automated candidate ranking, administrative approval workflows, and multi-party coordination for campus lectures.

This phase audited, repaired, and rigorously verified all acceptance risks:
1. **Mandatory Hard Qualification Enforcement**:
   - Qualification is a non-negotiable gate, not merely a ranking bonus.
   - Being in the same department does **not** automatically qualify a candidate. A candidate must have verified qualification evidence (`CourseAssignment` or published `TimetableEntry` teaching history for the exact course).
   - Unqualified candidates receive `is_eligible = False`, rank 0, and clear, transparent exclusion reasons (e.g. `QUALIFICATION: FAIL - Lacks verified course assignment or teaching record for this course`).
2. **Explicit Candidate Result Semantics**:
   - `ELIGIBLE`: One or more qualified, conflict-free faculty members are available with sufficient workload headroom.
   - `NO_ELIGIBLE_CANDIDATE`: Candidate evaluation completed normally, but zero candidates satisfy all mandatory criteria (qualification, timetable non-clash, availability, and weekly workload limit).
   - `CANNOT_DETERMINE`: Essential evaluation inputs are missing (e.g., class occurrence has no associated course reference, or no trusted faculty qualification / curriculum records exist in the database for the course), failing closed with explicit explanations.
3. **Availability & Workload Boundary Rules**:
   - Explicit `UNAVAILABLE` preferences in `FacultyAvailability` disqualify candidates.
   - Target-week workload calculations compute actual scheduled load minus approved absences plus approved coverages: `effective_load = max(0, base_load - week_absences + week_coverages)`. A candidate is rejected if `effective_load + 1 > max_weekly_load`.
4. **Scoped Reviewer Permissions & Lifecycle Enforcement**:
   - Reviewer authority is strictly validated via `check_reviewer_authority(db, user, department_id)`:
     - Global `ADMIN` role is authorized across all departments.
     - Non-admin reviewers must hold an active `CoordinatorCapability` (`SUBSTITUTION_COORDINATOR` or `SUBSTITUTION_REVIEWER`).
     - Department-scoped capability authorizes reviews strictly within that department; cross-department attempts receive `HTTP 403 Forbidden`.
     - Revoking capability (`is_active = False`) blocks reviewer operations immediately.
     - Single-request retrieval (`GET /substitutions/requests/{id}`) enforces strict RBAC (admin, authorized reviewer, involved faculty, or enrolled section student).
5. **Authentic Live Browser UI Verification**:
   - Executed real Chromium browser automation using Playwright against live FastAPI (port 8000) and live Vite (port 5173).
   - Authenticated real user personas (Faculty Allison Hill, Admin, Substitute Noah Rhodes, Student Monica Herrera).
   - Captured 8 authentic visual evidence screenshots in `eval/results/substitution_evidence/`.
6. **Master Timetable Immutability Guarantee & Three-Date Invariant**:
   - Date substitutions layer transiently over date-specific queries (`?date=YYYY-MM-DD`).
   - The canonical recurring timetable (`timetable_entries`) remains 100% unaltered.
   - Three-date invariant confirmed: preceding date and following date show canonical teacher, while substituted date shows substitute.
7. **Student Privacy Barrier**:
   - Faculty absence reasons (medical/personal reasons) are strictly masked at the schema serialization, notification dispatch, DOM rendering, and AI assistant layers.
8. **100% Green Verification Across All Quality Gates**:
   - Dedicated Faculty Substitution Pytest Suite: **14/14 passed (100%)**.
   - Full Pytest Regression Suite: **417/417 passed (100%)**.
   - Portal Role Completion Acceptance Suite: **28/28 passed (100%)**.
   - Role Communication Suite: **81/81 passed (100%)**.
   - Full-System E2E Verification Suite: **35/35 passed (100%)**.
   - Campus Events Acceptance Suite: **25/25 passed (100%)**.
   - CDC Placement Acceptance Suite: **12/12 passed (100%)**.
   - Substitution Complete Acceptance Suite: **12/12 passed (100%)**.
   - Live Browser Workflow Suite: **7/7 flows passed (100%)**.
   - Pyright Type Checking: **0 errors, 0 warnings**.
   - Alembic Schema Drift: **0 drift (clean)**.
   - Frontend Production Build: **0 errors (built in 2.31s)**.
   - Frontend Lint: **0 errors (5 baseline warnings)**.

---

## 2. Architecture & Database Design

### 2.1 Table Schema: `faculty_substitutions`
Implemented in `backend/models/substitution.py` and registered in Alembic migration `database/migrations/versions/9a60df141060_add_faculty_substitutions_table.py`.

```sql
CREATE TABLE faculty_substitutions (
    id SERIAL PRIMARY KEY,
    timetable_entry_id INTEGER NOT NULL REFERENCES timetable_entries(id) ON DELETE CASCADE,
    original_faculty_id INTEGER NOT NULL REFERENCES faculty(id) ON DELETE CASCADE,
    substitute_faculty_id INTEGER REFERENCES faculty(id) ON DELETE SET NULL,
    substitution_date DATE NOT NULL,
    reason TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'REQUESTED',
    reviewer_notes TEXT,
    reviewed_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_sub_status CHECK (status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'CANCELLED'))
);

CREATE INDEX ix_faculty_substitutions_date ON faculty_substitutions(substitution_date);
CREATE INDEX ix_faculty_substitutions_status ON faculty_substitutions(status);
CREATE INDEX ix_faculty_substitutions_original_fac ON faculty_substitutions(original_faculty_id);
CREATE INDEX ix_faculty_substitutions_substitute_fac ON faculty_substitutions(substitute_faculty_id);
CREATE INDEX ix_faculty_substitutions_entry_date ON faculty_substitutions(timetable_entry_id, substitution_date);
```

### 2.2 Concurrency & Locking
To avoid PostgreSQL `NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join` when querying relations, the workflow relies on optimistic concurrency control:
- Every record has an integer `version` field starting at 1.
- Reviewer mutations check `sub.version == request.version`, raising `HTTP 409 Conflict` on mismatch, and incrementing `sub.version += 1` on commit.

---

## 3. Candidate Recommendation Engine Algorithm

The ranking engine (`backend/services/substitution_service.py:find_and_rank_substitute_candidates`) evaluates all faculty members across the campus when an unavailability request is inspected.

### 3.1 Eligibility Checks (Mandatory Hard Gates)
A candidate is marked `is_eligible = False` and disqualified if any of the following fail:
1. **Mandatory Hard Qualification Gate**:
   - Candidate must be in `qualified_faculty_ids`, verified through an active `CourseAssignment` for `target_course_id` or an active published `TimetableEntry` teaching this course.
   - Same-department affinity is strictly a ranking bonus (+30 points) applied **only if** the candidate is already qualified. Unqualified faculty receive `QUALIFICATION: FAIL` and `is_eligible = False`.
2. **Active Account Status**:
   - Faculty user account must be active (`is_active == True`). Revoked or deactivated accounts receive `ACTIVE_STATUS: FAIL`.
3. **Timetable Slot Non-Clash**:
   - Candidate must not have any active lecture in `timetable_entries` for the same time slot and weekday in any published timetable.
4. **Availability Constraint**:
   - Candidate must not have an explicit `UNAVAILABLE` record in `faculty_availability` for that slot.
5. **Approved Substitution Non-Clash**:
   - Candidate must not already be covering another approved substitution on that date during that time slot.
6. **Target-Week Workload Limit Compliance**:
   - Computed as: `effective_load = max(0, base_load - week_absences + week_coverages)`.
   - If `effective_load + 1 > max_weekly_load`, candidate receives `WORKLOAD_LIMIT: FAIL`.
7. **Strict Self-Exclusion**:
   - The absent faculty member (`original_faculty_id`) is strictly excluded.

### 3.2 Candidate Result Semantics
- **`ELIGIBLE`**: At least one candidate passed all hard gates.
- **`NO_ELIGIBLE_CANDIDATE`**: Candidate evaluation completed normally, but 0 candidates met all mandatory gates.
- **`CANNOT_DETERMINE`**: Essential evaluation inputs are missing (e.g., class occurrence has no associated course reference, or no trusted faculty qualification / curriculum records exist in the database for the course), failing closed with explicit explanations.

---

## 4. Scoped Reviewer Permissions & Lifecycle Enforcement

Reviewer authorization is centralized in `backend/services/substitution_service.py:check_reviewer_authority`:
```python
def check_reviewer_authority(db: Session, reviewer_user: User, department_id: Optional[int] = None) -> bool:
    if reviewer_user.role == "ADMIN":
        return True

    caps = (
        db.query(CoordinatorCapability)
        .filter(
            CoordinatorCapability.user_id == reviewer_user.id,
            CoordinatorCapability.capability.in_(["SUBSTITUTION_COORDINATOR", "SUBSTITUTION_REVIEWER"]),
            CoordinatorCapability.is_active.is_(True),
        )
        .all()
    )
    if not caps:
        return False

    for c in caps:
        if c.department_id is None:
            return True
        if department_id is not None and c.department_id == department_id:
            return True

    return False
```

### Boundary Guarantees:
- **Global Admins**: Unrestricted approval/rejection across all departments.
- **Department-Scoped Reviewers**: Authorized strictly when `entry.department_id == cap.department_id`. Attempts to review cross-department requests yield `HTTP 403 Forbidden`.
- **Revocation Safety**: Setting `cap.is_active = False` immediately invalidates reviewer privileges without requiring session cache purges.
- **Single-Request Retrieval Security**: `GET /substitutions/requests/{id}` enforces that only Admins, scoped reviewers, the involved faculty, or students enrolled in the section can view the request.

---

## 5. Authentic Live Browser Acceptance Evidence

Executed via `eval/run_browser_verification.py` using Playwright Chromium against live FastAPI (port 8000) and live Vite (port 5173).

| Evidence Artifact | Description |
|---|---|
| `01_faculty_classes_view.png` | Faculty Allison Hill views upcoming scheduled occurrences on `/faculty/substitutions`. |
| `02_faculty_absence_modal.png` | Faculty fills substantive reason in the unavailability reporting modal. |
| `02_faculty_absence_submitted.png` | Faculty inspects submitted request in "My Absence Requests" tab (`REQUESTED` status). |
| `03_admin_pending_queue.png` | Admin inspects pending review queue in `/admin/substitutions`. |
| `04_admin_candidate_inspector.png` | Admin reviews deterministic candidate recommendations with qualification, clash, availability, and workload breakdown badges. |
| `05_admin_approval_confirmed.png` | Admin confirms approval with assigned substitute Noah Rhodes (`APPROVED` status). |
| `06_substitute_covering_duties.png` | Substitute Noah Rhodes views newly assigned duty in "My Covering Duties" tab. |
| `07_student_schedule_privacy_verified.png` | Student Monica Herrera views timetable showing substitute teacher, with private reason 100% masked. |

---

## 6. Verification Results Matrix

| Test Suite / Quality Gate | Scope | Result | Details |
|---|---|---|---|
| `tests/api/test_faculty_substitution.py` | API, RBAC, Semantics, Three-Date Invariant | **14 / 14 PASSED** | 100% Pass in 7.65s |
| `eval/run_browser_verification.py` | Real Live Playwright Chromium UI End-to-End | **7 / 7 PASSED** | Real Vite + FastAPI |
| `eval/test_substitution_browser_acceptance.py` | Full 12-Checkpoint Acceptance Suite | **12 / 12 PASSED** | 100% Pass in 8.35s |
| Full Pytest Regression Suite | Complete backend repository tests | **417 / 417 PASSED** | 100% Pass in 125.15s |
| `eval/test_portal_completion_acceptance.py` | Admin, Faculty, Student Portals | **28 / 28 PASSED** | 100% Pass in 6.00s |
| `eval/test_role_communication.py` | Cross-role broadcasts & RBAC barriers | **81 / 81 PASSED** | 100% Pass in 3.65s |
| `eval/e2e_full_system_test.py` | Complete Full-System E2E Lifecycle | **35 / 35 PASSED** | 100% Pass in 1.81s |
| `eval/test_events_browser_acceptance.py` | Campus Events & Club Coordination | **25 / 25 PASSED** | 100% Pass in 3.50s |
| `eval/test_cdc_browser_acceptance.py` | CDC Placement Management Acceptance | **12 / 12 PASSED** | 100% Pass in 5.25s |
| `npx pyright` | Backend Python Static Type Checking | **0 ERRORS, 0 WARNINGS** | Clean |
| `alembic check` | Database Schema Migration Drift Check | **0 DRIFT** | Clean |
| `npm --prefix frontend run build` | Frontend TypeScript & Vite Production Build | **0 ERRORS** | Built in 2.31s |
| `npm --prefix frontend run lint` | Frontend Oxlint Linting Check | **0 ERRORS** | 5 baseline warnings |

---

## 7. Definition of Done Compliance

- [x] Hard Qualification Gate verified (unqualified candidates strictly rejected, same department does not qualify).
- [x] Candidate result semantics verified (`ELIGIBLE`, `NO_ELIGIBLE_CANDIDATE`, `CANNOT_DETERMINE`).
- [x] Availability preferences and weekly workload bounds calculated accurately.
- [x] Reviewer scoped capabilities enforced with department boundaries and immediate revocation.
- [x] Genuine browser acceptance executed against live Vite and FastAPI servers with authentic screenshot capture.
- [x] Three-date invariant verified (transient date overlay without master timetable mutation).
- [x] Student privacy barrier verified (private absence reasons never leaked to students).
- [x] 100% regression suite passed (417/417 backend tests).
- [x] Zero type errors, zero linter errors, zero migration drift.
- [x] Strictly single-branch on `main`.
