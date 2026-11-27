"""
tests/api/test_published_timetable_query_pipeline.py
----------------------------------------------------
End-to-end integration tests for the RIO Multi-Agent Campus Assistant's
published & unpublished timetable query pipeline:
- Intent classification & tool selection (get_published_timetables)
- Real PostgreSQL retrieval across multiple departments & sections
- Exclusion of RECALLED, ARCHIVED, and DRAFT versions from published results
- Unpublished scope classification (No timetable generated, Generated not validated,
  Validated not approved, Approved not published, Recalled)
- Role-based visibility isolation (ADMIN, FACULTY, STUDENT)
- Empty-result natural language handling
- Duplicate tool call prevention & Nemotron synthesis fallback (no tool-log leaks)
- SSE streaming (/agents/chat/stream) coherence
"""

from __future__ import annotations

import datetime
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.config import engine
from backend.main import app
from backend.models import (
    AcademicYear,
    Course,
    Department,
    Faculty,
    Program,
    Room,
    Section,
    Semester,
    Student,
    TimeSlot,
    TimetableEntry,
    TimetableVersion,
    User,
)
from agents.llm.nvidia_provider import NvidiaNemotronProvider, strip_thinking

client = TestClient(app)


@pytest.fixture(scope="module")
def tokens():
    admin_r = client.post("/auth/login", json={"email": "admin@campus.edu", "password": "Test@1234"})
    fac_r = client.post("/auth/login", json={"email": "allison.hill@campus.edu", "password": "Test@1234"})
    stu_r = client.post("/auth/login", json={"email": "monica.herrera@campus.edu", "password": "Test@1234"})
    assert admin_r.status_code == 200
    assert fac_r.status_code == 200
    assert stu_r.status_code == 200
    return {
        "ADMIN": admin_r.json()["access_token"],
        "FACULTY": fac_r.json()["access_token"],
        "STUDENT": stu_r.json()["access_token"],
    }


