"""
tests/api/test_settings_and_browser_diagnostics.py
--------------------------------------------------
Unit and regression tests verifying:
- Safe handling of nullable Playwright locator text.
- Validation and rejection of missing/whitespace browser credentials.
- BreakPeriod normalization and schema validation without dictionary unpacking errors.
- Strict type deserialization for TimetableSettingsResponse (working_days, periods, bools, etc.).
- Preservation of authoritative REVA schedule (Tea Break: 10:20-10:40, Lunch Break: 12:30-13:30).
- Safe fallback when settings in database contain corrupted or malformed types.
"""

import pytest
from unittest.mock import MagicMock

from backend.database import SessionLocal
from backend.models.identity import User
from backend.models.system_setting import SystemSetting
from backend.schemas.settings import BreakPeriod, TimetableSettingsResponse, TimetableSettingsUpdate
from backend.services.settings_service import (
    DEFAULT_TIMETABLE,
    _deserialize_bool,
    _deserialize_break_periods,
    _deserialize_positive_int,
    _deserialize_working_days,
    _normalize_break_period,
    get_timetable_settings,
    update_timetable_settings,
)
from scripts.verify_global_refresh_and_feedback_live import (
    BrowserAuditConfig,
    extract_locator_text,
    validate_credential,
)


# ── 1. Browser Configuration & Nullable Text Extraction Tests ────────────────

def test_validate_credential_valid():
    assert validate_credential("ADMIN_EMAIL", "admin@campus.edu") == "admin@campus.edu"
    assert validate_credential("TRIMMED", "  secret  ") == "secret"


@pytest.mark.parametrize("invalid_val", [None, "", "   ", "\t\n"])
def test_validate_credential_missing_or_whitespace_raises(invalid_val):
    with pytest.raises(ValueError, match="is required and cannot be missing, empty, or whitespace-only"):
        validate_credential("TEST_KEY", invalid_val)


def test_browser_audit_config_valid(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "http://127.0.0.1:5173")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@campus.edu")
    monkeypatch.setenv("ADMIN_PASSWORD", "Admin#RioLocal26")
    monkeypatch.setenv("FACULTY_EMAIL", "faculty@campus.edu")
    monkeypatch.setenv("FACULTY_PASSWORD", "Faculty#RioLocal26")
    monkeypatch.setenv("STUDENT_EMAIL", "student@campus.edu")
    monkeypatch.setenv("STUDENT_PASSWORD", "Student#RioLocal26")

    cfg = BrowserAuditConfig.load()
    assert cfg.frontend_url == "http://127.0.0.1:5173"
    assert cfg.admin_email == "admin@campus.edu"
    assert cfg.student_email == "student@campus.edu"


def test_browser_audit_config_empty_env_var_raises(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "   ")
    with pytest.raises(ValueError, match="ADMIN_EMAIL"):
        BrowserAuditConfig.load()


def test_extract_locator_text_safely():
    # Valid text
    loc_valid = MagicMock()
    loc_valid.text_content.return_value = "  Success! Refresh completed.  "
    assert extract_locator_text(loc_valid) == "Success! Refresh completed."

    # None text content (must not raise AttributeError)
    loc_none = MagicMock()
    loc_none.text_content.return_value = None
    assert extract_locator_text(loc_none, fallback="Fallback") == "Fallback"

    # Exception thrown by locator
    loc_err = MagicMock()
    loc_err.text_content.side_effect = RuntimeError("Element detached")
    assert extract_locator_text(loc_err, fallback="SafeFallback") == "SafeFallback"


# ── 2. BreakPeriod Normalization & REVA Schedule Preservation ───────────────

def test_normalize_break_period_valid():
    result = _normalize_break_period({"name": "Tea Break", "start": "10:20", "end": "10:40"})
    assert isinstance(result, BreakPeriod)
    assert result.name == "Tea Break"
    assert result.start == "10:20"
    assert result.end == "10:40"


@pytest.mark.parametrize("malformed", [
    None,
    True,
    123,
    "string_not_dict",
    {},
    {"name": "Tea Break"},
    {"name": "Tea Break", "start": "10:20"},
    {"name": "", "start": "10:20", "end": "10:40"},
    {"name": "Lunch", "start": "", "end": "13:30"},
    {"name": "Lunch", "start": "12:30", "end": "   "},
    {"name": 123, "start": "12:30", "end": "13:30"},
])
def test_normalize_break_period_malformed_returns_none(malformed):
    assert _normalize_break_period(malformed) is None


def test_deserialize_break_periods_valid():
    raw = [
        {"name": "Morning Break", "start": "10:15", "end": "10:35"},
        {"name": "Lunch Break", "start": "12:30", "end": "13:30"},
    ]
    breaks = _deserialize_break_periods(raw)
    assert len(breaks) == 2
    assert breaks[0].name == "Morning Break"
    assert breaks[1].name == "Lunch Break"


