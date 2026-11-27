"""
tests/api/test_role_aware_personal_timetable.py
------------------------------------------------
Regression tests for strict role-aware personal identity resolution in
get_next_class_data, get_my_timetable_data, get_first_class_tomorrow_data,
and /agents/chat/stream across STUDENT, FACULTY, ADMIN, and SUPER_ADMIN roles.
"""

from __future__ import annotations

import datetime
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from agents.tools.faculty_tools import get_next_class_data
from agents.tools.student_tools import get_first_class_tomorrow_data, get_my_timetable_data
from backend.config import engine
from backend.core.security import create_access_token
from backend.main import app
from backend.models import (
    AcademicCalendar,
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
    Timetable,
    TimetableEntry,
    TimetableVersion,
    User,
)

client = TestClient(app)


def _setup_two_section_published_fixture(db: Session):
    """Creates/fetches two isolated sections (sec_a, sec_b) with distinct faculty and published timetable."""
    ay = db.query(AcademicYear).first()
    assert ay is not None
    sem = db.query(Semester).first()
    assert sem is not None
    dept = db.query(Department).first()
    assert dept is not None
    prog = db.query(Program).first()
    assert prog is not None

    sections = db.query(Section).limit(2).all()
    assert len(sections) >= 2
    sec_a, sec_b = sections[0], sections[1]

    faculties = db.query(Faculty).limit(2).all()
    assert len(faculties) >= 2
    fac_a, fac_b = faculties[0], faculties[1]

    courses = db.query(Course).limit(2).all()
    assert len(courses) >= 2
    course_a, course_b = courses[0], courses[1]

    room = db.query(Room).first()
    assert room is not None

    # Ensure Monday 08:30-09:25 slot exists
    mon_slot = (
        db.query(TimeSlot)
        .filter(TimeSlot.day == "MON", TimeSlot.start_time == datetime.time(8, 30))
        .first()
    )
    if not mon_slot:
        mon_slot = TimeSlot(
            day="MON",
            start_time=datetime.time(8, 30),
            end_time=datetime.time(9, 25),
            slot_order=1,
            is_break=False,
        )
        db.add(mon_slot)
        db.flush()

    # Clear previous test timetable entries/versions/timetables
    db.query(TimetableEntry).delete()
    db.query(TimetableVersion).delete()
    db.query(Timetable).delete()
    db.commit()

    tv = TimetableVersion(
        academic_year_id=ay.id,
        version_number="v99",
        status="PUBLISHED",
        published_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
    )
    db.add(tv)
    db.flush()

    tt_a = Timetable(
        academic_year_id=ay.id,
        semester_id=sem.id,
        section_id=sec_a.id,
        status="PUBLISHED",
    )
    tt_b = Timetable(
        academic_year_id=ay.id,
        semester_id=sem.id,
        section_id=sec_b.id,
        status="PUBLISHED",
    )
    db.add_all([tt_a, tt_b])
    db.flush()

    e_a = TimetableEntry(
        timetable_id=tt_a.id,
        version_id=tv.id,
        department_id=dept.id,
        program_id=sec_a.program_id or prog.id,
        semester_id=sec_a.semester_id or sem.id,
        section_id=sec_a.id,
        course_id=course_a.id,
        faculty_id=fac_a.id,
        room_id=room.id,
        slot_id=mon_slot.id,
        status="ACTIVE",
    )
    e_b = TimetableEntry(
        timetable_id=tt_b.id,
        version_id=tv.id,
        department_id=dept.id,
        program_id=sec_b.program_id or prog.id,
        semester_id=sec_b.semester_id or sem.id,
        section_id=sec_b.id,
        course_id=course_b.id,
        faculty_id=fac_b.id,
        room_id=room.id,
        slot_id=mon_slot.id,
        status="ACTIVE",
    )
    db.add_all([e_a, e_b])
    db.commit()

    return {
        "tv": tv,
        "tt_a": tt_a,
        "tt_b": tt_b,
        "sec_a": sec_a,
        "sec_b": sec_b,
        "fac_a": fac_a,
        "fac_b": fac_b,
        "course_a": course_a,
        "course_b": course_b,
        "mon_slot": mon_slot,
    }


