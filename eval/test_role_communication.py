"""
eval/test_role_communication.py
-------------------------------
Comprehensive verification script for:
1. Communication from all 3 roles: ADMIN, FACULTY, STUDENT
2. Explicit verification of HTTP 200 (or 201 for creation) for all role-specific API calls
3. Cross-role communication intactness (Admin Broadcast -> Faculty & Student; Faculty Update -> Student)
4. AI Supervisor assistant chat communication for all 3 roles
5. Strict RBAC 403/401 barrier integrity
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import datetime
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

PASS_COUNT = 0
FAIL_COUNT = 0
TEST_LOGS = []

def check(role: str, endpoint_name: str, expected_status: int, actual_status: int, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    ok = (actual_status == expected_status)
    if ok:
        PASS_COUNT += 1
        tag = "[PASS]"
    else:
        FAIL_COUNT += 1
        tag = "[FAIL]"
    msg = f"{tag:6} | {role:10} | {endpoint_name:35} | Status {actual_status} (Expected {expected_status}) | {detail}"
    print(msg)
    TEST_LOGS.append((tag, role, endpoint_name, actual_status, expected_status, detail))


def login(email: str, password: str = "Test@1234"):
    res = client.post("/auth/login", json={"email": email, "password": password})
    if res.status_code == 200:
        token = res.json().get("access_token")
        return token, res
    return None, res


def run_role_verification():
    print("=" * 105)
    print("RIO-MJP ROLE COMMUNICATION & FULL API 200-STATUS VERIFICATION")
    print(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 105)

    # =========================================================================
    # 1. ADMIN ROLE VERIFICATION (admin@campus.edu)
    # =========================================================================
    admin_token, admin_login_res = login("admin@campus.edu")
    check("ADMIN", "POST /auth/login", 200, admin_login_res.status_code, "Token issued successfully")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # /auth/me
    res = client.get("/auth/me", headers=admin_headers)
    check("ADMIN", "GET /auth/me", 200, res.status_code, f"Identity: {res.json().get('email')} (role={res.json().get('role')})")

    # Academic & Campus Directories
    endpoints_to_test = [
        ("GET /departments/", "/departments/"),
        ("GET /programs/", "/programs/"),
        ("GET /academic-years/", "/academic-years/"),
        ("GET /semesters/", "/semesters/"),
        ("GET /batches/", "/batches/"),
        ("GET /sections/", "/sections/"),
        ("GET /students/", "/students/"),
        ("GET /faculty/", "/faculty/"),
        ("GET /courses/", "/courses/"),
        ("GET /buildings/", "/buildings/"),
        ("GET /rooms/", "/rooms/"),
    ]
    for name, path in endpoints_to_test:
        r = client.get(path, headers=admin_headers)
        count = len(r.json()) if isinstance(r.json(), list) else 0
        check("ADMIN", name, 200, r.status_code, f"Returned {count} items")

    # Timetable Versions
    r = client.get("/timetable/versions", headers=admin_headers)
    check("ADMIN", "GET /timetable/versions", 200, r.status_code, f"Returned {len(r.json())} versions")

    # Resources & Bookings
    r = client.get("/resources", headers=admin_headers)
    check("ADMIN", "GET /resources", 200, r.status_code, f"Returned {len(r.json())} resources")

    r = client.get("/resources/bookings", headers=admin_headers)
    check("ADMIN", "GET /resources/bookings", 200, r.status_code, f"Returned {len(r.json())} bookings")

    avail_params = {"resource_id": 1, "date": "2026-11-15", "start_time": "10:00:00", "end_time": "11:00:00"}
    r = client.get("/resources/availability", headers=admin_headers, params=avail_params)
    check("ADMIN", "GET /resources/availability", 200, r.status_code, f"Available: {r.json().get('available')}")

    # Governance: Change Requests & Audit Logs
    r = client.get("/change-requests", headers=admin_headers)
    check("ADMIN", "GET /change-requests", 200, r.status_code, f"Returned {len(r.json())} change requests")

    r = client.get("/change-requests/pending", headers=admin_headers)
    check("ADMIN", "GET /change-requests/pending", 200, r.status_code, f"Returned {len(r.json())} pending requests")

    r = client.get("/admin/audit-logs", headers=admin_headers)
    check("ADMIN", "GET /admin/audit-logs", 200, r.status_code, f"Returned {len(r.json().get('items', r.json()))} audit log records")

    # Notifications
    r = client.get("/notifications", headers=admin_headers)
    check("ADMIN", "GET /notifications", 200, r.status_code, f"Feed returned {len(r.json())} items")

    r = client.get("/notifications/unread-count", headers=admin_headers)
    check("ADMIN", "GET /notifications/unread-count", 200, r.status_code, f"Unread count: {r.json().get('unread_count')}")

    # AI Chat
    r = client.post("/agents/chat", headers=admin_headers, json={"message": "Show academic departments"})
    check("ADMIN", "POST /agents/chat", 200, r.status_code, f"Supervisor reply: '{r.json().get('reply')[:45]}...'")

    r = client.post("/chat", headers=admin_headers, json={"message": "Help with campus resources"})
    check("ADMIN", "POST /chat (alias)", 200, r.status_code, f"Supervisor reply: '{r.json().get('reply')[:45]}...'")

    # =========================================================================
    # 2. FACULTY ROLE VERIFICATION (allison.hill@campus.edu)
    # =========================================================================
    print("-" * 105)
    fac_token, fac_login_res = login("allison.hill@campus.edu")
    check("FACULTY", "POST /auth/login", 200, fac_login_res.status_code, "Token issued successfully")
    fac_headers = {"Authorization": f"Bearer {fac_token}"}

    # /auth/me
    res = client.get("/auth/me", headers=fac_headers)
    check("FACULTY", "GET /auth/me", 200, res.status_code, f"Identity: {res.json().get('email')} (role={res.json().get('role')})")

    # Timetable
    r = client.get("/faculty/my-timetable", headers=fac_headers)
    check("FACULTY", "GET /faculty/my-timetable", 200, r.status_code, f"Teaching hours: {r.json().get('total_teaching_hours')}, entries: {len(r.json().get('entries', []))}")

    # Resources
    r = client.get("/resources", headers=fac_headers)
    check("FACULTY", "GET /resources", 200, r.status_code, f"Returned {len(r.json())} resources")

    r = client.get("/resources/bookings", headers=fac_headers)
    check("FACULTY", "GET /resources/bookings", 200, r.status_code, f"Returned {len(r.json())} bookings")

    r = client.get("/resources/availability", headers=fac_headers, params=avail_params)
    check("FACULTY", "GET /resources/availability", 200, r.status_code, f"Available: {r.json().get('available')}")

    # Change Requests
    r = client.get("/change-requests", headers=fac_headers)
    check("FACULTY", "GET /change-requests", 200, r.status_code, f"Returned {len(r.json())} own change requests")

    # Notifications
    r = client.get("/notifications", headers=fac_headers)
    check("FACULTY", "GET /notifications", 200, r.status_code, f"Feed returned {len(r.json())} items")

    r = client.get("/notifications/unread-count", headers=fac_headers)
    check("FACULTY", "GET /notifications/unread-count", 200, r.status_code, f"Unread count: {r.json().get('unread_count')}")

    # AI Chat
    r = client.post("/agents/chat", headers=fac_headers, json={"message": "What is my assigned teaching schedule?"})
    check("FACULTY", "POST /agents/chat", 200, r.status_code, f"Supervisor reply: '{r.json().get('reply')[:45]}...'")

    r = client.post("/chat", headers=fac_headers, json={"message": "Are there computer science courses available?"})
    check("FACULTY", "POST /chat (alias)", 200, r.status_code, f"Supervisor reply: '{r.json().get('reply')[:45]}...'")

    # =========================================================================
    # 3. STUDENT ROLE VERIFICATION (monica.herrera@campus.edu)
    # =========================================================================
    print("-" * 105)
    stu_token, stu_login_res = login("monica.herrera@campus.edu")
    check("STUDENT", "POST /auth/login", 200, stu_login_res.status_code, "Token issued successfully")
    stu_headers = {"Authorization": f"Bearer {stu_token}"}

    # /auth/me
    res = client.get("/auth/me", headers=stu_headers)
    check("STUDENT", "GET /auth/me", 200, res.status_code, f"Identity: {res.json().get('email')} (role={res.json().get('role')})")

    # Timetable
    r = client.get("/student/my-timetable", headers=stu_headers)
    check("STUDENT", "GET /student/my-timetable", 200, r.status_code, f"Class hours: {r.json().get('total_class_hours')}, entries: {len(r.json().get('entries', []))}")

    r = client.get("/students/my-timetable", headers=stu_headers)
    check("STUDENT", "GET /students/my-timetable (alias)", 200, r.status_code, f"Class hours: {r.json().get('total_class_hours')}")

    # Resources
    r = client.get("/resources", headers=stu_headers)
    check("STUDENT", "GET /resources", 200, r.status_code, f"Returned {len(r.json())} resources")

    r = client.get("/resources/bookings", headers=stu_headers)
    check("STUDENT", "GET /resources/bookings", 200, r.status_code, f"Returned {len(r.json())} bookings")

    r = client.get("/resources/availability", headers=stu_headers, params=avail_params)
    check("STUDENT", "GET /resources/availability", 200, r.status_code, f"Available: {r.json().get('available')}")

    # Change Requests
    r = client.get("/change-requests", headers=stu_headers)
    check("STUDENT", "GET /change-requests", 200, r.status_code, f"Returned {len(r.json())} own change requests")

    # Notifications
    r = client.get("/notifications", headers=stu_headers)
    check("STUDENT", "GET /notifications", 200, r.status_code, f"Feed returned {len(r.json())} items")

    r = client.get("/notifications/unread-count", headers=stu_headers)
    check("STUDENT", "GET /notifications/unread-count", 200, r.status_code, f"Unread count: {r.json().get('unread_count')}")

    # AI Chat
    r = client.post("/agents/chat", headers=stu_headers, json={"message": "Where is room MB-100 located?"})
    check("STUDENT", "POST /agents/chat", 200, r.status_code, f"Supervisor reply: '{r.json().get('reply')[:45]}...'")

    r = client.post("/chat", headers=stu_headers, json={"message": "Tell me about course EE614"})
    check("STUDENT", "POST /chat (alias)", 200, r.status_code, f"Supervisor reply: '{r.json().get('reply')[:45]}...'")

    # =========================================================================
    # 4. CROSS-ROLE COMMUNICATION INTACTNESS
    # =========================================================================
    print("-" * 105)
    print("TESTING CROSS-ROLE COMMUNICATION CHANNELS")
    print("-" * 105)

    # 4A. Admin broadcasts campus announcement -> Verified in Faculty & Student notifications
    announcement_title = f"Test Campus Announcement {datetime.datetime.now().strftime('%H%M%S')}"
    broadcast_payload = {
        "title": announcement_title,
        "message": "Campus-wide advisory regarding mid-term scheduling and library hours.",
        "target_role": "ALL"
    }
    r_broadcast = client.post("/notifications/admin/broadcast", headers=admin_headers, json=broadcast_payload)
    check("ADMIN->ALL", "POST /notifications/admin/broadcast", 200, r_broadcast.status_code, f"Recipients notified: {r_broadcast.json().get('recipients_count')}")

    # Verify Faculty received the broadcast
    r_fac_feed = client.get("/notifications", headers=fac_headers)
    fac_received = any(n.get("title") == announcement_title for n in r_fac_feed.json())
    check("FACULTY", "Verify Admin Broadcast Received", 200, 200 if fac_received else 500, f"Found title '{announcement_title}': {fac_received}")

    # Verify Student received the broadcast
    r_stu_feed = client.get("/notifications", headers=stu_headers)
    stu_received = any(n.get("title") == announcement_title for n in r_stu_feed.json())
    check("STUDENT", "Verify Admin Broadcast Received", 200, 200 if stu_received else 500, f"Found title '{announcement_title}': {stu_received}")

    # 4B. Faculty sends class update to Section 1 -> Student (Monica) is in Section 1 and receives it
    class_update_title = f"Class Room Update {datetime.datetime.now().strftime('%H%M%S')}"
    class_update_payload = {
        "course_id": 5,
        "section_id": 1,
        "update_type": "ROOM_CHANGE",
        "title": class_update_title,
        "message": "Today's lecture is moved to Room MB-100."
    }
    r_fac_update = client.post("/notifications/faculty/class-update", headers=fac_headers, json=class_update_payload)
    check("FACULTY->STU", "POST /notifications/faculty/class-update", 200, r_fac_update.status_code, f"Students notified: {r_fac_update.json().get('students_notified')}")

    # Verify Student received faculty class update (title is prefixed with [COURSE_CODE])
    r_stu_feed = client.get("/notifications", headers=stu_headers)
    stu_update_received = any(class_update_title in (n.get("title") or "") for n in r_stu_feed.json())
    notification_id_to_read = None
    for n in r_stu_feed.json():
        if class_update_title in (n.get("title") or ""):
            notification_id_to_read = n.get("id")
            break
    check("STUDENT", "Verify Faculty Update Received", 200, 200 if stu_update_received else 500, f"Found title '{class_update_title}': {stu_update_received}")

    # 4C. Student reads notification -> POST /notifications/{id}/read
    if notification_id_to_read:
        r_read = client.post(f"/notifications/{notification_id_to_read}/read", headers=stu_headers)
        check("STUDENT", f"POST /notifications/{notification_id_to_read}/read", 200, r_read.status_code, f"is_read: {r_read.json().get('is_read')}")

    # 4D. Student marks all as read
    r_mark_all = client.post("/notifications/mark-all-read", headers=stu_headers)
    check("STUDENT", "POST /notifications/mark-all-read", 200, r_mark_all.status_code, f"Marked: {r_mark_all.json().get('marked_count')}")

    # =========================================================================
    # 5. STRICT RBAC ACCESS CONTROL INTEGRITY
    # =========================================================================
    print("-" * 105)
    print("TESTING STRICT ROLE AUTHORIZATION BARRIERS")
    print("-" * 105)
    # Student blocked from admin broadcast (403)
    r = client.post("/notifications/admin/broadcast", headers=stu_headers, json=broadcast_payload)
    check("STUDENT", "Forbidden Admin Broadcast", 403, r.status_code, "Enforced 403 Forbidden")

    # Student blocked from pending change requests (403)
    r = client.get("/change-requests/pending", headers=stu_headers)
    check("STUDENT", "Forbidden Pending Change Requests", 403, r.status_code, "Enforced 403 Forbidden")

    # Student blocked from audit logs (403)
    r = client.get("/admin/audit-logs", headers=stu_headers)
    check("STUDENT", "Forbidden Audit Logs", 403, r.status_code, "Enforced 403 Forbidden")

    # Faculty blocked from admin broadcast (403)
    r = client.post("/notifications/admin/broadcast", headers=fac_headers, json=broadcast_payload)
    check("FACULTY", "Forbidden Admin Broadcast", 403, r.status_code, "Enforced 403 Forbidden")

    # Faculty blocked from audit logs (403)
    r = client.get("/admin/audit-logs", headers=fac_headers)
    check("FACULTY", "Forbidden Audit Logs", 403, r.status_code, "Enforced 403 Forbidden")

    # Unauthenticated blocked (401)
    r = client.get("/auth/me")
    check("ANONYMOUS", "Unauthorized /auth/me", 401, r.status_code, "Enforced 401 Unauthorized")

    r = client.get("/departments/")
    check("ANONYMOUS", "Unauthorized /departments/", 401, r.status_code, "Enforced 401 Unauthorized")

    print("=" * 105)
    print(f"VERIFICATION RESULTS: {PASS_COUNT} PASSED, {FAIL_COUNT} FAILED")
    print("=" * 105)

    if FAIL_COUNT > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_role_verification()
