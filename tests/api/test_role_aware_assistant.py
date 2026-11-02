"""
tests/api/test_role_aware_assistant.py
--------------------------------------
Comprehensive verification test suite for the Role-Aware AI Campus Assistant:
1. Conversation Persistence CRUD (POST, GET, GET by ID, DELETE)
2. Cross-user conversation security and RBAC barriers (403 for unauthorized access/deletion)
3. Unauthenticated access enforcement (401 for all chat/conversation endpoints)
4. Persistent multi-turn chat message tracking in ChatConversation and ChatMessage
5. Direct and agent-dispatched verification of all 12 prioritized grounded tools:
   - Tool 1: get_my_timetable (Student and Faculty self-schedules)
   - Tool 2: get_student_timetable (Admin-allowed, Student self-allowed, Student cross-user denied)
   - Tool 3: get_faculty_timetable (Admin-allowed, Faculty self-allowed, Faculty cross-user denied)
   - Tool 4: get_department_timetable (Admin and Faculty allowed, Student denied)
   - Tool 5: get_course_information (Catalog, credits, course type, instructors)
   - Tool 6: get_faculty_information (Designation, specialization, student contact masking)
   - Tool 7: get_room_availability (Classrooms availability)
   - Tool 8: get_lab_availability (Laboratory availability)
   - Tool 9: get_resource_booking_status (User-scoped history, Admin global view)
   - Tool 10: get_published_timetable_status (Strict draft isolation for students/faculty)
   - Tool 11: get_recent_timetable_changes (Timetable notices and admin audit log)
   - Tool 12: get_relevant_announcements (Audience-filtered notifications and broadcasts)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import engine
from backend.models import User, Student, Faculty, Department, Course, Room, TimetableVersion, TimetableEntry, Section
from agents.tools import execute_tool

client = TestClient(app)


# ---------------------------------------------------------------------------
# Test Fixtures & Tokens
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    with Session(engine) as db:
        yield db


@pytest.fixture(scope="module")
def student_auth():
    resp = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Student login failed: {resp.text}"
    data = resp.json()
    return {"token": data["access_token"], "user": data.get("user", {})}


@pytest.fixture(scope="module")
def student2_auth():
    # Another student in Dataset A to test cross-student barriers
    resp = client.post("/auth/login", json={"email": "jamie.arnold@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Student 2 login failed: {resp.text}"
    data = resp.json()
    return {"token": data["access_token"], "user": data.get("user", {})}


@pytest.fixture(scope="module")
def faculty_auth():
    resp = client.post("/auth/login", json={"email": "allison.hill@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Faculty login failed: {resp.text}"
    data = resp.json()
    return {"token": data["access_token"], "user": data.get("user", {})}


@pytest.fixture(scope="module")
def faculty2_auth():
    # Another faculty in Dataset A to test cross-faculty barriers
    resp = client.post("/auth/login", json={"email": "noah.rhodes@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Faculty 2 login failed: {resp.text}"
    data = resp.json()
    return {"token": data["access_token"], "user": data.get("user", {})}


@pytest.fixture(scope="module")
def admin_auth():
    resp = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    data = resp.json()
    return {"token": data["access_token"], "user": data.get("user", {})}


# ---------------------------------------------------------------------------
# 1. Unauthenticated Enforcement
# ---------------------------------------------------------------------------

def test_unauthenticated_endpoints_rejected():
    """All agent and conversation endpoints must require valid Bearer tokens."""
    assert client.get("/agents/conversations").status_code == 401
    assert client.post("/agents/conversations", json={"title": "Test"}).status_code == 401
    assert client.get("/agents/conversations/1").status_code == 401
    assert client.delete("/agents/conversations/1").status_code == 401
    assert client.post("/agents/chat", json={"message": "Hello"}).status_code == 401


# ---------------------------------------------------------------------------
# 2. Conversation Persistence & Lifecycle CRUD
# ---------------------------------------------------------------------------

def test_conversation_lifecycle(student_auth, student2_auth):
    """Verify conversation creation, listing, retrieval, cross-user isolation, and deletion."""
    s1_headers = {"Authorization": f"Bearer {student_auth['token']}"}
    s2_headers = {"Authorization": f"Bearer {student2_auth['token']}"}

    # 1. Create a conversation for Student 1
    create_resp = client.post(
        "/agents/conversations",
        headers=s1_headers,
        json={"title": "Academic Advising Session"},
    )
    assert create_resp.status_code == 201
    conv_data = create_resp.json()
    conv_id = conv_data["id"]
    assert conv_data["title"] == "Academic Advising Session"
    assert conv_data["role"] == "STUDENT"
    assert conv_data["message_count"] == 0

    # 2. List conversations for Student 1
    list_resp = client.get("/agents/conversations", headers=s1_headers)
    assert list_resp.status_code == 200
    conversations = list_resp.json()
    assert any(c["id"] == conv_id for c in conversations)

    # 3. Retrieve conversation detail for Student 1
    detail_resp = client.get(f"/agents/conversations/{conv_id}", headers=s1_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["id"] == conv_id
    assert detail["title"] == "Academic Advising Session"
    assert len(detail["messages"]) == 0

    # 4. Cross-user isolation: Student 2 cannot access Student 1's conversation
    s2_detail_resp = client.get(f"/agents/conversations/{conv_id}", headers=s2_headers)
    assert s2_detail_resp.status_code == 403

    # 5. Cross-user isolation: Student 2 cannot delete Student 1's conversation
    s2_del_resp = client.delete(f"/agents/conversations/{conv_id}", headers=s2_headers)
    assert s2_del_resp.status_code == 403

    # 6. Post a message to this conversation
    chat_resp = client.post(
        "/agents/chat",
        headers=s1_headers,
        json={
            "message": "When is my next class?",
            "conversation_id": conv_id,
        },
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert chat_data["conversation_id"] == conv_id

    # 7. Verify messages are persisted
    detail_resp2 = client.get(f"/agents/conversations/{conv_id}", headers=s1_headers)
    assert detail_resp2.status_code == 200
    detail2 = detail_resp2.json()
    assert len(detail2["messages"]) == 2  # 1 user + 1 assistant
    assert detail2["messages"][0]["sender"] == "user"
    assert detail2["messages"][0]["content"] == "When is my next class?"
    assert detail2["messages"][1]["sender"] == "assistant"

    # 8. Delete conversation
    del_resp = client.delete(f"/agents/conversations/{conv_id}", headers=s1_headers)
    assert del_resp.status_code == 200

    # 9. Ensure it is gone
    get_after_del = client.get(f"/agents/conversations/{conv_id}", headers=s1_headers)
    assert get_after_del.status_code == 404


def test_chat_cross_conversation_security(student_auth, student2_auth):
    """Posting a chat message with someone else's conversation_id must fail with 403."""
    s1_headers = {"Authorization": f"Bearer {student_auth['token']}"}
    s2_headers = {"Authorization": f"Bearer {student2_auth['token']}"}

    create_resp = client.post(
        "/agents/conversations",
        headers=s1_headers,
        json={"title": "Private Notes"},
    )
    assert create_resp.status_code == 201
    conv_id = create_resp.json()["id"]

    # Student 2 attempts to post into Student 1's conversation
    hacked_post = client.post(
        "/agents/chat",
        headers=s2_headers,
        json={
            "message": "Injecting into your session",
            "conversation_id": conv_id,
        },
    )
    assert hacked_post.status_code == 403

    # Cleanup
    client.delete(f"/agents/conversations/{conv_id}", headers=s1_headers)


