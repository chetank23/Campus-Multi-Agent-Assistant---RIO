"""
tests/api/test_nemotron_correctness.py
---------------------------------------
Authoritative test suite for Phase 2:
RIO-MJP Nemotron Assistant Correctness & Database Grounding.

Verifies:
1. Grounded campus queries against actual database data:
   - Departments with generated timetables
   - Student count in a department
   - Faculty members in a department
   - Courses assigned to a semester
   - Available rooms
   - "Show my timetable" (Student, Faculty, Admin, Super Admin)
   - Currently booked resources
2. Deterministic final answer synthesis when model returns empty or generic traces:
   - Stripping reasoning tokens leaving empty output
   - Discarding generic "Executed tool successfully" fallback
   - Distinguishing missing records from database query errors
   - Multi-tool calls with partial failure reporting
   - Exception/timeout recovery after tool execution
3. Role-based access control and department scope:
   - Super Admin cross-department query access
   - Admin department scope restriction
   - Student isolation from unauthorized directories
"""

from __future__ import annotations

import datetime
import json
import os
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.orm import Session

from backend.database import engine
from backend.models.identity import User
from backend.models.academic import Department, Student, Faculty, Semester, Section
from backend.models.courses import Course
from backend.models.space_time import Room, TimeSlot
from backend.models.timetable import TimetableVersion, TimetableEntry

from agents.llm.nvidia_provider import (
    NvidiaNemotronProvider,
    is_unusable_response,
    strip_thinking,
    synthesize_single_tool_result,
    synthesize_tool_results_answer,
)
from agents.tools import execute_tool
from agents.tools.campus_tools import (
    get_published_timetable_status_data,
    get_room_availability_data,
    get_semester_courses_data,
)
from agents.tools.admin_tools import (
    search_student_directory_data,
    search_faculty_directory_data,
)
from agents.tools.student_tools import get_my_timetable_data
from agents.tools.resource_tools import get_user_bookings_data


@pytest.fixture
def db_session():
    """Provides a database session bound to the active test database."""
    with Session(engine) as session:
        yield session


@pytest.fixture
def superadmin_user(db_session: Session) -> User:
    u = db_session.query(User).filter(User.role == "SUPER_ADMIN").first()
    assert u is not None, "Super Admin user required in seed data"
    return u


@pytest.fixture
def admin_user(db_session: Session) -> User:
    u = db_session.query(User).filter(User.role == "ADMIN").first()
    assert u is not None, "Admin user required in seed data"
    return u


@pytest.fixture
def faculty_user(db_session: Session) -> User:
    u = db_session.query(User).filter(User.role == "FACULTY").first()
    assert u is not None, "Faculty user required in seed data"
    return u


@pytest.fixture
def student_user(db_session: Session) -> User:
    u = db_session.query(User).filter(User.role == "STUDENT").first()
    assert u is not None, "Student user required in seed data"
    return u


@pytest.fixture
def published_timetable(
    db_session: Session,
    admin_user: User,
    student_user: User,
    faculty_user: User,
) -> TimetableVersion:
    """
    Ensures a PUBLISHED TimetableVersion with entries exists in test_schema.
    """
    pub_v = (
        db_session.query(TimetableVersion)
        .filter(TimetableVersion.status == "PUBLISHED")
        .first()
    )
    if not pub_v:
        dept = db_session.query(Department).first()
        slot = db_session.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").first()
        course = db_session.query(Course).first()
        room = db_session.query(Room).first()
        stu = db_session.query(Student).filter(Student.user_id == student_user.id).first()
        fac = db_session.query(Faculty).filter(Faculty.user_id == faculty_user.id).first()
        sem = db_session.query(Semester).first()

        pub_v = TimetableVersion(
            status="PUBLISHED",
            version_number="V-PUB-1",
            published_at=datetime.datetime.now(datetime.timezone.utc),
            created_by=admin_user.id,
        )
        db_session.add(pub_v)
        db_session.flush()

        if slot and course and room and dept and stu:
            entry = TimetableEntry(
                version_id=pub_v.id,
                department_id=dept.id,
                semester_id=sem.id if sem else None,
                slot_id=slot.id,
                course_id=course.id,
                room_id=room.id,
                section_id=stu.section_id,
                faculty_id=fac.id if fac else None,
                status="ACTIVE",
            )
            db_session.add(entry)
            db_session.commit()
    return pub_v


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 2: DATABASE-GROUNDED REALISTIC QUERIES (ACTUAL DATABASE DATA)
# ═══════════════════════════════════════════════════════════════════════════════

