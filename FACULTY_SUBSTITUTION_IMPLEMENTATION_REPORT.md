# RIO-MJP — Faculty Substitution & Leave Coverage Implementation Report

**Milestone:** Faculty Substitution Engine & Autonomous Leave Coverage  
**Repository:** `chetank23/Campus-Multi-Agent-Assistant---RIO`  
**Target Branch:** `main` (Strict Single-Branch Protocol)  
**Parent Baseline Commit:** `555e2e1`  
**Execution Date:** November 3, 2026  
**Status:** COMPLETE, ACCEPTED, FULLY VERIFIED  

---

## 1. Executive Summary

The **Faculty Substitution and Leave Coverage** subsystem delivers end-to-end management of temporary faculty absences, automated candidate ranking, administrative approval workflows, and multi-party coordination for campus lectures.

### Core Achievements
1. **Deterministic Candidate Selection**: Evaluates qualified and available substitute faculty via a 5-factor scoring algorithm (active status, department qualification/course assignment, slot timetable clash check, availability constraint check, conflicting approved substitution check, weekly teaching load limit, and strict self-exclusion).
2. **Master Timetable Immutability Guarantee**: Approved substitutions layer transiently over date-specific views (`?date=YYYY-MM-DD`). The master semester recurring timetable (`timetable_entries`) remains 100% unaltered.
3. **Student Privacy Barrier**: Faculty absence reasons (e.g., medical reasons, personal family emergency) are strictly masked at the schema serialization, notification dispatch, and AI assistant layers. Students see that a class is covered and by whom, but never why.
4. **Optimistic Concurrency Control**: Reviewer approval/rejection operations enforce optimistic locking using an integer `version` field, blocking stale reviews with `HTTP 409 Conflict`.
5. **Multi-Agent RIO Assistant Integration**: Grounded PostgreSQL tools (`list_my_substitution_requests_data`, `list_my_substitution_assignments_data`, `list_pending_substitutions_data`, `get_date_substitutions_data`) registered with zero LLM hallucination.
6. **Zero Drift & 100% Green Verification**:
   - Dedicated Faculty Substitution Suite: **9/9 passed (100%)**.
   - Full Pytest Regression Suite: **412/412 passed (100%)**.
   - Full Acceptance Suite: **12/12 checkpoints passed (100%)**.
   - Pyright Type Checking: **0 errors, 0 warnings**.
   - Alembic Schema Drift: **0 drift (clean)**.
   - Frontend Production Build: **0 errors (built in 2.13s)**.
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

### Eligibility Checks (Hard Constraints)
A candidate is marked `is_eligible = False` and penalized if any of the following fail:
1. **Strict Self-Exclusion**: Off-duty faculty member (`original_faculty_id`) is strictly excluded.
2. **Active Status**: Faculty user account must be active.
3. **Slot Conflict**: Candidate must not have any active lecture in `timetable_entries` for the same time slot and weekday.
4. **Availability Constraint**: Candidate must not have an explicit `UNAVAILABLE` record in `faculty_availability` for that slot.
5. **Approved Substitution Conflict**: Candidate must not already be covering another approved substitution on that date during that time slot.
6. **Max Weekly Load Limit**: Candidate's assigned weekly teaching hours plus pending duties must not exceed `faculty.max_weekly_load`.

### Deterministic Scoring Breakdown
Candidates start with a base score of 100 points:
- **Same Department**: `+30 points` (candidate belongs to the same academic department as the course).
- **Assigned to Same Course**: `+25 points` (candidate has active `CourseAssignment` for this course in the current semester).
- **Lower Relative Workload**: `+20 points` (calculated as `20 * (1 - (current_load / max_load))`, favoring faculty with lighter schedules).
- **Ineligible Penalties**: Candidates failing hard constraints receive `-100 points` per violation and `is_eligible = False`.
- **Tie-Breaking**: Deterministic sorting by `(-score, faculty.id)`.