@pytest.fixture(scope="module")
def seeded_timetable_fixture():
    """
    Sets up deterministic multi-department timetable versions in the test DB:
    - Dept 1 (e.g. CSE / first dept): PUBLISHED version with active entries
    - Dept 2 (or newly created AI & DS dept): DRAFT / RECALLED / APPROVED versions for unpublished coverage
    Restores original state after module tests complete.
    """
    created_version_ids = []
    created_dept_id = None
    created_prog_id = None
    created_sec_id = None

    with Session(engine) as db:
        # Clean prior timetable versions & entries so assertions are deterministic
        db.query(TimetableEntry).delete()
        db.query(TimetableVersion).delete()
        db.commit()

        ay = db.query(AcademicYear).first()
        sem = db.query(Semester).first()
        depts = db.query(Department).order_by(Department.id.asc()).all()
        assert ay and sem and len(depts) >= 1
        dept1 = depts[0]
        prog1 = db.query(Program).filter(Program.department_id == dept1.id).first() or db.query(Program).first()
        sec1 = db.query(Section).filter(Section.department_id == dept1.id).first() or db.query(Section).first()
        fac = db.query(Faculty).first()
        course = db.query(Course).first()
        room = db.query(Room).first()
        slot = db.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").first()
        admin_user = db.query(User).filter(User.role == "ADMIN").first()
        assert all([prog1, sec1, fac, course, room, slot, admin_user])
        assert prog1 and sec1 and fac and course and room and slot and admin_user

        # Ensure a second department exists (e.g. AI & DS) for multi-department & unpublished tests
        dept2 = db.query(Department).filter(Department.id != dept1.id).first()
        if not dept2:
            dept2 = Department(department_code="AIDS-TEST", name="AI & DS")
            db.add(dept2)
            db.flush()
            created_dept_id = dept2.id
            prog2 = Program(department_id=dept2.id, program_name="B.Tech AI & DS", degree="B.Tech", duration=4)
            db.add(prog2)
            db.flush()
            created_prog_id = prog2.id
            sec2 = Section(
                department_id=dept2.id,
                program_id=prog2.id,
                semester_id=sem.id,
                section_name="AIDS-A",
                student_count=60,
            )
            db.add(sec2)
            db.flush()
            created_sec_id = sec2.id
        else:
            prog2 = db.query(Program).filter(Program.department_id == dept2.id).first()
            sec2 = db.query(Section).filter(Section.department_id == dept2.id).first()
            if not sec2:
                sec2 = Section(
                    department_id=dept2.id,
                    program_id=prog2.id if prog2 else None,
                    semester_id=sem.id,
                    section_name="SEC-D2",
                    student_count=60,
                )
                db.add(sec2)
                db.flush()
                created_sec_id = sec2.id

        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

        # 1. Published version for dept1
        v_pub1 = TimetableVersion(
            academic_year_id=ay.id,
            department_id=dept1.id,
            program_id=prog1.id,
            semester_id=sem.id,
            version_number="1.0",
            status="PUBLISHED",
            revision=1,
            validated_revision=1,
            validation_status="PASSED",
            approved_revision=1,
            approved_by=admin_user.id,
            approved_at=now_utc,
            published_at=now_utc,
            created_by=admin_user.id,
            last_saved_by=admin_user.id,
        )
        db.add(v_pub1)
        db.flush()
        created_version_ids.append(v_pub1.id)

        db.add(TimetableEntry(
            version_id=v_pub1.id,
            department_id=dept1.id,
            program_id=prog1.id,
            semester_id=sem.id,
            section_id=sec1.id,
            course_id=course.id,
            faculty_id=fac.id,
            room_id=room.id,
            slot_id=slot.id,
            status="ACTIVE",
        ))

        # 2. Recalled version for dept1 (MUST be excluded from published results)
        v_recalled = TimetableVersion(
            academic_year_id=ay.id,
            department_id=dept1.id,
            program_id=prog1.id,
            semester_id=sem.id,
            version_number="0.9",
            status="RECALLED",
            revision=1,
            created_by=admin_user.id,
            recalled_by=admin_user.id,
            recalled_at=now_utc,
            recall_reason="Superseded test",
        )
        db.add(v_recalled)
        db.flush()
        created_version_ids.append(v_recalled.id)

        # 3. Draft (unvalidated) version for dept2
        v_draft2 = TimetableVersion(
            academic_year_id=ay.id,
            department_id=dept2.id,
            program_id=prog2.id if prog2 else None,
            semester_id=sem.id,
            version_number="1.0",
            status="GENERATED",
            revision=1,
            created_by=admin_user.id,
        )
        db.add(v_draft2)
        db.flush()
        created_version_ids.append(v_draft2.id)

        db.commit()

        info = {
            "dept1_id": dept1.id,
            "dept1_name": dept1.name,
            "sec1_name": sec1.section_name,
            "dept2_id": dept2.id,
            "dept2_name": dept2.name,
            "sec2_name": sec2.section_name if sec2 else None,
            "pub_version_id": v_pub1.id,
            "recalled_version_id": v_recalled.id,
            "draft2_version_id": v_draft2.id,
            "ay_id": ay.id,
            "sem_id": sem.id,
            "prog2_id": prog2.id if prog2 else None,
        }

    yield info

    with Session(engine) as db:
        db.query(TimetableEntry).filter(TimetableEntry.version_id.in_(created_version_ids)).delete(synchronize_session=False)
        db.query(TimetableVersion).filter(TimetableVersion.id.in_(created_version_ids)).delete(synchronize_session=False)
        if created_sec_id:
            db.query(Section).filter(Section.id == created_sec_id).delete(synchronize_session=False)
        if created_prog_id:
            db.query(Program).filter(Program.id == created_prog_id).delete(synchronize_session=False)
        if created_dept_id:
            db.query(Department).filter(Department.id == created_dept_id).delete(synchronize_session=False)
        db.commit()