def test_query_1_departments_with_generated_timetables(
    db_session: Session,
    admin_user: User,
    published_timetable: TimetableVersion,
):
    """
    Query 1: Which departments currently have generated timetables?
    Verifies actual departments from published timetable version.
    """
    res = get_published_timetable_status_data(db=db_session, user=admin_user)
    assert res["is_admin"] is True
    assert res["active_published_version"] is not None
    assert len(res["departments_with_timetables"]) > 0

    dept_name = res["departments_with_timetables"][0]
    v_num = res["active_published_version"]["version_number"]
    synth = synthesize_single_tool_result("get_published_timetable_status", {}, res, admin_user)
    assert dept_name in synth
    assert v_num in synth
    assert "Executed tool" not in synth


def test_query_2_student_count_in_department(db_session: Session, admin_user: User):
    """
    Query 2: How many students are registered in a department?
    Verifies exact count and student USNs from the database.
    """
    first_dept = db_session.query(Department).first()
    assert first_dept is not None
    expected_count = db_session.query(Student).filter(Student.department_id == first_dept.id).count()

    res = search_student_directory_data(db=db_session, user=admin_user, department_name=first_dept.name)
    assert res["success"] is True
    assert res["total_count"] == expected_count

    synth = synthesize_single_tool_result(
        "search_student_directory",
        {"department_name": first_dept.name},
        res,
        admin_user,
    )
    assert f"Found **{expected_count}** registered student(s)" in synth
    assert first_dept.name in synth
    assert "Executed tool" not in synth


def test_query_3_faculty_members_in_department(db_session: Session, admin_user: User):
    """
    Query 3: Which faculty members belong to a department?
    Verifies actual faculty count and faculty names from the database.
    """
    first_dept = db_session.query(Department).first()
    assert first_dept is not None
    expected_count = db_session.query(Faculty).filter(Faculty.department_id == first_dept.id).count()

    res = search_faculty_directory_data(db=db_session, user=admin_user, department_name=first_dept.name)
    assert res["success"] is True
    assert res["total_count"] == expected_count

    synth = synthesize_single_tool_result(
        "search_faculty_directory",
        {"department_name": first_dept.name},
        res,
        admin_user,
    )
    assert f"Found **{expected_count}** faculty member(s)" in synth
    assert first_dept.name in synth
    assert "Executed tool" not in synth


def test_query_4_semester_courses(db_session: Session, admin_user: User):
    """
    Query 4: What courses are assigned to a particular semester?
    Verifies curriculum courses for Semester 1 without fabricating non-existent courses.
    """
    res = get_semester_courses_data(db=db_session, user=admin_user, semester_number=1)
    assert res["semester_number"] == 1
    assert res["total_courses"] > 0

    synth = synthesize_single_tool_result("get_semester_courses", {"semester_number": 1}, res, admin_user)
    assert "Semester 1" in synth
    assert str(res["total_courses"]) in synth
    assert "Executed tool" not in synth


def test_query_5_available_rooms(db_session: Session, admin_user: User):
    """
    Query 5: Which rooms are available?
    Verifies available rooms on MONDAY 09:00 - 10:00.
    """
    res = get_room_availability_data(db=db_session, day="MONDAY", start_time="09:00", end_time="10:00")
    assert len(res["available_rooms"]) > 0

    synth = synthesize_single_tool_result(
        "get_room_availability",
        {"day": "MONDAY", "start_time": "09:00", "end_time": "10:00"},
        res,
        admin_user,
    )
    assert "available room(s)" in synth
    assert "Room" in synth
    assert "Executed tool" not in synth


