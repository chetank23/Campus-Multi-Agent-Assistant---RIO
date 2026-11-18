"""
tests/api/test_timetable_input_loader.py
----------------------------------------
Unit tests for timetable input loading and type validation safeguards.
"""

import pytest
from backend.schemas.timetable_generation import OptFacultyAvailability


def test_opt_faculty_availability_rejects_none_ids():
    """OptFacultyAvailability requires concrete int IDs for faculty_id and slot_id."""
    with pytest.raises(Exception):
        OptFacultyAvailability(
            id=1,
            faculty_id=None,  # type: ignore
            slot_id=1,
            availability="UNAVAILABLE",
            preference=0,
        )

    with pytest.raises(Exception):
        OptFacultyAvailability(
            id=2,
            faculty_id=1,
            slot_id=None,  # type: ignore
            availability="UNAVAILABLE",
            preference=0,
        )


def test_busy_slots_filtering_skips_none_pairs():
    """Simulates the timetable_input_loader external_busy_slots loop."""
    opt_fa: list[OptFacultyAvailability] = []
    external_busy_slots = [
        (None, 10),
        (5, None),
        (None, None),
        (101, 201),
        (102, 202),
    ]

    for b_fid, b_sid in external_busy_slots:
        if b_fid is None or b_sid is None:
            continue
        match_fa = next((fa for fa in opt_fa if fa.faculty_id == b_fid and fa.slot_id == b_sid), None)
        if match_fa:
            match_fa.availability = "UNAVAILABLE"
        else:
            opt_fa.append(
                OptFacultyAvailability(
                    id=990000 + len(opt_fa),
                    faculty_id=b_fid,
                    slot_id=b_sid,
                    availability="UNAVAILABLE",
                    preference=0,
                )
            )

    # Only valid non-null pairs should have been created
    assert len(opt_fa) == 2
    assert opt_fa[0].faculty_id == 101
    assert opt_fa[0].slot_id == 201
    assert opt_fa[1].faculty_id == 102
    assert opt_fa[1].slot_id == 202
