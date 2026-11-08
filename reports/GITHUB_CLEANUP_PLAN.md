# RIO-MJP — GitHub Cleanup Plan & Repository Readiness

**Audit Date:** November 8, 2026  
**Current Branch:** `main`  
**Remote URL:** `https://github.com/chetank23/Campus-Multi-Agent-Assistant---RIO.git`  
**Last Pushed Commit:** `d8fd470` (`fix: resolve pyrefly diagnostics, student isolation, and 60-student verification`)  
**Synchronization Status:** Up to date with `origin/main` (0 commits ahead, 0 commits behind)

---

## 1. Executive Git State Summary

The local working directory contains substantial uncommitted development work from recent sessions:
- **53 Modified Tracked Files** (`backend/`, `frontend/`, `agents/`, `scripts/`, `tests/`)
- **20 Untracked Files and Folders** (including critical migration, admin page, test suite, and temporary scripts)
- **0 Staged Files** (nothing currently queued in the Git index)
- **0 Merge Conflicts**

### Critical Findings
1. **Tracked SQLite Database (`test.db`):**  
   A 110,592-byte SQLite database (`test.db`) is currently **tracked** in Git. This file was committed in an earlier stage and has remained in the Git index.
2. **Untracked Core Subsystem Files:**  
   The entire Canonical Timetable implementation is currently split between modified files and untracked files:
   - `database/migrations/versions/e4f5a6b7c8d9_add_canonical_timetables.py` (**Untracked**)
   - `frontend/src/pages/admin/timetable/AdminTimetableManagementPage.tsx` (**Untracked**)
   - `tests/api/test_canonical_timetable_workflow.py` (**Untracked**)
   - `data/raw/RIO_MJP_AIDS_A_Clean_Test_Data_No_Attendance.xlsx` (**Untracked**)
   If pushed without these untracked files, the remote repository would be severely broken.
3. **Missing `.gitignore` Exclusions:**  
   - `test_pg_5433/` (the local PostgreSQL test cluster directory) is not excluded in `.gitignore`.
   - `*.db` is missing (`.gitignore` only contains `*.sqlite3`).
   - `.kilo/`, `.qodo/`, and `eval/results/` are not excluded.

---

## 2. File Categorization Matrix

### Category A: Core Features to Stage & Commit (Must Preserve)

| File Path | Description | Reason to Commit |
|:---|:---|:---|
| `database/migrations/versions/e4f5a6b7c8d9_add_canonical_timetables.py` | Canonical timetables Alembic migration | Establishes `timetables` table and FK in schema |
| `frontend/src/pages/admin/timetable/AdminTimetableManagementPage.tsx` | Admin Canonical Timetable Management Page | Primary UI for preview, validation, and publishing |
| `tests/api/test_canonical_timetable_workflow.py` | Canonical timetable workflow integration tests | Verification suite for admin generation & publishing |
| `data/raw/RIO_MJP_AIDS_A_Clean_Test_Data_No_Attendance.xlsx` | Authoritative AIDS-A master Excel workbook | Source of truth for clean 60-student dataset |
| `backend/models/timetable.py` | `Timetable` canonical model & relationships | Prevents duplicate version sprawl |
| `backend/routes/timetable.py` | Preview generation and publish routes | Core scheduling API surface |
| `backend/services/timetable_service.py` | In-memory solver & canonical publish service | Business logic for optimization & publishing |
| `frontend/src/api/timetable.ts` | Frontend client for preview & publishing | Connects UI to canonical routes |
| `frontend/src/components/timetable/PersonalTimetableGrid.tsx` | Role-aware personal timetable grid | Student & faculty timetable display |
| `pyrefly.toml`, `pyrightconfig.json`, `pytest.ini` | Python typing & test configurations | Preserves 0-error type checking |

### Category B: Audit & Verification Reports to Preserve