def test_query_6_show_my_timetable_student(
    db_session: Session,
    student_user: User,
    published_timetable: TimetableVersion,
):
    """
    Query 6: Show my timetable (for student).
    Verifies student's scheduled class entries from the active published timetable.
    """
    res = get_my_timetable_data(db=db_session, user=student_user)
    assert len(res["entries"]) >= 1

    synth = synthesize_single_tool_result("get_my_timetable", {}, res, student_user)
    assert "Timetable Schedule" in synth
    assert "Room" in synth
    assert "Executed tool" not in synth


def test_query_6_show_my_timetable_admin_and_faculty(
    db_session: Session,
    admin_user: User,
    faculty_user: User,
    published_timetable: TimetableVersion,
):
    """
    Query 6: Show my timetable for Admin and Faculty.
    Admin receives clear guidance that they do not have personal class enrollments.
    Faculty receives their teaching slots.
    """
    admin_res = get_my_timetable_data(db=db_session, user=admin_user)
    admin_synth = synthesize_single_tool_result("get_my_timetable", {}, admin_res, admin_user)
    assert "Administrator" in admin_synth

    fac_res = get_my_timetable_data(db=db_session, user=faculty_user)
    fac_synth = synthesize_single_tool_result("get_my_timetable", {}, fac_res, faculty_user)
    assert "Timetable Schedule" in fac_synth or "No scheduled classes" in fac_synth


def test_query_7_booked_resources(db_session: Session, admin_user: User):
    """
    Query 7: Which resources are currently booked?
    When no bookings are active, responds clearly that no bookings were found (no hallucination).
    """
    res = get_user_bookings_data(db=db_session, user=admin_user)
    synth = synthesize_single_tool_result("get_user_bookings", {}, res, admin_user)
    assert "No resource bookings were found" in synth
    assert "Executed tool" not in synth


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 1 & 6: FINAL ANSWER SYNTHESIS & RESPONSE QUALITY
# ═══════════════════════════════════════════════════════════════════════════════