def test_admin_cannot_access_or_delete_user_conversations(student_auth, admin_auth):
    """Admin has no blanket access to other users' private chat conversations."""
    s_headers = {"Authorization": f"Bearer {student_auth['token']}"}
    a_headers = {"Authorization": f"Bearer {admin_auth['token']}"}

    create_resp = client.post(
        "/agents/conversations",
        headers=s_headers,
        json={"title": "Confidential Student Chat"},
    )
    assert create_resp.status_code == 201
    conv_id = create_resp.json()["id"]

    # Admin attempts to read Student's conversation -> 403 Forbidden
    admin_get = client.get(f"/agents/conversations/{conv_id}", headers=a_headers)
    assert admin_get.status_code == 403

    # Admin attempts to post into Student's conversation -> 403 Forbidden
    admin_post = client.post(
        "/agents/chat",
        headers=a_headers,
        json={"message": "Admin probe", "conversation_id": conv_id},
    )
    assert admin_post.status_code == 403

    # Admin attempts to delete Student's conversation -> 403 Forbidden
    admin_del = client.delete(f"/agents/conversations/{conv_id}", headers=a_headers)
    assert admin_del.status_code == 403

    # Student can delete their own conversation
    student_del = client.delete(f"/agents/conversations/{conv_id}", headers=s_headers)
    assert student_del.status_code == 200