| File Path | Description | Action |
|:---|:---|:---|
| `reports/COMPLETE_REPOSITORY_FORENSIC_AUDIT.md` | Comprehensive forensic inspection report | Track in Git |
| `reports/FEATURE_IMPLEMENTATION_MATRIX.md` | Feature-by-feature implementation matrix | Track in Git |
| `reports/API_ROUTE_INVENTORY.md` | Complete 253-operation API inventory | Track in Git |
| `reports/DATABASE_INTEGRITY_AUDIT.md` | Schema, migration, and workbook audit | Track in Git |
| `reports/GITHUB_CLEANUP_PLAN.md` | GitHub cleanup & readiness plan | Track in Git |
| `reports/RECOVERY_AND_NEXT_STEPS.md` | Prioritized remediation roadmap | Track in Git |
| `reports/ROLE_BASED_LIVE_BROWSER_TEST_REPORT.md` | 42/42 Playwright browser test results | Track in Git |
| `reports/PRE_STABILIZATION_BASELINE.md` | Pre-stabilization baseline audit | Track in Git |
| `reports/CODEBASE_COMPLETE_ERROR_AUDIT.md` | Codebase error elimination audit | Track in Git |

### Category C: Files to Remove from Git Index (Untrack)

| File Path | Size | Reason to Untrack | Safe Command |
|:---|:---:|:---|:---|
| `test.db` | 110 KB | SQLite binary database committed in error | `git rm --cached test.db` |

### Category D: Temporary Debug Scripts (Review Before Commit)

| File Path | Description | Recommended Action |
|:---|:---|:---|
| `scripts/check_slots.py` | Scratch script for inspecting time slot IDs | Move to scratch / do not track |
| `scripts/check_preview_data.py` | Scratch script for preview response checks | Move to scratch / do not track |
| `scripts/inspect_preview_entries.py` | Scratch script for preview duplicate checks | Move to scratch / do not track |
| `scripts/db_port_forwarder.py` | TCP proxy for port 5433 -> 5432 forwarding | Preserve if needed for systems lacking admin port access |
| `scripts/clean_and_replace_aids_a_test_data.py` | Automated workbook replacement runner | Preserve & track (vital tooling) |
| `scripts/import_aids_a_dataset.py` | Authoritative dataset importer | Preserve & track (vital tooling) |
| `scripts/verify_all_60_students.py` | 60-student verification test runner | Preserve & track (vital tooling) |

### Category E: Local & Generated Assets to Ignore (`.gitignore`)

| File / Pattern | Type | Reason |
|:---|:---|:---|
| `test_pg_5433/` | Directory | Local PostgreSQL cluster data directory |
| `*.db` | Pattern | Catches SQLite databases (`test.db`) |
| `.kilo/` | Directory | Local IDE assistant cache |
| `.qodo/` | Directory | Local AI extension cache |
| `eval/results/` | Directory | Local Playwright screenshot dumps |
| `reports/screenshots/` | Directory | Local test screenshots (binary files) |

---

## 3. Required `.gitignore` Updates

The following lines must be appended to `.gitignore`:

```gitignore
# Database binary files & clusters
*.db
test_pg_5433/

# Tool & IDE caches
.kilo/
.qodo/
.pytest_cache/

# Test browser artifacts
eval/results/
reports/screenshots/
```

---

## 4. GitHub Push Readiness Checklist

- [ ] Untrack `test.db` via `git rm --cached test.db`.
- [ ] Update `.gitignore` with missing patterns.
- [ ] Fix the time slot day format mismatch (`MON-SAT` vs `MONDAY-SATURDAY`) in `timetable_input_loader.py`.
- [ ] Stamp `alembic_version` to `e4f5a6b7c8d9`.
- [ ] Seed missing `SUPER_ADMIN` user in test database.
- [ ] Verify `npx pyright` returns 0 errors.
- [ ] Verify `npm run build` returns 0 errors.
- [ ] Verify `npm run lint` returns 0 errors.
- [ ] Stage verified source files, migrations, authoritative workbook, and audit reports.
- [ ] Review staged diff with `git diff --cached --stat`.
- [ ] Create atomic conventional commit: `feat: implement canonical timetable architecture, workbook alignment, and complete forensic audit`.
- [ ] Push cleanly to `origin/main`.