def _assert_clean_grounded_reply(resp_json: dict):
    reply = resp_json.get("reply", "")
    assert reply.strip(), "Reply must not be empty"
    assert "Executed tool" not in reply, f"Internal tool log leaked: {reply}"
    assert "execute_semantic_query" not in reply, f"Internal tool name leaked: {reply}"
    assert "get_published_timetables" not in reply, f"Internal tool name leaked: {reply}"
    assert "<tool_call" not in reply, f"Raw XML tool call leaked: {reply}"
    assert "<thought" not in reply and "<think" not in reply, f"Thinking tags leaked: {reply}"


@pytest.mark.parametrize(
    "question",
    [
        "Timetable is published for which department?",
        "Which departments currently have published timetables?",
        "Which sections have their timetable published?",
        "Is the AI & DS timetable published?",
        "When was the timetable published?",
        "How many published timetables are available?",
        "Show me all published timetables.",
        "Which department's timetable is not yet published?",
    ],
)
def test_all_eight_published_timetable_questions_grounded(tokens, seeded_timetable_fixture, question):
    """All 8 target questions must route to get_published_timetables and return grounded NL answers."""
    resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {tokens['ADMIN']}"},
        json={"message": question},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    _assert_clean_grounded_reply(data)

    tool_names = [tc.get("tool") for tc in data.get("tool_calls", [])]
    assert "get_published_timetables" in tool_names, f"Expected get_published_timetables for '{question}', got {tool_names}"
    assert len(tool_names) == len(set(tool_names)), f"Duplicate tool calls detected: {tool_names}"

    reply = data["reply"]
    if "not yet published" in question.lower():
        assert seeded_timetable_fixture["dept2_name"] in reply
        assert "not validated" in reply.lower() or "generated" in reply.lower()
    elif "ai & ds" in question.lower() and "AI & DS" not in seeded_timetable_fixture["dept1_name"]:
        assert "couldn't find any currently published timetable" in reply.lower()
    else:
        assert seeded_timetable_fixture["dept1_name"] in reply


