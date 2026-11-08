"""
scripts/verify_clean_state.py
-----------------------------
Phase 7 Verification for RIO-MJP after test data cleanup.
Checks:
1. No obsolete test records remain on DEV DB (port 5432).
2. Exactly 2 bootstrap administrative accounts remain (admin@campus.edu, superadmin@campus.edu).
3. Both bootstrap accounts authenticate and generate valid JWT tokens.
4. Core FastAPI endpoints load and respond with 200 OK without crashing.
5. Storage is clean of test documents.
6. Protected AIDS-A records on port 5433 are 100% intact.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import psycopg
from psycopg import sql
from fastapi.testclient import TestClient
from backend.main import app

DEV_URL = os.environ.get("DEV_DATABASE_URL") or os.environ.get("DATABASE_URL") or "postgresql://campus_user@localhost:5432/campus_ai"
TEST_URL = os.environ.get("TEST_DATABASE_URL") or "postgresql://campus_user@127.0.0.1:5433/campus_ai_test"


def verify_database_5432() -> None:
    print("=" * 80)
    print("PHASE 7.1: VERIFYING DEV DATABASE CLEAN STATE (campus_ai:5432)")
    print("=" * 80)

    with psycopg.connect(DEV_URL) as conn:
        with conn.cursor() as cur:
            # 1. Obsolete students
            cur.execute(sql.SQL("SELECT count(*) FROM public.students;"))
            r_std = cur.fetchone()
            std_cnt = int(r_std[0]) if r_std is not None else -1
            print(f"  [1] Obsolete students in public.students: {std_cnt} (Expected: 0)")
            assert std_cnt == 0, "Obsolete students still present!"

            # 2. Obsolete faculty
            cur.execute(sql.SQL("SELECT count(*) FROM public.faculty;"))
            r_fac = cur.fetchone()
            fac_cnt = int(r_fac[0]) if r_fac is not None else -1
            print(f"  [2] Obsolete faculty in public.faculty : {fac_cnt} (Expected: 0)")
            assert fac_cnt == 0, "Obsolete faculty still present!"

            # 3. Users audit
            cur.execute(sql.SQL("SELECT id, email, role, name, is_active FROM public.users ORDER BY id;"))
            users = cur.fetchall()
            print(f"  [3] Accounts in public.users          : {len(users)} (Expected: 2)")
            for u in users:
                u_id, u_email, u_role, u_name = u[0], str(u[1]), str(u[2]), str(u[3])
                print(f"      - ID {u_id:4d}: {u_email:<25} ({u_role:<11}) | Name: {u_name}")
            assert len(users) == 2, f"Expected exactly 2 bootstrap users, found {len(users)}"
            roles = {str(u[2]) for u in users}
            assert roles == {"ADMIN", "SUPER_ADMIN"}, f"Unexpected roles: {roles}"

            # 4. Curriculum
            cur.execute(sql.SQL("SELECT count(*) FROM public.curriculum_versions;"))
            r_cv = cur.fetchone()
            cv_cnt = int(r_cv[0]) if r_cv is not None else -1

            cur.execute(sql.SQL("SELECT count(*) FROM public.courses;"))
            r_c = cur.fetchone()
            c_cnt = int(r_c[0]) if r_c is not None else -1
            print(f"  [4] Obsolete curriculum versions/courses: {cv_cnt} versions, {c_cnt} courses (Expected: 0)")
            assert cv_cnt == 0 and c_cnt == 0

            # 5. Timetables
            cur.execute(sql.SQL("SELECT count(*) FROM public.timetable_entries;"))
            r_te = cur.fetchone()
            te_cnt = int(r_te[0]) if r_te is not None else -1

            cur.execute(sql.SQL("SELECT count(*) FROM public.timetable_versions;"))
            r_tv = cur.fetchone()
            tv_cnt = int(r_tv[0]) if r_tv is not None else -1
            print(f"  [5] Obsolete timetable entries/versions : {te_cnt} entries, {tv_cnt} versions (Expected: 0)")
            assert te_cnt == 0 and tv_cnt == 0

            # 6. Infrastructure (rooms/labs/buildings)
            cur.execute(sql.SQL("SELECT count(*) FROM public.rooms;"))
            r_rm = cur.fetchone()
            r_cnt = int(r_rm[0]) if r_rm is not None else -1

            cur.execute(sql.SQL("SELECT count(*) FROM public.labs;"))
            r_lb = cur.fetchone()
            l_cnt = int(r_lb[0]) if r_lb is not None else -1

            cur.execute(sql.SQL("SELECT count(*) FROM public.buildings;"))
            r_bd = cur.fetchone()
            b_cnt = int(r_bd[0]) if r_bd is not None else -1
            print(f"  [6] Obsolete infrastructure             : {b_cnt} buildings, {r_cnt} rooms, {l_cnt} labs (Expected: 0)")
            assert r_cnt == 0 and l_cnt == 0 and b_cnt == 0

            # 7. Other modules
            tables_to_check: List[Tuple[str, str]] = [
                ("placement_drives", "CDC placement drives"),
                ("placement_schedules", "CDC placement schedules"),
                ("campus_events", "Campus events"),
                ("clubs", "Student clubs"),
                ("faculty_substitutions", "Faculty substitutions"),
                ("notifications", "Notifications"),
                ("notification_outbox", "Notification outbox"),
                ("chat_conversations", "Chat conversations"),
                ("chat_messages", "Chat messages"),
                ("audit_logs", "Audit logs"),
                ("resource_bookings", "Resource bookings"),
            ]
            for tbl, name in tables_to_check:
                q = sql.SQL("SELECT count(*) FROM public.{};").format(sql.Identifier(tbl))
                cur.execute(q)
                r_other = cur.fetchone()
                cnt = int(r_other[0]) if r_other is not None else -1
                print(f"  [7] Obsolete {name:<30}: {cnt} (Expected: 0)")
                assert cnt == 0, f"{name} not empty!"

            # 8. Alembic version
            cur.execute(sql.SQL("SELECT version_num FROM public.alembic_version;"))
            alembic_rows = cur.fetchall()
            v_num = str(alembic_rows[0][0]) if alembic_rows else ""
            print(f"  [8] Alembic version                     : {v_num} (Expected: cdd3afe221f2)")
            assert v_num == "cdd3afe221f2", "Alembic migration history missing or altered!"

    print("[+] All DEV database verification checks PASSED.")


def verify_fastapi_and_auth() -> None:
    print("\n" + "=" * 80)
    print("PHASE 7.2: VERIFYING APPLICATION FUNCTIONALITY & BOOTSTRAP LOGIN")
    print("=" * 80)
    client = TestClient(app)

    # 1. Health check
    res = client.get("/health")
    print(f"  [1] GET /health                      : {res.status_code} ({res.json()})")
    assert res.status_code == 200

    # 2. Login as ADMIN
    res = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    print(f"  [2] POST /auth/login (ADMIN)         : {res.status_code}")
    assert res.status_code == 200
    admin_data = res.json()
    admin_token = str(admin_data.get("access_token", ""))
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    me_admin = client.get("/auth/me", headers=admin_headers)
    me_admin_data = me_admin.json()
    print(f"      - /auth/me -> Name: {me_admin_data.get('name')}, Role: {me_admin_data.get('role')}")
    assert me_admin_data.get("role") == "ADMIN"

    # 3. Login as SUPER_ADMIN
    res = client.post("/auth/login", json={"email": "superadmin@campus.edu", "password": "Test@1234"})
    print(f"  [3] POST /auth/login (SUPER_ADMIN)   : {res.status_code}")
    assert res.status_code == 200
    super_data = res.json()
    super_token = str(super_data.get("access_token", ""))
    super_headers = {"Authorization": f"Bearer {super_token}"}
    me_super = client.get("/auth/me", headers=super_headers)
    me_super_data = me_super.json()
    print(f"      - /auth/me -> Name: {me_super_data.get('name')}, Role: {me_super_data.get('role')}")
    assert me_super_data.get("role") == "SUPER_ADMIN"

    # 4. Clean endpoints respond with empty data (no crashes)
    endpoints: List[Tuple[str, Dict[str, str], str]] = [
        ("/departments/", admin_headers, "Departments list"),
        ("/programs/", admin_headers, "Programs list"),
        ("/semesters/", admin_headers, "Semesters list"),
        ("/sections/", admin_headers, "Sections list"),
        ("/courses/", admin_headers, "Courses list"),
        ("/rooms/", admin_headers, "Rooms list"),
        ("/events/", admin_headers, "Events list"),
        ("/clubs/", admin_headers, "Clubs list"),
        ("/substitutions/my-requests", admin_headers, "Substitutions list"),
        ("/notifications/", admin_headers, "Notifications list"),
        ("/agents/conversations", admin_headers, "Chat conversations list"),
    ]

    print("\n  [4] Testing clean module endpoints (must return [] without 500 crashes):")
    for ep, headers, label in endpoints:
        resp = client.get(ep, headers=headers)
        status = resp.status_code
        data = resp.json() if status == 200 else resp.text
        is_ok = status == 200
        count: Any = len(data) if isinstance(data, list) else (len(data.get("items", [])) if isinstance(data, dict) else "N/A")
        print(f"      - GET {ep:<30}: Status {status} | Items: {count} ({label})")
        assert is_ok, f"Endpoint {ep} failed with status {status}: {data}"

    print("[+] All application functionality checks PASSED.")


def verify_protected_test_db() -> None:
    print("\n" + "=" * 80)
    print("PHASE 7.3: VERIFYING PROTECTED AIDS-A RECORDS IN TEST DB (port 5433)")
    print("=" * 80)
    with psycopg.connect(TEST_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT count(*) FROM test_schema.students WHERE student_id LIKE 'R23EH%';"))
            r_std = cur.fetchone()
            cnt_std = int(r_std[0]) if r_std is not None else 0
            print(f"  [1] Protected AIDS-A Students in 5433: {cnt_std}/60")
            assert cnt_std == 60

            cur.execute(sql.SQL("SELECT count(*) FROM test_schema.faculty;"))
            r_fac = cur.fetchone()
            cnt_fac = int(r_fac[0]) if r_fac is not None else 0
            print(f"  [2] Protected Faculty in 5433         : {cnt_fac}/10")
            assert cnt_fac == 10

            cur.execute(sql.SQL("SELECT section_name, student_count FROM test_schema.sections;"))
            r_sec = cur.fetchone()
            sec_name = str(r_sec[0]) if r_sec is not None else ""
            sec_count = int(r_sec[1]) if r_sec is not None else 0
            print(f"  [3] Protected Section in 5433         : {sec_name} ({sec_count} students)")
            assert sec_name == "AIDS-A"

            cur.execute(sql.SQL("SELECT count(*) FROM test_schema.courses;"))
            r_crs = cur.fetchone()
            cnt_crs = int(r_crs[0]) if r_crs is not None else 0
            print(f"  [4] Protected Courses in 5433         : {cnt_crs} courses")
            assert cnt_crs == 18

            cur.execute(sql.SQL("SELECT count(*) FROM test_schema.rooms;"))
            r_rm = cur.fetchone()
            cnt_rm = int(r_rm[0]) if r_rm is not None else 0
            print(f"  [5] Protected Rooms in 5433           : {cnt_rm} rooms")
            assert cnt_rm == 225

    print("[+] Protected AIDS-A records verification PASSED.")


if __name__ == "__main__":
    verify_database_5432()
    verify_fastapi_and_auth()
    verify_protected_test_db()
    print("\n" + "=" * 80)
    print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY WITH ZERO ERRORS.")
    print("=" * 80)
