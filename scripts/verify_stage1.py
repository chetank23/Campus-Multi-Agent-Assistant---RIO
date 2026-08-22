"""Verification script — Stage 1. Run with: venv\\Scripts\\python scripts\\verify_stage1.py"""
import io
import os
import sys

# Force UTF-8 output on Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env")
engine = create_engine(os.environ["DATABASE_URL"])

PASS = "[OK]"
FAIL = "[FAIL]"

with engine.connect() as conn:
    # ── Tables ────────────────────────────────────────────────────
    tables = conn.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    ).fetchall()
    print(f"\n{'='*55}")
    print(f"  TABLES IN campus_ai.public  ({len(tables)} total)")
    print(f"{'='*55}")
    for t in tables:
        print(f"  {PASS}  {t[0]}")

    expected_tables = 26  # 20 entity tables + alembic_version + others Alembic adds
    status = PASS if len(tables) >= 20 else FAIL
    print(f"\n  Table count >= 20: {status}")

    # ── Timetable composite indexes ───────────────────────────────
    indexes = conn.execute(
        text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE tablename='timetable' AND schemaname='public' ORDER BY indexname"
        )
    ).fetchall()
    print(f"\n{'='*55}")
    print(f"  INDEXES ON timetable  ({len(indexes)} found)")
    print(f"{'='*55}")
    for idx in indexes:
        print(f"  {PASS}  {idx[0]}")
        print(f"         {idx[1]}")

    expected_idx = {"ix_timetable_faculty_slot", "ix_timetable_room_slot", "ix_timetable_section_slot"}
    found_idx = {i[0] for i in indexes}
    missing = expected_idx - found_idx
    if missing:
        print(f"\n  {FAIL} Missing indexes: {missing}")
    else:
        print(f"\n  All 3 composite indexes present: {PASS}")

    # ── Foreign keys ──────────────────────────────────────────────
    fk_count = conn.execute(
        text(
            "SELECT COUNT(constraint_name) FROM information_schema.table_constraints "
            "WHERE constraint_type='FOREIGN KEY' AND table_schema='public'"
        )
    ).scalar()
    print(f"\n{'='*55}")
    print(f"  FOREIGN KEYS: {fk_count} total")
    print(f"{'='*55}")
    fk_ok = PASS if fk_count > 0 else FAIL
    print(f"  FK count > 0: {fk_ok}")

    # ── CHECK constraints ─────────────────────────────────────────
    ck_count = conn.execute(
        text(
            "SELECT COUNT(constraint_name) FROM information_schema.table_constraints "
            "WHERE constraint_type='CHECK' AND table_schema='public'"
        )
    ).scalar()
    print(f"\n  CHECK constraints: {ck_count}  {PASS if ck_count > 0 else FAIL}")

    # ── Alembic version ───────────────────────────────────────────
    ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    print(f"\n{'='*55}")
    print(f"  ALEMBIC REVISION: {ver}")
    print(f"{'='*55}")

    print(f"\n  Stage 1 database verification: {PASS}\n")