def test_empty_model_response_triggers_deterministic_synthesis(
    db_session: Session,
    admin_user: User,
    published_timetable: TimetableVersion,
):
    """
    When model executes a tool but outputs empty content on the next turn,
    the provider deterministically synthesizes the grounded answer.
    """
    tc = MagicMock()
    tc.id = "call_dept_tt"
    tc.type = "function"
    tc.function.name = "get_published_timetable_status"
    tc.function.arguments = "{}"

    resp1 = MagicMock()
    resp1.choices = [MagicMock()]
    resp1.choices[0].message.tool_calls = [tc]
    resp1.choices[0].message.content = ""

    # Turn 2: Model returns empty content
    resp2 = MagicMock()
    resp2.choices = [MagicMock()]
    resp2.choices[0].message.tool_calls = None
    resp2.choices[0].message.content = ""

    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-valid-test-key",
    }):
        with patch("agents.llm.nvidia_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = [resp1, resp2]
            MockOpenAI.return_value = mock_client

            provider = NvidiaNemotronProvider()
            res = provider.generate_chat_response(
                message="Which departments have generated timetables?",
                user=admin_user,
                db=db_session,
            )

            assert res["success"] is True
            assert published_timetable.version_number in res["reply"]
            assert "Executed tool" not in res["reply"]


def test_thinking_tokens_only_model_response_triggers_synthesis(db_session: Session, admin_user: User):
    """
    When model returns only reasoning tokens (<thought>...</thought>),
    strip_thinking leaves empty text, triggering deterministic data synthesis.
    """
    first_dept = db_session.query(Department).first()
    assert first_dept is not None

    tc = MagicMock()
    tc.id = "call_students"
    tc.type = "function"
    tc.function.name = "search_student_directory"
    tc.function.arguments = json.dumps({"department_name": first_dept.name})

    resp1 = MagicMock()
    resp1.choices = [MagicMock()]
    resp1.choices[0].message.tool_calls = [tc]
    resp1.choices[0].message.content = f"<thought>Looking up students in {first_dept.name}</thought>"

    resp2 = MagicMock()
    resp2.choices = [MagicMock()]
    resp2.choices[0].message.tool_calls = None
    resp2.choices[0].message.content = "<thought>Finished tool execution. Internal summary only.</thought>"

    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-valid-test-key",
    }):
        with patch("agents.llm.nvidia_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = [resp1, resp2]
            MockOpenAI.return_value = mock_client

            provider = NvidiaNemotronProvider()
            res = provider.generate_chat_response(
                message=f"How many students are in {first_dept.name}?",
                user=admin_user,
                db=db_session,
            )

            assert res["success"] is True
            assert "<thought>" not in res["reply"]
            assert "registered student(s)" in res["reply"]
            assert "Executed tool" not in res["reply"]


def test_generic_tool_trace_model_response_is_discarded(
    db_session: Session,
    student_user: User,
    published_timetable: TimetableVersion,
):
    """
    When model outputs generic fallback text ('Executed tool get_my_timetable successfully'),
    is_unusable_response detects it and replaces it with verified data.
    """
    generic_text = "Here are the database records matching your inquiry:\n\n- Executed tool `get_my_timetable` successfully.\n"
    assert is_unusable_response(generic_text) is True

    tc = MagicMock()
    tc.id = "call_tt"
    tc.type = "function"
    tc.function.name = "get_my_timetable"
    tc.function.arguments = "{}"

    resp1 = MagicMock()
    resp1.choices = [MagicMock()]
    resp1.choices[0].message.tool_calls = [tc]
    resp1.choices[0].message.content = ""

    resp2 = MagicMock()
    resp2.choices = [MagicMock()]
    resp2.choices[0].message.tool_calls = None
    resp2.choices[0].message.content = generic_text

    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-valid-test-key",
    }):
        with patch("agents.llm.nvidia_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = [resp1, resp2]
            MockOpenAI.return_value = mock_client

            provider = NvidiaNemotronProvider()
            res = provider.generate_chat_response(
                message="Show my timetable.",
                user=student_user,
                db=db_session,
            )

            assert res["success"] is True
            assert "Executed tool" not in res["reply"]
            assert "Timetable Schedule" in res["reply"]


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 4: SUPER ADMIN SUPPORT & AUTHORIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def test_super_admin_cross_department_and_institutional_overview(
    db_session: Session,
    superadmin_user: User,
):
    """
    Verifies Super Admin can query cross-department data and institutional summaries.
    """
    inst_res = execute_tool("get_institutional_overview", {}, superadmin_user, db_session)
    assert inst_res.get("error") is None
    assert inst_res.get("total_departments") is not None

    synth = synthesize_single_tool_result("get_institutional_overview", {}, inst_res, superadmin_user)
    assert "Institutional Governance Overview" in synth
    assert "Academic Departments" in synth

    first_dept = db_session.query(Department).first()
    assert first_dept is not None
    stu_res = execute_tool(
        "search_student_directory",
        {"department_name": first_dept.name},
        superadmin_user,
        db_session,
    )
    assert stu_res.get("error") is None
    assert stu_res.get("total_count") > 0


def test_admin_department_scope_restriction(db_session: Session, admin_user: User):
    """
    Verifies department-scoped Admin cannot query outside assigned department.
    """
    first_dept = db_session.query(Department).first()
    other_dept = db_session.query(Department).filter(Department.id != first_dept.id).first()
    assert first_dept is not None
    assert other_dept is not None

    orig_dept = admin_user.department_id
    try:
        # Assign admin to other_dept, then attempt to query first_dept
        admin_user.department_id = other_dept.id
        db_session.commit()
        res = search_student_directory_data(db=db_session, user=admin_user, department_name=first_dept.name)
        assert "error" in res
        assert "Access denied" in res["error"]
    finally:
        admin_user.department_id = orig_dept
        db_session.commit()


def test_student_unauthorized_tool_query(db_session: Session, student_user: User):
    """
    Verifies student cannot query administrative tools (e.g. search_student_directory).
    """
    res = execute_tool("search_student_directory", {"search_query": "test"}, student_user, db_session)
    assert "error" in res
    assert "Role 'STUDENT' is not authorized" in res["error"]

    synth = synthesize_single_tool_result("search_student_directory", {}, res, student_user)
    assert "Access Denied" in synth


# ═══════════════════════════════════════════════════════════════════════════════
# TASK 5: ERROR AND EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

def test_tool_execution_with_empty_results(admin_user: User):
    """
    When database query returns zero records, synthesizer clearly reports that
    no records were found without inventing data.
    """
    empty_tool_result = {"total_courses": 0, "courses": []}
    synth = synthesize_single_tool_result("get_semester_courses", {"semester_number": 99}, empty_tool_result, admin_user)
    assert "No courses found" in synth


def test_tool_execution_failure_reporting(admin_user: User):
    """
    When database tool returns error, synthesizer clearly reports failure,
    never disguising it as success.
    """
    failed_tool_result = {"error": "Connection to database failed."}
    synth = synthesize_single_tool_result("get_room_availability", {}, failed_tool_result, admin_user)
    assert "Unable to retrieve the requested information: Connection to database failed." in synth


def test_partial_tool_failure_in_multi_tool_sequence(admin_user: User):
    """
    When multiple tools execute, one succeeds and one fails,
    both successful data and failure notice are reported cleanly.
    """
    tool_records = [
        {
            "tool": "get_semester_courses",
            "args": {"semester_number": 7},
            "result": {
                "semester_number": 7,
                "total_courses": 1,
                "courses": [{"course_code": "CS701", "course_name": "AI Systems", "credits": 4}],
            },
            "error": None,
        },
        {
            "tool": "get_room_availability",
            "args": {},
            "result": {"error": "Room catalog currently undergoing maintenance."},
            "error": "Room catalog currently undergoing maintenance.",
        },
    ]

    synth = synthesize_tool_results_answer(admin_user, "Check sem 7 courses and rooms.", tool_records)
    assert "CS701" in synth
    assert "AI Systems" in synth
    assert "Notice: Unable to retrieve records for get room availability" in synth


def test_malformed_tool_output_handled_gracefully(admin_user: User):
    """
    When tool output is non-dict (e.g. string or None), synthesizer does not crash.
    """
    synth1 = synthesize_single_tool_result("unknown_tool", {}, None, admin_user)
    assert "No records were returned" in synth1

    synth2 = synthesize_single_tool_result("unknown_tool", {}, "Raw string output", admin_user)
    assert "Raw string output" in synth2


def test_model_timeout_after_tools_executed_recovers(
    db_session: Session,
    student_user: User,
    published_timetable: TimetableVersion,
):
    """
    When model drops connection or times out on final response turn after executing tools,
    provider recovers and returns the synthesized answer from executed tool records.
    """
    tc = MagicMock()
    tc.id = "call_tt_timeout"
    tc.type = "function"
    tc.function.name = "get_my_timetable"
    tc.function.arguments = "{}"

    resp1 = MagicMock()
    resp1.choices = [MagicMock()]
    resp1.choices[0].message.tool_calls = [tc]
    resp1.choices[0].message.content = ""

    with patch.dict(os.environ, {
        "RIO_CHAT_LLM_ENABLED": "true",
        "RIO_CHAT_LLM_PROVIDER": "nvidia",
        "NVIDIA_API_KEY": "nvapi-valid-test-key",
    }):
        with patch("agents.llm.nvidia_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            # Turn 1 succeeds with tool call, Turn 2 raises timeout exception
            mock_client.chat.completions.create.side_effect = [
                resp1,
                Exception("ReadTimeout: Connection closed while reading response"),
            ]
            MockOpenAI.return_value = mock_client

            provider = NvidiaNemotronProvider()
            res = provider.generate_chat_response(
                message="Show my timetable.",
                user=student_user,
                db=db_session,
            )

            # Successfully recovered using deterministic answer builder!
            assert res["success"] is True
            assert "Timetable Schedule" in res["reply"]