def test_student_receives_only_own_section_next_class():
    with Session(engine) as db:
        fx = _setup_two_section_published_fixture(db)
        stu_a = db.query(Student).filter(Student.section_id == fx["sec_a"].id).first()
        stu_b = db.query(Student).filter(Student.section_id == fx["sec_b"].id).first()
        assert stu_a is not None and stu_b is not None

        user_a = db.query(User).filter(User.id == stu_a.user_id).first()
        user_b = db.query(User).filter(User.id == stu_b.user_id).first()
        assert user_a is not None and user_b is not None

        # Monday 07:30 -> upcoming class at 08:30
        ref_dt = datetime.datetime(2026, 11, 30, 7, 30)
        res_a = get_next_class_data(db, user_a, ref_datetime=ref_dt)
        res_b = get_next_class_data(db, user_b, ref_datetime=ref_dt)

        assert res_a["found"] is True
        assert res_a["section"] == fx["sec_a"].section_name
        assert res_a["subject_code"] == fx["course_a"].course_code

        assert res_b["found"] is True
        assert res_b["section"] == fx["sec_b"].section_name
        assert res_b["subject_code"] == fx["course_b"].course_code
        assert res_a["subject_code"] != res_b["subject_code"]


def test_faculty_receives_only_assigned_teaching_next_class():
    with Session(engine) as db:
        fx = _setup_two_section_published_fixture(db)
        user_fa = db.query(User).filter(User.id == fx["fac_a"].user_id).first()
        user_fb = db.query(User).filter(User.id == fx["fac_b"].user_id).first()
        assert user_fa is not None and user_fb is not None

        ref_dt = datetime.datetime(2026, 11, 30, 7, 30)
        res_fa = get_next_class_data(db, user_fa, ref_datetime=ref_dt)
        res_fb = get_next_class_data(db, user_fb, ref_datetime=ref_dt)

        assert res_fa["found"] is True
        assert res_fa["resolved_profile_type"] == "faculty"
        assert res_fa["subject_code"] == fx["course_a"].course_code

        assert res_fb["found"] is True
        assert res_fb["resolved_profile_type"] == "faculty"
        assert res_fb["subject_code"] == fx["course_b"].course_code


def test_admin_without_personal_profile_never_receives_random_class():
    with Session(engine) as db:
        _setup_two_section_published_fixture(db)
        admin = db.query(User).filter(User.role == "ADMIN").first()
        assert admin is not None
        # Ensure no linked profile on admin
        assert db.query(Faculty).filter(Faculty.user_id == admin.id).first() is None
        assert db.query(Student).filter(Student.user_id == admin.id).first() is None

        ref_dt = datetime.datetime(2026, 11, 30, 7, 30)
        res = get_next_class_data(db, admin, ref_datetime=ref_dt)
        assert res["found"] is False
        assert res["has_personal_schedule"] is False
        assert res["needs_clarification"] is True
        assert "personal class schedule" in res["message"].lower()

        res_my = get_my_timetable_data(db, admin)
        assert res_my["has_personal_schedule"] is False
        assert res_my["entries"] == []

        res_tmrw = get_first_class_tomorrow_data(db, admin)
        assert res_tmrw["has_class"] is False
        assert res_tmrw["has_personal_schedule"] is False


def test_super_admin_without_personal_profile_never_receives_random_class():
    with Session(engine) as db:
        _setup_two_section_published_fixture(db)
        sa = db.query(User).filter(User.role == "SUPER_ADMIN").first()
        assert sa is not None

        res = get_next_class_data(db, sa, ref_datetime=datetime.datetime(2026, 11, 30, 7, 30))
        assert res["found"] is False
        assert res["has_personal_schedule"] is False
        assert res["needs_clarification"] is True


def test_admin_with_linked_faculty_profile_receives_only_own_teaching_class():
    with Session(engine) as db:
        fx = _setup_two_section_published_fixture(db)
        admin = db.query(User).filter(User.role == "ADMIN").first()
        assert admin is not None

        # Temporarily link fac_b to admin user_id
        orig_uid = fx["fac_b"].user_id
        try:
            fx["fac_b"].user_id = admin.id
            db.commit()

            res = get_next_class_data(db, admin, ref_datetime=datetime.datetime(2026, 11, 30, 7, 30))
            assert res["found"] is True
            assert res["resolved_profile_type"] == "faculty"
            assert res["subject_code"] == fx["course_b"].course_code
            assert res["section"] == fx["sec_b"].section_name
        finally:
            fx["fac_b"].user_id = orig_uid
            db.commit()