@pytest.mark.parametrize("corrupted_input", [
    None,
    True,
    False,
    42,
    "not a list",
    [],
    [{"bad": "data"}],
    [True, 123, "text"],
])
def test_deserialize_break_periods_corrupted_defaults_to_reva_schedule(corrupted_input):
    breaks = _deserialize_break_periods(corrupted_input)
    assert len(breaks) == 2
    assert breaks[0].name == "Tea Break"
    assert breaks[0].start == "10:20"
    assert breaks[0].end == "10:40"
    assert breaks[1].name == "Lunch Break"
    assert breaks[1].start == "12:30"
    assert breaks[1].end == "13:30"


# ── 3. Typed Deserializers (Working Days, Integers, Booleans) ───────────────

@pytest.mark.parametrize("input_val, expected", [
    ("MON_SAT", "MON_SAT"),
    ("MON_FRI", "MON_FRI"),
    ("mon_sat", "MON_SAT"),
    ("  mon_fri  ", "MON_FRI"),
    ("INVALID_DAYS", "MON_SAT"),
    (None, "MON_SAT"),
    (123, "MON_SAT"),
    (True, "MON_SAT"),
])
def test_deserialize_working_days(input_val, expected):
    assert _deserialize_working_days(input_val, default="MON_SAT") == expected


@pytest.mark.parametrize("input_val, expected", [
    (7, 7),
    (55, 55),
    (3, 3),
    ("7", 7),
    ("  55  ", 55),
    (0, 7),        # non-positive returns default
    (-5, 7),       # negative returns default
    (True, 7),     # boolean rejected as integer
    (False, 7),
    ("invalid", 7),
    (None, 7),
])
def test_deserialize_positive_int(input_val, expected):
    assert _deserialize_positive_int(input_val, default=7) == expected


@pytest.mark.parametrize("input_val, expected", [
    (True, True),
    (False, False),
    ("true", True),
    ("True", True),
    ("1", True),
    ("yes", True),
    ("false", False),
    ("False", False),
    ("0", False),
    ("no", False),
    (None, True),
    (123, True),
])
def test_deserialize_bool(input_val, expected):
    assert _deserialize_bool(input_val, default=True) == expected


# ── 4. Database-backed Timetable Settings Safe Recovery ───────────────────────

def test_get_timetable_settings_handles_corrupted_db_value():
    with SessionLocal() as db:
        admin_user = db.query(User).filter(User.role == "ADMIN").first()
        assert admin_user is not None

        # Intentionally inject corrupted types into the setting
        setting = db.query(SystemSetting).filter(SystemSetting.key == "timetable_defaults").first()
        if not setting:
            setting = SystemSetting(
                key="timetable_defaults",
                category="TIMETABLE",
                value={},
                description="Test setting",
            )
            db.add(setting)

        setting.value = {
            "working_days": 12345,                           # invalid type
            "periods_per_day": "not_an_int",                 # invalid type
            "period_duration_minutes": True,                 # bool instead of int
            "break_times": True,                             # bool instead of list!
            "max_consecutive_faculty_lectures": -10,         # invalid negative int
            "enable_soft_lab_preference": "invalid_bool",    # unparseable bool
        }
        db.commit()

        # get_timetable_settings must safely recover to defaults without raising TypeError
        res = get_timetable_settings(db)
        assert isinstance(res, TimetableSettingsResponse)
        assert res.working_days == "MON_SAT"
        assert res.periods_per_day == 7
        assert res.period_duration_minutes == 55
        assert len(res.break_times) == 2
        assert res.break_times[0].name == "Tea Break"
        assert res.break_times[0].start == "10:20"
        assert res.break_times[0].end == "10:40"
        assert res.break_times[1].name == "Lunch Break"
        assert res.break_times[1].start == "12:30"
        assert res.break_times[1].end == "13:30"
        assert res.max_consecutive_faculty_lectures == 3
        assert res.enable_soft_lab_preference is True

        # Clean update to valid state
        updated = update_timetable_settings(
            db,
            TimetableSettingsUpdate(
                working_days="MON_FRI",
                max_consecutive_faculty_lectures=2,
                enable_soft_lab_preference=False,
            ),
            admin_user,
        )
        assert updated.working_days == "MON_FRI"
        assert updated.max_consecutive_faculty_lectures == 2
        assert updated.enable_soft_lab_preference is False

        # Reset back to MON_SAT for canonical schedule
        reset = update_timetable_settings(
            db,
            TimetableSettingsUpdate(
                working_days="MON_SAT",
                max_consecutive_faculty_lectures=3,
                enable_soft_lab_preference=True,
            ),
            admin_user,
        )
        assert reset.working_days == "MON_SAT"
        assert reset.max_consecutive_faculty_lectures == 3
        assert reset.enable_soft_lab_preference is True
