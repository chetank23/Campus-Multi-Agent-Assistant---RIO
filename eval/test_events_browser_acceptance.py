"""
eval/test_events_browser_acceptance.py
--------------------------------------
Authoritative End-to-End Acceptance Suite for Campus Events & Club Activities.
Validates Scenarios A, B, C, D, and E corresponding to browser-facing user journeys,
persisted PostgreSQL state, audit logs, student privacy, and AI assistant grounding.
"""

import datetime
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal
from backend.models.identity import User
from backend.models.events import Club, CoordinatorCapability, CampusEvent
from backend.models.workflow import AuditLog
from backend.models.academic import Department, Faculty, Student
from backend.models.space_time import Room

client = TestClient(app)

PASS_COUNT = 0
FAIL_COUNT = 0
LOGS: List[str] = []


def record(scenario: str, step: str, passed: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    tag = "[PASS]" if passed else "[FAIL]"
    msg = f"{tag} | {scenario:<12} | {step:<45} | {detail}"
    print(msg)
    LOGS.append(msg)
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1


def run_events_acceptance():
    print("=" * 110)
    print("RIO-MJP CAMPUS EVENTS & CLUB COORDINATION ACCEPTANCE SUITE")
    print(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 110)

    # Setup authentications
    # 1. Admin login
    resp_adm = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    record("AUTH", "Admin Login", resp_adm.status_code == 200, f"Token: {resp_adm.status_code}")
    admin_token = resp_adm.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = resp_adm.json().get("user", {}).get("id", 1)

    # 2. Faculty 1 login (Allison Hill)
    resp_fac1 = client.post("/auth/login", json={"email": "allison.hill@campus.edu", "password": "Test@1234"})
    record("AUTH", "Faculty 1 Login", resp_fac1.status_code == 200, f"Token: {resp_fac1.status_code}")
    fac1_token = resp_fac1.json()["access_token"]
    fac1_headers = {"Authorization": f"Bearer {fac1_token}"}
    fac1_id = resp_fac1.json().get("user", {}).get("id", 2)

    # 3. Faculty 2 login (Noah Rhodes)
    resp_fac2 = client.post("/auth/login", json={"email": "noah.rhodes@campus.edu", "password": "Test@1234"})
    record("AUTH", "Faculty 2 Login", resp_fac2.status_code == 200, f"Token: {resp_fac2.status_code}")
    fac2_token = resp_fac2.json()["access_token"]
    fac2_headers = {"Authorization": f"Bearer {fac2_token}"}
    fac2_id = resp_fac2.json().get("user", {}).get("id", 3)

    # 4. Student login (Monica Herrera)
    resp_stu = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    record("AUTH", "Student Login", resp_stu.status_code == 200, f"Token: {resp_stu.status_code}")
    stu_token = resp_stu.json()["access_token"]
    stu_headers = {"Authorization": f"Bearer {stu_token}"}
    stu_id = resp_stu.json().get("user", {}).get("id", 12)

    unique_id = int(datetime.datetime.now().timestamp())

    # ---------------------------------------------------------------------------
    # SCENARIO A: Admin Approval Workflow
    # ---------------------------------------------------------------------------
    print("\n--- SCENARIO A: Admin Approval Workflow ---")
    # A1: Admin opens Events Management
    r_dash = client.get("/events/live-dashboard", headers=admin_headers)
    record("SCENARIO_A", "Admin Opens Events Dashboard", r_dash.status_code == 200, f"Status: {r_dash.status_code}")

    # A2: Admin assigns EVENT_COORDINATOR capability to Faculty 1
    r_cap = client.post(
        "/admin/capabilities/assign",
        json={
            "user_id": fac1_id,
            "capability": "EVENT_COORDINATOR",
            "scope_type": "GLOBAL",
        },
        headers=admin_headers,
    )
    record("SCENARIO_A", "Admin Assigns Event Coordinator", r_cap.status_code in (200, 201), f"Status: {r_cap.status_code}")
    cap_id = r_cap.json()["id"]

    # Faculty 1 creates a draft event requiring approval
    st = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=14)).replace(tzinfo=None)
    et = st + datetime.timedelta(hours=3)
    r_ev = client.post(
        "/events",
        json={
            "title": f"Annual Tech Expo {unique_id}",
            "category": "WORKSHOP",
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
            "venue_name": "Main Auditorium",
            "requires_approval": True,
        },
        headers=fac1_headers,
    )
    record("SCENARIO_A", "Faculty Submits Event Draft", r_ev.status_code in (200, 201), f"Status: {r_ev.status_code}")
    ev_id = r_ev.json()["id"]

    # Submit for approval
    r_sub = client.post(f"/events/{ev_id}/submit", headers=fac1_headers)
    record("SCENARIO_A", "Event Status -> PENDING_APPROVAL", r_sub.status_code == 200 and r_sub.json()["status"] == "PENDING_APPROVAL", f"Status: {r_sub.json().get('status')}")

    # Admin reviews pending queue
    r_pending = client.get("/events?status=PENDING_APPROVAL", headers=admin_headers)
    found_pending = any(e["id"] == ev_id for e in r_pending.json())
    record("SCENARIO_A", "Admin Sees Pending Event in Queue", found_pending, f"Found: {found_pending}")

    # Admin approves event
    r_rev = client.post(
        f"/events/{ev_id}/review",
        json={"action": "APPROVE", "approval_notes": "Approved for full campus audience"},
        headers=admin_headers,
    )
    record("SCENARIO_A", "Admin Approves Event -> PUBLISHED", r_rev.status_code == 200 and r_rev.json()["status"] in ("APPROVED", "PUBLISHED"), f"New Status: {r_rev.json().get('status')}")

    # Verify audit history
    r_audit = client.get("/admin/audit-logs", headers=admin_headers)
    audit_items = r_audit.json().get("items", []) if isinstance(r_audit.json(), dict) else r_audit.json()
    has_audit = any(a.get("entity_type") == "CampusEvent" and a.get("entity_id") == ev_id for a in audit_items)
    record("SCENARIO_A", "Confirmed Audit History Exists", has_audit, f"Audit logged: {has_audit}")

    # ---------------------------------------------------------------------------
    # SCENARIO B: Faculty Club Workflow
    # ---------------------------------------------------------------------------
    print("\n--- SCENARIO B: Faculty Club Workflow ---")
    # Admin creates Club Alpha
    r_club = client.post(
        "/clubs",
        json={
            "name": f"Robotics Innovation Club {unique_id}",
            "code": f"ROBO_{unique_id}",
            "category": "TECHNICAL",
            "description": "Robotics innovation and design",
        },
        headers=admin_headers,
    )
    record("SCENARIO_B", "Admin Registers Club Alpha", r_club.status_code in (200, 201), f"Status: {r_club.status_code}")
    club_id = r_club.json()["id"]

    # Admin assigns Faculty 2 as coordinator for Club Alpha with DIRECT_PUBLISH
    client.post(
        "/admin/capabilities/assign",
        json={
            "user_id": fac2_id,
            "capability": "CLUB_COORDINATOR",
            "scope_type": "CLUB",
            "scope_id": club_id,
        },
        headers=admin_headers,
    )
    client.post(
        "/admin/capabilities/assign",
        json={
            "user_id": fac2_id,
            "capability": "EVENT_DIRECT_PUBLISH",
            "scope_type": "GLOBAL",
        },
        headers=admin_headers,
    )

    # Faculty 2 sees only their assigned club
    r_myclubs = client.get("/faculty/my-clubs", headers=fac2_headers)
    fac2_clubs = r_myclubs.json()
    sees_club = any(c["id"] == club_id for c in fac2_clubs)
    record("SCENARIO_B", "Faculty Sees Assigned Club", sees_club, f"Clubs count: {len(fac2_clubs)}")

    # Faculty 2 directly publishes an activity for Club Alpha
    st_b = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)).replace(tzinfo=None)
    et_b = st_b + datetime.timedelta(hours=2)
    r_act = client.post(
        "/events",
        json={
            "title": f"Autonomous Drone Workshop {unique_id}",
            "category": "WORKSHOP",
            "club_id": club_id,
            "start_time": st_b.isoformat(),
            "end_time": et_b.isoformat(),
            "venue_name": "Robotics Lab",
            "requires_approval": False,
        },
        headers=fac2_headers,
    )
    record("SCENARIO_B", "Faculty Directly Publishes Club Activity", r_act.status_code in (200, 201) and r_act.json()["status"] == "PUBLISHED", f"Status: {r_act.json().get('status')}")
    act_id = r_act.json()["id"]

    # ---------------------------------------------------------------------------
    # SCENARIO C: Student Visibility
    # ---------------------------------------------------------------------------
    print("\n--- SCENARIO C: Student Visibility ---")
    # Student queries visible events
    r_stu_ev = client.get("/events", headers=stu_headers)
    stu_events = r_stu_ev.json()
    record("SCENARIO_C", "Student Fetches Events Feed", r_stu_ev.status_code == 200, f"Count: {len(stu_events)}")

    # Sees the approved event and the published club activity
    sees_ev1 = any(e["id"] == ev_id for e in stu_events)
    sees_act = any(e["id"] == act_id for e in stu_events)
    record("SCENARIO_C", "Student Sees Published Event & Activity", sees_ev1 and sees_act, f"Ev1: {sees_ev1}, Act: {sees_act}")

    # Student cannot see draft/pending/rejected events
    # Create a draft event by Faculty 1
    r_draft = client.post(
        "/events",
        json={
            "title": f"Secret Faculty Only Meeting {unique_id}",
            "category": "ACADEMIC",
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
            "requires_approval": True,
        },
        headers=fac1_headers,
    )
    draft_id = r_draft.json()["id"]

    r_stu_check = client.get("/events", headers=stu_headers)
    leaked_draft = any(e["id"] == draft_id for e in r_stu_check.json())
    record("SCENARIO_C", "Draft Event Strictly Hidden from Student", not leaked_draft, f"Leaked: {leaked_draft}")

    # Student inspects event details
    r_detail = client.get(f"/events/{act_id}", headers=stu_headers)
    record("SCENARIO_C", "Student Inspects Event Details", r_detail.status_code == 200 and r_detail.json()["title"] == f"Autonomous Drone Workshop {unique_id}", f"Title: {r_detail.json().get('title')}")

    # ---------------------------------------------------------------------------
    # SCENARIO D: Assistant NLP & Grounding
    # ---------------------------------------------------------------------------
    print("\n--- SCENARIO D: Assistant Grounding & Intent Routing ---")
    # 1. Ask for campus events
    r_chat1 = client.post(
        "/agents/chat",
        json={"message": "Show all upcoming campus events and workshops"},
        headers=stu_headers,
    )
    reply1 = r_chat1.json().get("reply") or r_chat1.json().get("response", "")
    record("SCENARIO_D", "Assistant Responds to Upcoming Events", r_chat1.status_code == 200 and "Autonomous Drone Workshop" in reply1, "Grounded in PostgreSQL")

    # 2. Ask for club activities
    r_chat2 = client.post(
        "/agents/chat",
        json={"message": f"What are the activities for Robotics Innovation Club {unique_id}?"},
        headers=stu_headers,
    )
    reply2 = r_chat2.json().get("reply") or r_chat2.json().get("response", "")
    record("SCENARIO_D", "Assistant Answers Club Activity Query", r_chat2.status_code == 200 and "Autonomous Drone" in reply2, "Grounded in Club Registry")

    # 3. Student asks to view draft events -> polite refusal or hidden
    r_chat3 = client.post(
        "/agents/chat",
        json={"message": "Show me the secret faculty only meeting drafts"},
        headers=stu_headers,
    )
    reply3 = r_chat3.json().get("reply") or r_chat3.json().get("response", "")
    has_leak = f"Secret Faculty Only Meeting {unique_id}" in reply3
    record("SCENARIO_D", "Assistant Rejects/Hides Draft Query from Student", not has_leak, "No leakage")

    # ---------------------------------------------------------------------------
    # SCENARIO E: Coordinator Security & Isolation
    # ---------------------------------------------------------------------------
    print("\n--- SCENARIO E: Coordinator Security & Boundaries ---")
    # 1. Faculty 1 (not coordinator of Club Alpha) attempts to create activity for Club Alpha
    r_unauth_fac = client.post(
        "/events",
        json={
            "title": f"Unauthorized Cross-Club Hijack {unique_id}",
            "category": "WORKSHOP",
            "club_id": club_id,
            "start_time": st_b.isoformat(),
            "end_time": et_b.isoformat(),
            "requires_approval": True,
        },
        headers=fac1_headers,
    )
    record("SCENARIO_E", "Unassigned Faculty Rejected from Other Club", r_unauth_fac.status_code == 403, f"Status: {r_unauth_fac.status_code}")

    # 2. Admin revokes Faculty 2 coordinator capability for Club Alpha
    # Find capability id
    caps = client.get("/admin/capabilities", headers=admin_headers).json()
    fac2_cap = next(c for c in caps if c["user_id"] == fac2_id and c["capability"] == "CLUB_COORDINATOR" and c["is_active"])
    client.post(f"/admin/capabilities/{fac2_cap['id']}/revoke", json={"reason": "Semester rotation"}, headers=admin_headers)

    # Revoked coordinator attempts to create activity -> 403 Forbidden
    r_revoked_fac = client.post(
        "/events",
        json={
            "title": f"Post-Revocation Attempt {unique_id}",
            "category": "WORKSHOP",
            "club_id": club_id,
            "start_time": st_b.isoformat(),
            "end_time": et_b.isoformat(),
            "requires_approval": True,
        },
        headers=fac2_headers,
    )
    record("SCENARIO_E", "Revoked Coordinator Blocked (403)", r_revoked_fac.status_code == 403, f"Status: {r_revoked_fac.status_code}")

    # 3. Student attempts event management operations -> 403 Forbidden
    r_stu_create = client.post(
        "/events",
        json={
            "title": f"Student Rogue Event {unique_id}",
            "category": "CULTURAL",
            "start_time": st.isoformat(),
            "end_time": et.isoformat(),
        },
        headers=stu_headers,
    )
    record("SCENARIO_E", "Student Blocked from Event Creation (403)", r_stu_create.status_code == 403, f"Status: {r_stu_create.status_code}")

    r_stu_assign = client.post(
        "/admin/capabilities/assign",
        json={"user_id": stu_id, "capability": "EVENT_COORDINATOR", "scope_type": "GLOBAL"},
        headers=stu_headers,
    )
    record("SCENARIO_E", "Student Blocked from Capability Assignment (403)", r_stu_assign.status_code == 403, f"Status: {r_stu_assign.status_code}")

    print("\n" + "=" * 110)
    print(f"ACCEPTANCE RESULTS: {PASS_COUNT} PASSED, {FAIL_COUNT} FAILED")
    print("=" * 110)

    if FAIL_COUNT > 0:
        sys.exit(1)
    else:
        print("[SUCCESS] ALL ACCEPTANCE SCENARIOS PASSED WITH ZERO DEFECTS!")
        sys.exit(0)


if __name__ == "__main__":
    run_events_acceptance()