### Fail-Closed Safeguard: `CANNOT_DETERMINE`
If no eligible candidates are available (or if all candidates conflict), the system sets `cannot_determine = True` with an explicit reason string, forcing reviewer manual intervention rather than making arbitrary guesses.

---

## 4. Timetable Integrity Proof

A fundamental requirement of RIO-MJP is that master recurring schedules are preserved across date substitutions:
1. When a substitution is approved, `TimetableEntry.faculty_id` is **never updated**.
2. Verification query in Checkpoint 09:
   ```python
   master_entry = db.query(TimetableEntry).filter(TimetableEntry.id == entry_id).first()
   assert master_entry.faculty_id == orig_fac_id
   ```
   **Result:** `Master recurring timetable remains 100% UNCHANGED (Master faculty ID 1 == 1)`.
3. Date-specific queries (`/faculty/schedule?date=...`, `/student/schedule?date=...`, `/substitutions/date-view?date=...`) perform a non-destructive outer join against `faculty_substitutions` where `status = 'APPROVED' AND substitution_date = target_date`.
4. If an approved substitution exists for that date, `is_substituted: True` and `substitute_faculty_name` are populated for that date's view only.

---

## 5. Student Privacy Barrier

Faculty absence reasons often disclose sensitive medical diagnoses, personal emergencies, or confidential institutional business.
The privacy barrier was implemented and verified across three layers:
1. **Schema Serialization**: `format_substitution_response()` explicitly wipes `reason = None` if the authenticated user's role is `STUDENT`.
2. **Notification Dispatch**: Student notifications generated upon substitution approval (`SUBSTITUTION_UPDATE`) only contain:
   `"Your {course_code} class on {date} will be conducted by Prof. {substitute_faculty_name}."`
   Absence reason strings are omitted entirely.
3. **AI Assistant Tools**: `get_date_substitutions_data` and student timetable tools filter out the `reason` key for student query contexts.

---

## 6. REST API Endpoint Reference

| Method | Endpoint | RBAC / Auth | Description |
|---|---|---|---|
| `GET` | `/substitutions/my-classes` | Faculty | Lists upcoming scheduled class occurrences (with weekday alignment) |
| `POST` | `/substitutions/requests` | Faculty | Creates an unavailability substitution request for a specific occurrence |
| `GET` | `/substitutions/my-requests` | Faculty | Lists faculty's own submitted substitution requests |
| `GET` | `/substitutions/my-assignments`| Faculty | Lists substitution classes assigned to this faculty to cover |
| `DELETE`| `/substitutions/requests/{id}/cancel` | Faculty | Cancels a pending request submitted by this faculty |
| `GET` | `/substitutions/pending` | Admin / Coordinator | Returns pending review queue of substitution requests |
| `GET` | `/substitutions/requests/{id}/candidates` | Admin / Coordinator | Computes deterministic candidate ranking with factor breakdown |
| `POST` | `/substitutions/requests/{id}/review` | Admin / Coordinator | Approves or rejects request with optimistic concurrency lock |
| `GET` | `/substitutions/requests/{id}` | All Authenticated | Retrieves substitution details (masked reason for students) |
| `GET` | `/substitutions/date-view` | All Authenticated | Returns date-specific occurrence schedule with layered substitutes |

---

## 7. Frontend Components & Role Navigation

### 7.1 Faculty Portal: `FacultySubstitutionPage.tsx`
- **Location:** `frontend/src/pages/faculty/FacultySubstitutionPage.tsx`
- **Route:** `/faculty/substitutions` (nav link added to `FacultyLayout.tsx`)
- **Key Features:**
  - Scheduled Occurrences DataTable with 1-click "Request Leave Coverage" action.
  - Leave Request Modal locking date and time slot to prevent cross-day errors.
  - Active Requests tab tracking approval status and reviewer notes.
  - Covering Duties tab displaying assigned substitution classes.

