# RIO-MJP — Test Infrastructure & Regression Guide

**Repository:** `C:\Users\Chethan Kumar\Desktop\RIO-MJP`  
**Python Environment:** `.\venv\Scripts\python.exe` (Python 3.13.1)  
**Test Framework:** `pytest 9.1.1` with `pytest-asyncio`, `anyio`  
**Static Analysis:** `pyrefly 0.1` (`.\venv\Scripts\pyrefly.exe`), `oxlint`  
**Database Infrastructure:** PostgreSQL 18 Daemon on Port `5433`  

---

## 1. Test Environment Setup

### 1.1 PostgreSQL Daemon (Port 5433)
The test database cluster runs locally on port 5433 with data directory `c:\Users\Chethan Kumar\Desktop\RIO-MJP\test_pg_5433`:
```powershell
& "C:\Program Files\PostgreSQL\18\bin\postgres.exe" -D "c:\Users\Chethan Kumar\Desktop\RIO-MJP\test_pg_5433"
```

Databases configured:
- `campus_ai_test`: Operational and baseline integration database.
- `campus_ai_pytest`: Dedicated isolated database seeded per test suite via `tests/conftest.py`.

### 1.2 Redis Broker (Optional for Background Queue)
```powershell
redis-server --port 6379
```
*Note:* If Redis is offline, the Celery app automatically logs a warning and falls back to synchronous inline execution for headless testing.

---

## 2. Test Suites Inventory

| Test Module | Coverage Scope | Test Count | Status |
|---|---|---|---|
| `tests/test_phase2_multi_section_and_tasks.py` | Celery task status endpoint, multi-section CP-SAT timetable generation, conflict prevention, atomic publication, SSE notifications | 3 | **PASSED** (100%) |
| `tests/test_placements_and_events_api.py` | CDC placement drive listing, academic eligibility check, application lifecycle, club memberships, event registrations, PDF upload security | 5 | **PASSED** (100%) |
| `tests/api/test_auth.py` | Login success, token generation, refresh tokens, invalid credentials, RBAC token decoding | 12 | **PASSED** (100%) |
| `tests/api/test_cdc_placements.py` | CDC drive CRUD, eligibility logic, application transitions, student isolation | 6 | **PASSED** (100%) |
| `tests/api/test_events_and_clubs.py` | Club creation, member limits, event capacity tracking, cancelations | 8 | **PASSED** (100%) |
| `tests/test_stage13_e2e_acceptance.py` | Comprehensive multi-role end-to-end user journeys (Admin $\rightarrow$ Faculty $\rightarrow$ Student) | 5 | **PASSED** (100%) |

---

## 3. Standard Verification Commands

### 3.1 Run Phase 2 Integration Tests
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_phase2_multi_section_and_tasks.py tests/test_placements_and_events_api.py -v
```

### 3.2 Run Pyrefly Type Safety Verification
```powershell
.\venv\Scripts\pyrefly.exe check tests/test_phase2_multi_section_and_tasks.py tests/test_placements_and_events_api.py backend/optimizer/timetable_solver.py
```

### 3.3 Run Full API Integration Suite
```powershell
.\venv\Scripts\python.exe -m pytest tests/api/ -v
```

### 3.4 Run Frontend Lint and Production Build
```powershell
cd frontend
npm run lint
npm run build
```
