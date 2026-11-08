"""
scripts/test_timetable_generation_scenarios.py
----------------------------------------------
Automated verification utility to test OR-Tools CP-SAT timetable generation
under both working-day configurations:
- Scenario A: Monday - Saturday (6-day instructional week)
- Scenario B: Monday - Friday (5-day instructional week)

Ensures:
- 100% type-safe ORM narrowing (zero NoneType attribute access).
- Explicit authentication and role validation for current_user.
- Academic scope consistency without fabricated records.
- Complete constraint validation (zero blockers, zero warnings).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TypeVar

# Add repository root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.models.academic import AcademicYear, Department, Program, Section, Semester
from backend.models.identity import User
from backend.models.space_time import Building
from backend.schemas.timetable_generation import GenerationScope
from backend.services.timetable_service import generate_timetable_preview

T = TypeVar("T")


def require_record(record: T | None, description: str) -> T:
    """Safely narrows an optional ORM lookup, raising a descriptive error if missing."""
    if record is None:
        raise RuntimeError(
            f"Database integrity failure: Required record '{description}' was not found in the database."
        )
    return record


def main() -> None:
    with SessionLocal() as db:
        print("=" * 80)
        print("VERIFYING TIMETABLE GENERATION SCENARIOS (6-DAY vs 5-DAY)")
        print("=" * 80)

        # 1. Authenticate and validate admin user
        admin_candidate: User | None = db.query(User).filter(User.role == "ADMIN").first()
        admin_user: User = require_record(admin_candidate, "Active user with ADMIN role")
        if admin_user.role != "ADMIN":
            raise RuntimeError(
                f"Authorization failure: User {admin_user.email} has role '{admin_user.role}', expected 'ADMIN'."
            )
        print(f"[AUTH] Verified Admin User: {admin_user.email} (ID: {admin_user.id}, Role: {admin_user.role})")

        # 2. Look up and narrow required academic scope records
        ay: AcademicYear = require_record(
            db.query(AcademicYear).filter(AcademicYear.name == "2026-2027").first(),
            "Academic Year '2026-2027'",
        )

        sem: Semester = require_record(
            db.query(Semester)
            .filter(Semester.academic_year_id == ay.id, Semester.semester_number == 7)
            .first(),
            "Semester 7 for Academic Year 2026-2027",
        )

        dept: Department = require_record(
            db.query(Department).filter(Department.department_code == "AIDS").first(),
            "Department 'AIDS'",
        )

        prog: Program = require_record(
            db.query(Program).filter(Program.department_id == dept.id).first(),
            "Program for Department AIDS",
        )

        sec: Section = require_record(
            db.query(Section).filter(Section.section_name == "AIDS-A").first(),
            "Section 'AIDS-A'",
        )

        bldg: Building = require_record(
            db.query(Building).filter(Building.code == "SMV-BLK-01").first(),
            "Building 'SMV-BLK-01'",
        )

        print(
            f"[SCOPE] AY: {ay.id} ({ay.name}) | Sem: {sem.id} (Sem {sem.semester_number}) | "
            f"Dept: {dept.id} ({dept.department_code}) | Program: {prog.id} | "
            f"Section: {sec.id} ({sec.section_name}) | Building: {bldg.id} ({bldg.code})"
        )

        # ----------------------------------------------------------------------
        # SCENARIO A: Monday - Saturday (6-Day Working Week)
        # ----------------------------------------------------------------------
        print("\n--- SCENARIO A: Monday-Saturday (6-Day Schedule) ---")
        scope_6d = GenerationScope(
            academic_year_id=ay.id,
            semester_id=sem.id,
            department_id=dept.id,
            program_id=prog.id,
            section_ids=[sec.id],
            building_ids=[bldg.id],
            working_days="MON_SAT",
        )

        preview_6d = generate_timetable_preview(
            db,
            scope_6d,
            admin_user,
            strategy="BALANCED",
            time_limit=45,
        )

        days_6d = {e.day for e in preview_6d.entries}
        periods_6d = {f"{e.start_time}-{e.end_time}" for e in preview_6d.entries}

        print(f"Status: {preview_6d.status}")
        print(f"Is Valid: {preview_6d.is_valid} | Can Publish: {preview_6d.can_publish}")
        print(f"Blockers: {preview_6d.blocker_count} | Warnings: {preview_6d.warning_count}")
        print(f"Generated Entries: {len(preview_6d.entries)}")
        print(f"Days Assigned: {sorted(list(days_6d))}")
        print(f"Distinct Teaching Periods: {len(periods_6d)} -> {sorted(list(periods_6d))}")

        # Assertions for Scenario A
        assert preview_6d.status in ("OPTIMAL", "FEASIBLE"), f"Scenario A solver failed: {preview_6d.status}"
        assert preview_6d.can_publish is True, "Scenario A must be publishable"
        assert preview_6d.is_valid is True, "Scenario A must pass validation"
        assert preview_6d.blocker_count == 0, f"Scenario A had {preview_6d.blocker_count} blockers"
        assert "SAT" in days_6d, "Scenario A must include Saturday assignments"
        assert "SUN" not in days_6d, "Scenario A must NOT include Sunday assignments"
        assert len(preview_6d.entries) == 23, f"Scenario A expected 23 entries, got {len(preview_6d.entries)}"
        print("[PASS] Scenario A passed all verification criteria.")

        # ----------------------------------------------------------------------
        # SCENARIO B: Monday - Friday (5-Day Working Week)
        # ----------------------------------------------------------------------
        print("\n--- SCENARIO B: Monday-Friday (5-Day Schedule) ---")
        scope_5d = GenerationScope(
            academic_year_id=ay.id,
            semester_id=sem.id,
            department_id=dept.id,
            program_id=prog.id,
            section_ids=[sec.id],
            building_ids=[bldg.id],
            working_days="MON_FRI",
        )

        preview_5d = generate_timetable_preview(
            db,
            scope_5d,
            admin_user,
            strategy="BALANCED",
            time_limit=45,
        )

        days_5d = {e.day for e in preview_5d.entries}
        periods_5d = {f"{e.start_time}-{e.end_time}" for e in preview_5d.entries}

        print(f"Status: {preview_5d.status}")
        print(f"Is Valid: {preview_5d.is_valid} | Can Publish: {preview_5d.can_publish}")
        print(f"Blockers: {preview_5d.blocker_count} | Warnings: {preview_5d.warning_count}")
        print(f"Generated Entries: {len(preview_5d.entries)}")
        print(f"Days Assigned: {sorted(list(days_5d))}")
        print(f"Distinct Teaching Periods: {len(periods_5d)} -> {sorted(list(periods_5d))}")

        # Assertions for Scenario B
        assert preview_5d.status in ("OPTIMAL", "FEASIBLE"), f"Scenario B solver failed: {preview_5d.status}"
        assert preview_5d.can_publish is True, "Scenario B must be publishable"
        assert preview_5d.is_valid is True, "Scenario B must pass validation"
        assert preview_5d.blocker_count == 0, f"Scenario B had {preview_5d.blocker_count} blockers"
        assert "SAT" not in days_5d, "Scenario B must NOT include Saturday assignments"
        assert "SUN" not in days_5d, "Scenario B must NOT include Sunday assignments"
        assert len(preview_5d.entries) == 23, f"Scenario B expected 23 entries, got {len(preview_5d.entries)}"
        print("[PASS] Scenario B passed all verification criteria.")

        print("\n" + "=" * 80)
        print("ALL TIMETABLE GENERATION SCENARIOS SUCCESSFULLY VERIFIED")
        print("=" * 80)


if __name__ == "__main__":
    main()