def test_missing_profile_returns_safe_no_personal_schedule():
    with Session(engine) as db:
        _setup_two_section_published_fixture(db)
        orphan_stu = User(
            name="Orphan Student",
            email="orphan_stu@rio.test",
            password_hash="x",
            role="STUDENT",
        )
        orphan_fac = User(
            name="Orphan Faculty",
            email="orphan_fac@rio.test",
            password_hash="x",
            role="FACULTY",
        )
        db.add_all([orphan_stu, orphan_fac])
        db.flush()

        res_s = get_next_class_data(db, orphan_stu, ref_datetime=datetime.datetime(2026, 11, 30, 7, 30))
        res_f = get_next_class_data(db, orphan_fac, ref_datetime=datetime.datetime(2026, 11, 30, 7, 30))
        assert res_s["found"] is False and res_s["has_personal_schedule"] is False
        assert res_f["found"] is False and res_f["has_personal_schedule"] is False
        db.rollback()


def test_recalled_and_archived_timetables_never_returned():
    with Session(engine) as db:
        fx = _setup_two_section_published_fixture(db)
        stu_a = db.query(Student).filter(Student.section_id == fx["sec_a"].id).first()
        assert stu_a is not None
        user_a = db.query(User).filter(User.id == stu_a.user_id).first()
        assert user_a is not None

        # Mark Timetable A as RECALLED
        fx["tt_a"].status = "RECALLED"
        db.commit()
        res_recalled = get_next_class_data(db, user_a, ref_datetime=datetime.datetime(2026, 11, 30, 7, 30))
        assert res_recalled["found"] is False

        # Mark Version as ARCHIVED
        fx["tt_a"].status = "PUBLISHED"
        fx["tv"].status = "ARCHIVED"
        db.commit()
        res_archived = get_next_class_data(db, user_a, ref_datetime=datetime.datetime(2026, 11, 30, 7, 30))
        assert res_archived["found"] is False


def test_holiday_and_empty_upcoming_schedule_handled_safely():
    with Session(engine) as db:
        fx = _setup_two_section_published_fixture(db)
        stu_a = db.query(Student).filter(Student.section_id == fx["sec_a"].id).first()
        assert stu_a is not None
        user_a = db.query(User).filter(User.id == stu_a.user_id).first()
        assert user_a is not None

        # Mark Monday 2026-11-30 as HOLIDAY
        cal = AcademicCalendar(
            academic_year_id=fx["tv"].academic_year_id,
            date=datetime.date(2026, 11, 30),
            event_type="HOLIDAY",
            description="Test Holiday",
        )
        db.add(cal)
        db.commit()
        try:
            # Should NOT return 2026-11-30; only Monday entry exists, and next Monday is +7 days (2026-12-07)
            res = get_next_class_data(db, user_a, ref_datetime=datetime.datetime(2026, 11, 30, 7, 30))
            if res["found"]:
                assert res["date"] != "2026-11-30"
        finally:
            db.delete(cal)
            db.commit()


def test_chat_stream_my_next_class_admin_gets_clarification(monkeypatch):
    monkeypatch.setenv("RIO_CHAT_LLM_ENABLED", "true")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key-0001")

    with Session(engine) as db:
        _setup_two_section_published_fixture(db)
        admin = db.query(User).filter(User.role == "ADMIN").first()
        assert admin is not None
        tok = create_access_token({"sub": str(admin.id), "role": admin.role})

    tc = SimpleNamespace(id="c1", type="function", function=SimpleNamespace(name="get_next_class", arguments="{}"))
    r1 = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[tc]))])
    r2 = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="I don't have a personal class schedule linked to your Admin account. Are you asking about a teaching schedule or a particular section?",
                    tool_calls=None,
                )
            )
        ]
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [r1, r2]

    with patch("agents.llm.nvidia_provider.OpenAI", return_value=mock_client):
        resp = client.post(
            "/agents/chat/stream",
            headers={"Authorization": f"Bearer {tok}"},
            json={"message": "my next class?"},
        )

    assert resp.status_code == 200
    events = [
        json.loads(b.strip()[5:].strip())
        for b in resp.text.replace("\r\n", "\n").split("\n\n")
        if b.strip().startswith("data:")
    ]
    done = events[-1]
    assert done["event"] == "done"
    assert "personal class schedule" in done["reply"].lower()
    assert "B23ASO711" not in done["reply"]
