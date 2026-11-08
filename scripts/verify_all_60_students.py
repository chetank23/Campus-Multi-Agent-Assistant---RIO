#!/usr/bin/env python3
"""
scripts/verify_all_60_students.py
---------------------------------
Comprehensive verification of all 60 AIDS-A student accounts (R23EH001..R23EH060):
- Login via /auth/login
- Identity mapping (email -> SRN)
- Role verification (STUDENT)
- Section association (AIDS-A)
- Timetable access (/student/my-timetable)
- Cross-student data isolation & RBAC protection
"""

import sys
import os
from pathlib import Path
from typing import Dict, Any, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Ensure isolated test database target
target_url = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://campus_user:@127.0.0.1:5433/campus_ai_test?options=-csearch_path%3Dtest_schema",
)
os.environ["DATABASE_URL"] = target_url
os.environ["TEST_DATABASE_URL"] = target_url

from fastapi.testclient import TestClient
from backend.main import app
from scripts.import_aids_a_dataset import DEFAULT_TEST_PASSWORD, get_unique_account_password

client = TestClient(app)


def verify_all_60_students() -> Dict[str, Any]:
    print("=" * 80)
    print("VERIFYING ALL 60 AIDS-A STUDENT ACCOUNTS (R23EH001 - R23EH060)")
    print(f"Target URL: {target_url}")
    print(f"Password  : {DEFAULT_TEST_PASSWORD}")
    print("=" * 80)

    results: List[Dict[str, Any]] = []
    tokens: Dict[str, str] = {}
    student_ids: Dict[str, int] = {}
    passed_count = 0
    failed_count = 0

    print(f"{'SRN':<10} | {'Email':<25} | {'Role':<8} | {'Section':<8} | {'TT Status':<10} | {'Entries':<8} | {'Status':<6}")
    print("-" * 84)

    for idx in range(1, 61):
        srn = f"R23EH{idx:03d}"
        email = f"{srn.lower()}@rio-mjp.test"
        stu_pwd = get_unique_account_password("STUDENT", srn)

        # 1. Login (using unique account password with fallback)
        login_res = client.post("/auth/login", json={"email": email, "password": stu_pwd})
        if login_res.status_code != 200:
            login_res = client.post("/auth/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
        if login_res.status_code != 200:
            print(f"{srn:<10} | {email:<25} | LOGIN FAILED ({login_res.status_code})")
            failed_count += 1
            results.append({"srn": srn, "email": email, "passed": False, "error": f"Login failed: {login_res.text}"})
            continue

        token = login_res.json()["access_token"]
        tokens[srn] = token
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Profile (/auth/me)
        me_res = client.get("/auth/me", headers=headers)
        if me_res.status_code != 200:
            failed_count += 1
            results.append({"srn": srn, "email": email, "passed": False, "error": "Get /auth/me failed"})
            continue
        me_data = me_res.json()
        role = me_data.get("role")

        # 3. Timetable (/student/my-timetable)
        tt_res = client.get("/student/my-timetable", headers=headers)
        if tt_res.status_code != 200:
            failed_count += 1
            results.append({"srn": srn, "email": email, "passed": False, "error": f"Timetable failed: {tt_res.text}"})
            continue
        tt_data = tt_res.json()
        section = tt_data.get("section_name")
        reported_code = tt_data.get("student_code")
        student_pk = tt_data.get("student_id")
        if student_pk:
            student_ids[srn] = student_pk
        entries_cnt = len(tt_data.get("entries", []))

        # Checks
        is_ok = (
            role == "STUDENT"
            and reported_code == srn
            and section == "AIDS-A"
            and entries_cnt >= 0
        )

        if is_ok:
            passed_count += 1
            status_str = "PASS"
        else:
            failed_count += 1
            status_str = "FAIL"

        print(f"{srn:<10} | {email:<25} | {role:<8} | {section:<8} | 200 OK     | {entries_cnt:<8} | {status_str:<6}")
        results.append({
            "srn": srn,
            "email": email,
            "role": role,
            "section": section,
            "entries_count": entries_cnt,
            "passed": is_ok,
        })

    # 4. Cross-Student Privacy & Isolation Verification
    print("\n" + "=" * 80)
    print("VERIFYING CROSS-STUDENT PRIVACY & DATA ISOLATION (ZERO LEAKAGE)")
    print("=" * 80)
    isolation_passed = True
    isolation_checks = []

    # Test 4a: Student 1 attempts to fetch Student 2's record via /students/{id}
    if "R23EH001" in tokens and "R23EH002" in student_ids:
        s1_headers = {"Authorization": f"Bearer {tokens['R23EH001']}"}
        s2_pk = student_ids["R23EH002"]
        s1_to_s2 = client.get(f"/students/{s2_pk}", headers=s1_headers)
        check_pass = s1_to_s2.status_code == 403
        isolation_checks.append({
            "test": "R23EH001 access /students/{R23EH002_id}",
            "expected_status": 403,
            "actual_status": s1_to_s2.status_code,
            "passed": check_pass,
        })
        print(f"[*] R23EH001 accessing /students/{s2_pk} (R23EH002): {s1_to_s2.status_code} ({'PASS' if check_pass else 'FAIL'})")
        if not check_pass:
            isolation_passed = False

    # Test 4b: Student 2 attempts to fetch Student 60's record
    if "R23EH002" in tokens and "R23EH060" in student_ids:
        s2_headers = {"Authorization": f"Bearer {tokens['R23EH002']}"}
        s60_pk = student_ids["R23EH060"]
        s2_to_s60 = client.get(f"/students/{s60_pk}", headers=s2_headers)
        check_pass = s2_to_s60.status_code == 403
        isolation_checks.append({
            "test": "R23EH002 access /students/{R23EH060_id}",
            "expected_status": 403,
            "actual_status": s2_to_s60.status_code,
            "passed": check_pass,
        })
        print(f"[*] R23EH002 accessing /students/{s60_pk} (R23EH060): {s2_to_s60.status_code} ({'PASS' if check_pass else 'FAIL'})")
        if not check_pass:
            isolation_passed = False

    # Test 4c: Student 1 calls /students/ (plural list) -> must only return own record
    if "R23EH001" in tokens:
        s1_headers = {"Authorization": f"Bearer {tokens['R23EH001']}"}
        list_res = client.get("/students/", headers=s1_headers)
        list_items = list_res.json() if list_res.status_code == 200 else []
        check_pass = (list_res.status_code == 200 and len(list_items) == 1 and list_items[0].get("student_id") == "R23EH001")
        isolation_checks.append({
            "test": "R23EH001 list /students/ (only own record)",
            "expected_count": 1,
            "actual_count": len(list_items),
            "passed": check_pass,
        })
        print(f"[*] R23EH001 listing /students/: returned {len(list_items)} records ({'PASS' if check_pass else 'FAIL'})")
        if not check_pass:
            isolation_passed = False

    # Test 4d: Student 1 attempts to access /admin/audit-logs
    if "R23EH001" in tokens:
        s1_headers = {"Authorization": f"Bearer {tokens['R23EH001']}"}
        admin_res = client.get("/admin/audit-logs", headers=s1_headers)
        check_pass = admin_res.status_code == 403
        isolation_checks.append({
            "test": "R23EH001 access /admin/audit-logs",
            "expected_status": 403,
            "actual_status": admin_res.status_code,
            "passed": check_pass,
        })
        print(f"[*] R23EH001 accessing /admin/audit-logs: {admin_res.status_code} ({'PASS' if check_pass else 'FAIL'})")
        if not check_pass:
            isolation_passed = False

    print("-" * 80)
    print(f"SUMMARY: {passed_count}/60 Student Accounts Verified | Privacy Isolation: {'PASS' if isolation_passed else 'FAIL'}")
    print("=" * 80)

    return {
        "total_tested": len(results),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "isolation_passed": isolation_passed,
        "results": results,
        "isolation_checks": isolation_checks,
    }


if __name__ == "__main__":
    summary = verify_all_60_students()
    if summary["failed_count"] > 0 or not summary["isolation_passed"]:
        sys.exit(1)
    sys.exit(0)