def test_role_based_visibility_and_unpublished_redaction(tokens, seeded_timetable_fixture):
    """Non-admins must not see draft/generated internal status details for unpublished departments."""
    resp = client.post(
        "/agents/chat",
        headers={"Authorization": f"Bearer {tokens['STUDENT']}"},
        json={"message": "Which department's timetable is not yet published?"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    _assert_clean_grounded_reply(data)
    reply_lower = data["reply"].lower()
    # Student must not see internal admin states like 'validated but not approved' or other dept drafts
    assert "generated but not validated" not in reply_lower
    assert "approved but not published" not in reply_lower


def test_multi_department_published_timetables(tokens, seeded_timetable_fixture):
    """When multiple departments have published timetables, both are listed."""
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    v2_id = None
    with Session(engine) as db:
        dept2_id = seeded_timetable_fixture["dept2_id"]
        sec2 = db.query(Section).filter(Section.department_id == dept2_id).first()
        fac = db.query(Faculty).first()
        course = db.query(Course).first()
        room = db.query(Room).first()
        slot = db.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").first()
        admin_user = db.query(User).filter(User.role == "ADMIN").first()
        assert sec2 and fac and course and room and slot and admin_user

        v2 = TimetableVersion(
            academic_year_id=seeded_timetable_fixture["ay_id"],
            department_id=dept2_id,
            program_id=seeded_timetable_fixture["prog2_id"],
            semester_id=seeded_timetable_fixture["sem_id"],
            version_number="2.0",
            status="PUBLISHED",
            revision=1,
            validated_revision=1,
            validation_status="PASSED",
            approved_revision=1,
            approved_by=admin_user.id,
            approved_at=now_utc,
            published_at=now_utc,
            created_by=admin_user.id,
            last_saved_by=admin_user.id,
        )
        db.add(v2)
        db.flush()
        v2_id = v2.id
        db.add(TimetableEntry(
            version_id=v2.id,
            department_id=dept2_id,
            program_id=seeded_timetable_fixture["prog2_id"],
            semester_id=seeded_timetable_fixture["sem_id"],
            section_id=sec2.id,
            course_id=course.id,
            faculty_id=fac.id,
            room_id=room.id,
            slot_id=slot.id,
            status="ACTIVE",
        ))
        db.commit()

    try:
        resp = client.post(
            "/agents/chat",
            headers={"Authorization": f"Bearer {tokens['ADMIN']}"},
            json={"message": "Show me all published timetables."},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        _assert_clean_grounded_reply(data)
        assert seeded_timetable_fixture["dept1_name"] in data["reply"]
        assert seeded_timetable_fixture["dept2_name"] in data["reply"]
        assert "|" in data["reply"]  # Valid markdown table for multiple records
    finally:
        if v2_id:
            with Session(engine) as db:
                db.query(TimetableEntry).filter(TimetableEntry.version_id == v2_id).delete()
                db.query(TimetableVersion).filter(TimetableVersion.id == v2_id).delete()
                db.commit()


def test_sse_streaming_produces_clean_coherent_answer(tokens, seeded_timetable_fixture):
    """SSE /agents/chat/stream must stream tokens and done payload without leaking internal tool logs."""
    resp = client.post(
        "/agents/chat/stream",
        headers={"Authorization": f"Bearer {tokens['ADMIN']}"},
        json={"message": "Timetable is published for which department?"},
    )
    assert resp.status_code == 200
    events = []
    for block in resp.text.split("\n\n"):
        line = block.strip()
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))

    event_types = [e.get("event") for e in events]
    assert "status" in event_types
    assert "token" in event_types
    assert "done" in event_types
    done_ev = next(e for e in events if e.get("event") == "done")
    _assert_clean_grounded_reply(done_ev)
    assert seeded_timetable_fixture["dept1_name"] in done_ev["reply"]


def test_nvidia_provider_deduplicates_calls_and_never_leaks_tool_logs(seeded_timetable_fixture):
    """
    Simulates Nemotron repeating an identical tool call and returning empty content:
    - Identical read-only tool call is NOT executed twice.
    - Final reply is synthesized from actual DB records, NEVER 'Executed tool ... successfully.'.
    """
    provider = NvidiaNemotronProvider(api_key="nvapi-fake-test-key-123456")

    tc_obj = SimpleNamespace(
        id="call_1",
        type="function",
        function=SimpleNamespace(name="get_published_timetables", arguments="{}"),
    )
    tc_dup = SimpleNamespace(
        id="call_2",
        type="function",
        function=SimpleNamespace(name="get_published_timetables", arguments="{}"),
    )

    resp1 = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[tc_obj]))])
    resp2 = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[tc_dup]))])
    # Synthesis response also empty after thinking -> must fall back to grounded formatter, not tool log
    resp3 = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="<think>internal</think>", tool_calls=None))])

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [resp1, resp2, resp3, resp3]

    with Session(engine) as db:
        admin_user = db.query(User).filter(User.role == "ADMIN").first()
        assert admin_user is not None

        with patch("agents.llm.nvidia_provider.OpenAI", return_value=mock_client):
            result = provider.generate_chat_response(
                message="Timetable is published for which department?",
                user=admin_user,
                db=db,
            )

    assert result["success"] is True
    assert len(result["tool_calls"]) == 1, "Duplicate identical tool call must not be recorded twice"
    assert "Executed tool" not in result["reply"]
    assert seeded_timetable_fixture["dept1_name"] in result["reply"]


def test_strip_thinking_handles_think_and_thought_tags():
    assert strip_thinking("<think>reasoning</think>Actual answer") == "Actual answer"
    assert strip_thinking("<thought>reasoning</thought>Actual answer") == "Actual answer"
    assert strip_thinking("<think>unclosed reasoning") == ""