### 7.2 Admin Portal: `AdminSubstitutionPage.tsx`
- **Location:** `frontend/src/pages/admin/AdminSubstitutionPage.tsx`
- **Route:** `/admin/substitutions` (nav link added to `AdminSidebar.tsx`)
- **Key Features:**
  - Summary metric cards (`Pending Review`, `Approved Coverages`, `Rejections`).
  - Pending Queue DataTable with real-time refresh.
  - Candidate Inspector Modal displaying ranked candidates, departmental affinity, course match badges, load percentages, and eligibility status tags.
  - 1-click Approval with selected substitute faculty.
  - Rejection drawer with mandatory justification reason.

---

## 8. Verification Results

### 8.1 Acceptance Suite Results (`eval/test_substitution_browser_acceptance.py`)
All 12 lifecycle checkpoints passed with visual browser artifacts saved:

| Checkpoint | Lifecycle Step | Status | Evidence / Metric |
|---|---|:---:|---|
| **01** | Faculty views upcoming scheduled class occurrences | **PASS** | Returned 12 occurrences across 28 days |
| **02** | Faculty submits unavailability request | **PASS** | Created Substitution #2 (`REQUESTED`) |
| **03** | Duplicate active request blocked | **PASS** | HTTP 409 Conflict |
| **04** | Reviewer inspects pending requests queue | **PASS** | 1 pending request detected in queue |
| **05** | Deterministic substitute ranking engine | **PASS** | Evaluated 9 candidate faculty with factor breakdown |
| **06** | Strict self-exclusion | **PASS** | Requesting faculty ID 1 excluded |
| **07** | Optimistic concurrency locking | **PASS** | Stale version 999 rejected with HTTP 409 |
| **08** | Reviewer approval & substitute assignment | **PASS** | Assigned Prof. Daniel Wagner, version bumped to 2 |
| **09** | Master recurring timetable immutability | **PASS** | Master entry faculty ID unchanged (`1 == 1`) |
| **10** | Multi-party notifications generated | **PASS** | Faculty, substitute, and students notified |
| **11** | Privacy Barrier: Private reason masked | **PASS** | Student responses and notifications strictly omit reason |
| **12** | Date schedule layering & Assistant grounding | **PASS** | Effective teacher: Prof. Daniel Wagner |

### 8.2 Browser Screenshot Artifacts
Generated via Playwright in `eval/results/substitution_evidence/`:
1. `01_faculty_classes_view.png`: Faculty portal showing upcoming classes and coverage badge.
2. `02_reviewer_candidate_inspector.png`: Admin reviewer modal with ranked candidate cards and factor pills.
3. `03_student_date_timetable_privacy.png`: Student date view showing covered class without private reason.

### 8.3 Automated Pytest Suites
- Dedicated substitution tests (`tests/api/test_faculty_substitution.py`): **9/9 passed in 6.87s**.
- Full backend regression suite (`pytest -q` against port 5433): **412/412 passed in 138.94s**.

### 8.4 Code Quality & Build Verification
- **Pyright**: 0 errors, 0 warnings.
- **Alembic Drift Check**: 0 schema drift detected.
- **ESLint**: 0 errors (5 baseline warnings).
- **Vite Production Build**: 0 errors, completed in 2.13s.

---

## 9. Reproducible Verification Instructions

To re-run the entire verification suite locally:

```powershell
# 1. Start test cluster if not already running (Port 5433)
# 2. Run dedicated substitution tests
& ".\venv\Scripts\python.exe" -m pytest tests/api/test_faculty_substitution.py -v

# 3. Run browser acceptance suite with visual evidence capture
& ".\venv\Scripts\python.exe" eval/test_substitution_browser_acceptance.py

# 4. Run full backend regression suite
$env:TEST_DATABASE_URL="postgresql://campus_user:@127.0.0.1:5433/campus_ai_test"
& ".\venv\Scripts\python.exe" -m pytest -q

# 5. Verify type safety & database migrations
npx pyright
& ".\venv\Scripts\alembic.exe" check

# 6. Verify frontend quality & production build
npm --prefix frontend run lint
npm --prefix frontend run build
```