# ---------------------------------------------------------------------------
# 3. Grounded Tools Verification (All 12 Tools)
# ---------------------------------------------------------------------------

def test_tool_1_get_my_timetable_student(student_auth):
    """Tool 1: get_my_timetable returns student's section schedule."""
    headers = {"Authorization": f"Bearer {student_auth['token']}"}
    resp = client.post("/agents/chat", headers=headers, json={"message": "Show my timetable"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    reply = data["reply"].lower()
    assert "timetable" in reply or "class" in reply or "schedule" in reply or "active" in reply


def test_tool_1_get_my_timetable_faculty(faculty_auth):
    """Tool 1: get_my_timetable returns faculty's assigned classes."""
    headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    resp = client.post("/agents/chat", headers=headers, json={"message": "Show my schedule"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    reply = data["reply"].lower()
    assert "schedule" in reply or "teaching" in reply or "class" in reply or "timetable" in reply or "active" in reply


def test_tool_2_get_student_timetable_rbac(db_session: Session):
    """Tool 2: get_student_timetable allows Admin and Self, strictly denies cross-student."""
    s1_user = db_session.query(User).filter(User.email == "monica.herrera@campus.edu").first()
    s2_user = db_session.query(User).filter(User.email == "jamie.arnold@campus.edu").first()
    admin_user = db_session.query(User).filter(User.email == "admin@campus.edu").first()
    assert s1_user and s2_user and admin_user

    s1 = db_session.query(Student).filter(Student.user_id == s1_user.id).first()
    assert s1

    # 1. Admin query for Student 1 succeeds
    admin_result = execute_tool(
        tool_name="get_student_timetable",
        tool_args={"student_id": s1.id},
        user=admin_user,
        db=db_session,
    )
    assert "error" not in admin_result or admin_result.get("success") is True

    # 2. Student 1 querying own schedule succeeds without error
    self_result = execute_tool(
        tool_name="get_student_timetable",
        tool_args={"student_id": s1.id},
        user=s1_user,
        db=db_session,
    )
    assert "error" not in self_result
    assert "entries" in self_result

    # 3. Student 2 querying Student 1's schedule is strictly denied
    cross_result = execute_tool(
        tool_name="get_student_timetable",
        tool_args={"student_id": s1.id},
        user=s2_user,
        db=db_session,
    )
    assert "error" in cross_result
    assert "Access denied" in cross_result["error"]


def test_tool_3_get_faculty_timetable_rbac(db_session: Session):
    """Tool 3: get_faculty_timetable allows Admin and Self, denies cross-faculty."""
    f1_user = db_session.query(User).filter(User.email == "allison.hill@campus.edu").first()
    f2_user = db_session.query(User).filter(User.email == "noah.rhodes@campus.edu").first()
    admin_user = db_session.query(User).filter(User.email == "admin@campus.edu").first()
    assert f1_user and f2_user and admin_user

    f1 = db_session.query(Faculty).filter(Faculty.user_id == f1_user.id).first()
    assert f1

    # 1. Admin query for Faculty 1 succeeds
    admin_result = execute_tool(
        tool_name="get_faculty_timetable",
        tool_args={"faculty_id": f1.id},
        user=admin_user,
        db=db_session,
    )
    assert "error" not in admin_result
    assert admin_result.get("faculty_name") == "Allison Hill"

    # 2. Faculty 1 querying own schedule succeeds
    self_result = execute_tool(
        tool_name="get_faculty_timetable",
        tool_args={"faculty_id": f1.id},
        user=f1_user,
        db=db_session,
    )
    assert "error" not in self_result
    assert self_result.get("faculty_name") == "Allison Hill"

    # 3. Faculty 2 querying Faculty 1 schedule is denied
    cross_result = execute_tool(
        tool_name="get_faculty_timetable",
        tool_args={"faculty_id": f1.id},
        user=f2_user,
        db=db_session,
    )
    assert "error" in cross_result
    assert "Access denied" in cross_result["error"]


def test_tool_4_get_department_timetable_rbac(db_session: Session):
    """Tool 4: get_department_timetable allows Admin & assigned Faculty, denies Student."""
    dept = db_session.query(Department).first()
    admin_user = db_session.query(User).filter(User.role == "ADMIN").first()
    student_user = db_session.query(User).filter(User.role == "STUDENT").first()
    assert dept and admin_user and student_user

    # 1. Admin allowed
    admin_res = execute_tool(
        tool_name="get_department_timetable",
        tool_args={"department_id": dept.id},
        user=admin_user,
        db=db_session,
    )
    assert "error" not in admin_res
    assert "entries" in admin_res

    # 2. Student strictly denied
    student_res = execute_tool(
        tool_name="get_department_timetable",
        tool_args={"department_id": dept.id},
        user=student_user,
        db=db_session,
    )
    assert "error" in student_res
    assert "not authorized" in student_res["error"]


def test_tool_5_get_course_information(db_session: Session, student_auth):
    """Tool 5: get_course_information returns code, name, credits, and assigned instructors."""
    course = db_session.query(Course).first()
    student_user = db_session.query(User).filter(User.role == "STUDENT").first()
    assert course and student_user

    # Direct tool execution
    direct_res = execute_tool(
        tool_name="get_course_information",
        tool_args={"query_str": course.course_code},
        user=student_user,
        db=db_session,
    )
    assert "results" in direct_res
    assert direct_res["count"] > 0
    assert direct_res["results"][0]["code"] == course.course_code

    # Natural language API invocation
    headers = {"Authorization": f"Bearer {student_auth['token']}"}
    resp = client.post("/agents/chat", headers=headers, json={"message": f"Tell me about course {course.course_code}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    reply = data["reply"]
    assert course.course_code in reply or course.course_name in reply


def test_tool_6_get_faculty_information_privacy(db_session: Session):
    """Tool 6: get_faculty_information returns academic details and masks phone for students."""
    fac = db_session.query(Faculty).first()
    student_user = db_session.query(User).filter(User.role == "STUDENT").first()
    admin_user = db_session.query(User).filter(User.role == "ADMIN").first()
    assert fac and student_user and admin_user
    assert fac.user is not None

    # Direct tool call as STUDENT -> contact_number MUST be None
    s_res = execute_tool(
        tool_name="get_faculty_information",
        tool_args={"name_or_dept": fac.user.name},
        user=student_user,
        db=db_session,
    )
    assert "results" in s_res
    assert len(s_res["results"]) > 0
    first_fac_s = s_res["results"][0]
    assert first_fac_s["contact_number"] is None  # Masked for student privacy

    # Temporarily assign a test contact number to verify admin unmasking
    original_contact = fac.contact_number
    fac.contact_number = "555-0199"
    db_session.commit()

    try:
        a_res = execute_tool(
            tool_name="get_faculty_information",
            tool_args={"name_or_dept": fac.user.name},
            user=admin_user,
            db=db_session,
        )
        assert "results" in a_res
        matching = [f for f in a_res["results"] if f["faculty_id"] == fac.faculty_id or f["name"] == fac.user.name]
        assert len(matching) > 0
        assert matching[0]["contact_number"] == "555-0199"  # Admin sees contact
    finally:
        fac.contact_number = original_contact
        db_session.commit()


def test_tool_7_and_8_room_and_lab_availability(db_session: Session):
    """Tool 7 & 8: get_room_availability and get_lab_availability return grounded availability."""
    student_user = db_session.query(User).filter(User.role == "STUDENT").first()
    assert student_user

    # Room availability
    room_res = execute_tool(
        tool_name="get_room_availability",
        tool_args={"day": "MONDAY"},
        user=student_user,
        db=db_session,
    )
    assert "available_rooms" in room_res
    assert isinstance(room_res["available_rooms"], list)

    # Lab availability
    lab_res = execute_tool(
        tool_name="get_lab_availability",
        tool_args={"day": "MONDAY"},
        user=student_user,
        db=db_session,
    )
    assert "available_rooms" in lab_res
    assert lab_res.get("room_type") == "LAB"
    assert isinstance(lab_res["available_rooms"], list)


def test_tool_9_get_resource_booking_status(db_session: Session):
    """Tool 9: get_resource_booking_status returns user-scoped bookings, Admin sees global."""
    student_user = db_session.query(User).filter(User.role == "STUDENT").first()
    admin_user = db_session.query(User).filter(User.role == "ADMIN").first()
    assert student_user and admin_user

    res_student = execute_tool(
        tool_name="get_resource_booking_status",
        tool_args={},
        user=student_user,
        db=db_session,
    )
    assert "bookings" in res_student
    assert "count" in res_student

    res_admin = execute_tool(
        tool_name="get_resource_booking_status",
        tool_args={},
        user=admin_user,
        db=db_session,
    )
    assert "bookings" in res_admin
    assert "count" in res_admin


def test_tool_10_get_published_timetable_status_draft_isolation(db_session: Session):
    """Tool 10: get_published_timetable_status isolates drafts from Students & Faculty."""
    student_user = db_session.query(User).filter(User.role == "STUDENT").first()
    admin_user = db_session.query(User).filter(User.role == "ADMIN").first()
    assert student_user and admin_user

    # Student view
    s_res = execute_tool(
        tool_name="get_published_timetable_status",
        tool_args={},
        user=student_user,
        db=db_session,
    )
    assert "has_published_timetable" in s_res
    assert s_res.get("role") == "STUDENT"
    # Drafts must NOT be present in student output
    assert "draft_timetables" not in s_res

    # Admin view
    a_res = execute_tool(
        tool_name="get_published_timetable_status",
        tool_args={},
        user=admin_user,
        db=db_session,
    )
    assert a_res.get("is_admin") is True
    assert "versions" in a_res


def test_tool_11_get_recent_timetable_changes(db_session: Session):
    """Tool 11: get_recent_timetable_changes returns notices and updates."""
    student_user = db_session.query(User).filter(User.role == "STUDENT").first()
    assert student_user

    changes_res = execute_tool(
        tool_name="get_recent_timetable_changes",
        tool_args={"limit": 5},
        user=student_user,
        db=db_session,
    )
    assert "recent_announcements" in changes_res
    assert "admin_audit_records" in changes_res
    assert "total_changes" in changes_res


def test_tool_12_get_relevant_announcements(db_session: Session):
    """Tool 12: get_relevant_announcements returns audience-grounded notifications."""
    student_user = db_session.query(User).filter(User.role == "STUDENT").first()
    faculty_user = db_session.query(User).filter(User.role == "FACULTY").first()
    assert student_user and faculty_user

    # Student query
    s_res = execute_tool(
        tool_name="get_relevant_announcements",
        tool_args={},
        user=student_user,
        db=db_session,
    )
    assert "announcements" in s_res
    for ann in s_res["announcements"]:
        assert ann.get("target_audience") in ("ALL", "STUDENT", "ALL_ROLES", None)

    # Faculty query
    f_res = execute_tool(
        tool_name="get_relevant_announcements",
        tool_args={},
        user=faculty_user,
        db=db_session,
    )
    assert "announcements" in f_res
    for ann in f_res["announcements"]:
        assert ann.get("target_audience") in ("ALL", "FACULTY", "ALL_ROLES", None)


def test_chat_drawer_tool_queries_via_api(student_auth, faculty_auth, admin_auth):
    """End-to-end API test verifying natural language chat invokes grounded tools."""
    # Student asks for announcements
    s_headers = {"Authorization": f"Bearer {student_auth['token']}"}
    s_resp = client.post("/agents/chat", headers=s_headers, json={"message": "What are the latest announcements?"})
    assert s_resp.status_code == 200
    s_data = s_resp.json()
    assert s_data["success"] is True
    reply_lower = s_data["reply"].lower()
    assert "announcement" in reply_lower or "notice" in reply_lower or "event" in reply_lower or "academic calendar" in reply_lower

    # Faculty asks about room availability
    f_headers = {"Authorization": f"Bearer {faculty_auth['token']}"}
    f_resp = client.post("/agents/chat", headers=f_headers, json={"message": "Are there rooms available on Monday?"})
    assert f_resp.status_code == 200
    f_data = f_resp.json()
    assert f_data["success"] is True
    assert "room" in f_data["reply"].lower()

    # Admin asks for timetable status
    a_headers = {"Authorization": f"Bearer {admin_auth['token']}"}
    a_resp = client.post("/agents/chat", headers=a_headers, json={"message": "Check published timetable status"})
    assert a_resp.status_code == 200
    a_data = a_resp.json()
    assert a_data["success"] is True
    assert "timetable" in a_data["reply"].lower()
