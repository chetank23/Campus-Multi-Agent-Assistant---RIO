"""
agents/resource_agent/parser.py
--------------------------------
Natural-language entity extraction for Resource Agent:
- Date resolution (relative: today, tomorrow, day of week; absolute: YYYY-MM-DD, Month DD)
- Time interval resolution (start time, end time, duration)
- Resource identifier / type extraction
- Capacity and purpose extraction
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, Optional, Tuple


WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

RESOURCE_TYPE_MAP = {
    "seminar hall": "SEMINAR_HALL",
    "seminar_hall": "SEMINAR_HALL",
    "seminar": "SEMINAR_HALL",
    "conference hall": "SEMINAR_HALL",
    "conference room": "SEMINAR_HALL",
    "lab": "LAB",
    "laboratory": "LAB",
    "computer lab": "LAB",
    "auditorium": "AUDITORIUM",
    "audi": "AUDITORIUM",
    "projector": "PROJECTOR",
    "equipment": "EQUIPMENT",
    "classroom": "CLASSROOM",
    "room": "CLASSROOM",
}


def parse_date(text: str, base_date: Optional[datetime.date] = None) -> Optional[datetime.date]:
    """
    Parses natural language date string into datetime.date.
    Supports:
    - 'today'
    - 'tomorrow'
    - 'next monday', 'this friday', 'wednesday'
    - 'YYYY-MM-DD', 'DD-MM-YYYY'
    - '20th Oct', 'October 25', 'Nov 5 2026'
    """
    text_lower = text.lower()
    today = base_date or datetime.date.today()

    if "today" in text_lower:
        return today

    if "tomorrow" in text_lower:
        return today + datetime.timedelta(days=1)

    # ISO Format: YYYY-MM-DD
    iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if iso_match:
        try:
            return datetime.date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
        except ValueError:
            pass

    # DD/MM/YYYY or DD-MM-YYYY
    dmy_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
    if dmy_match:
        try:
            return datetime.date(int(dmy_match.group(3)), int(dmy_match.group(2)), int(dmy_match.group(1)))
        except ValueError:
            pass

    # Month Name + Day: e.g. "Oct 25", "October 25, 2026", "25th October"
    month_pattern = r"\b(" + "|".join(MONTHS.keys()) + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?\b"
    m_match = re.search(month_pattern, text_lower)
    if m_match:
        m_name = m_match.group(1)
        day_num = int(m_match.group(2))
        year_num = int(m_match.group(3)) if m_match.group(3) else today.year
        month_num = MONTHS[m_name]
        try:
            return datetime.date(year_num, month_num, day_num)
        except ValueError:
            pass

    # Day + Month Name: e.g. "25th Oct", "25 October"
    day_month_pattern = r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS.keys()) + r")(?:\s*,?\s*(\d{4}))?\b"
    dm_match = re.search(day_month_pattern, text_lower)
    if dm_match:
        day_num = int(dm_match.group(1))
        m_name = dm_match.group(2)
        year_num = int(dm_match.group(3)) if dm_match.group(3) else today.year
        month_num = MONTHS[m_name]
        try:
            return datetime.date(year_num, month_num, day_num)
        except ValueError:
            pass

    # Weekdays: e.g. "on Monday", "this Friday", "next Tuesday"
    for day_name, weekday_idx in WEEKDAYS.items():
        if re.search(rf"\b(this\s+|next\s+|on\s+)?{day_name}\b", text_lower):
            days_ahead = (weekday_idx - today.weekday()) % 7
            if days_ahead == 0 and ("next" in text_lower or today.weekday() == weekday_idx):
                days_ahead = 7
            return today + datetime.timedelta(days=days_ahead)

    return None


def parse_time_str(time_str: str) -> Optional[datetime.time]:
    """
    Converts individual time token (e.g. '2pm', '14:00', '10:30am', '9') into datetime.time.
    """
    clean = time_str.lower().strip()

    # 12-hour format with am/pm (e.g. '2:30pm', '2pm', '11am')
    ampm_match = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", clean)
    if ampm_match:
        hour = int(ampm_match.group(1))
        minute = int(ampm_match.group(2) or 0)
        ampm = ampm_match.group(3)

        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return datetime.time(hour, minute)

    # 24-hour format: '14:00', '09:30'
    colon_match = re.match(r"^(\d{1,2}):(\d{2})$", clean)
    if colon_match:
        hour = int(colon_match.group(1))
        minute = int(colon_match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return datetime.time(hour, minute)

    return None


def parse_time_interval(text: str) -> Tuple[Optional[datetime.time], Optional[datetime.time]]:
    """
    Extracts (start_time, end_time) from natural language text.
    Patterns:
    - 'from 2pm to 4pm', '2pm to 4pm', '2:00 PM - 4:00 PM'
    - 'from 10:00 to 12:00', '10:00 - 12:00'
    - 'between 9am and 11am'
    - 'at 2pm for 2 hours', 'from 10am for 1 hour'
    """
    text_lower = text.lower()

    # Mask full dates (e.g. 2026-10-25 or 25-10-2026) so their hyphens/numbers don't interfere with time range matching
    cleaned = re.sub(r"\b\d{4}-\d{1,2}-\d{1,2}\b", " ", text_lower)
    cleaned = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b", " ", cleaned)

    # Pattern A: Standard range: "<start> (to|-|until|through) <end>"
    # E.g. "10:00 am to 12:00 pm", "2pm - 4pm", "14:00 to 16:00", "2 to 4 pm"
    range_pattern = r"\b(?:from\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:to|-|until|through|and)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b"
    m = re.search(range_pattern, cleaned)
    if m:
        start_str = m.group(1).strip()
        end_str = m.group(2).strip()

        # Handle inherited am/pm (e.g. "2 to 4 pm" -> start is 2 pm)
        if ("pm" in end_str or "am" in end_str) and not ("pm" in start_str or "am" in start_str):
            ampm = "pm" if "pm" in end_str else "am"
            start_str += ampm

        start_t = parse_time_str(start_str)
        end_t = parse_time_str(end_str)

        if start_t and end_t:
            return start_t, end_t

    # Pattern B: Duration based: "at <start> for <N> hour(s)" or "from <start> for <N> hour(s)"
    duration_pattern = r"\b(?:at|from)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+for\s+(\d+(?:\.\d+)?)\s*(?:hour|hr|hours|hrs)\b"
    m_dur = re.search(duration_pattern, cleaned)
    if m_dur:
        start_str = m_dur.group(1).strip()
        duration_hrs = float(m_dur.group(2))
        start_t = parse_time_str(start_str)
        if start_t:
            start_dt = datetime.datetime.combine(datetime.date.today(), start_t)
            end_dt = start_dt + datetime.timedelta(hours=duration_hrs)
            return start_t, end_dt.time()

    return None, None


def extract_resource_details(text: str) -> Dict[str, Any]:
    """
    Extracts resource name, type, capacity, and purpose from natural language text.
    """
    text_lower = text.lower()
    res_details: Dict[str, Any] = {
        "resource_name": None,
        "resource_type": None,
        "resource_id": None,
        "min_capacity": None,
        "purpose": None,
    }

    # Resource ID direct reference: "resource #12", "resource id 5"
    id_match = re.search(r"\bresource\s+(?:id\s+|#)?(\d+)\b", text_lower)
    if id_match:
        res_details["resource_id"] = int(id_match.group(1))

    # Detect Resource Type
    for key, r_type in RESOURCE_TYPE_MAP.items():
        if re.search(rf"\b{re.escape(key)}s?\b", text_lower):
            res_details["resource_type"] = r_type
            break

    # Detect Named Resource Candidates (e.g. "Seminar Hall A", "CSE Lab 1", "Auditorium 1", "Room 101")
    # Negative lookahead ensures prepositions like 'on', 'at', 'from' are not captured as name suffixes
    name_patterns = [
        r"\b(seminar\s+hall\s+(?!(?:on|at|from|for|in|with|by|to|available|free|booked|open|vacant|needed|wanted)\b)[a-zA-Z0-9_-]+)\b",
        r"\b(cse\s+lab\s+(?!(?:on|at|from|for|in|with|by|to|available|free|booked|open|vacant|needed|wanted)\b)[a-zA-Z0-9_-]+)\b",
        r"\b(lab\s+(?!(?:on|at|from|for|in|with|by|to|available|free|booked|open|vacant|needed|wanted)\b)[a-zA-Z0-9_-]+)\b",
        r"\b(auditorium\s+(?!(?:on|at|from|for|in|with|by|to|available|free|booked|open|vacant|needed|wanted)\b)[a-zA-Z0-9_-]+)\b",
        r"\b(room\s+(?!(?:on|at|from|for|in|with|by|to|available|free|booked|open|vacant|needed|wanted)\b)[a-zA-Z0-9_-]+)\b",
        r"\b(main\s+auditorium)\b",
        r"\b(portable\s+projector\s+[0-9]+)\b",
    ]
    for np in name_patterns:
        m = re.search(np, text_lower)
        if m:
            res_details["resource_name"] = m.group(1).title()
            break

    # Capacity extraction: "capacity 50", "capacity of 100", "for 60 students", "50 seats"
    cap_patterns = [
        r"\bcapacity\s*(?:of|>=|:)?\s*(\d+)\b",
        r"\bfor\s+(\d+)\s*(?:students|people|seats|attendees)\b",
        r"\b(\d+)\s*(?:seats|capacity)\b",
    ]
    for cp in cap_patterns:
        cm = re.search(cp, text_lower)
        if cm:
            res_details["min_capacity"] = int(cm.group(1))
            break

    # Purpose extraction: "for <purpose>", e.g. "for AI workshop", "for guest lecture"
    # Make sure we don't grab "for 2 hours" or "for 50 students"
    purpose_match = re.search(r"\bfor\s+(?!\d+\s*(?:hour|hr|student|seat|people))([a-zA-Z0-9\s,.-]+)$", text, re.IGNORECASE)
    if purpose_match:
        candidate_purpose = purpose_match.group(1).strip()
        # Clean up any trailing punctuation or date words if present
        candidate_purpose = re.sub(r"\b(on|at|from)\b.*$", "", candidate_purpose, flags=re.IGNORECASE).strip()
        if len(candidate_purpose) >= 3:
            res_details["purpose"] = candidate_purpose

    return res_details
