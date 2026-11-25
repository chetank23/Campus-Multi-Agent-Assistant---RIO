"""
agents/common/context_resolver.py
---------------------------------
Multi-turn conversational context resolver.
Inspects previous turns in the active conversation session to resolve:
1. Follow-up temporal filters ("what about tomorrow", "and on friday", "next week")
2. Follow-up ordinal entity references ("the first one", "who teaches the second course", "tell me about the last one")
3. Follow-up pronouns and subject continuity ("who teaches it", "where is it located", "what courses does she teach")
4. Section and department scope continuity ("show AIDS-A courses" -> "show the timetable")

Never bypasses authorization or leaks context across conversations or users.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


def extract_contextual_follow_up(
    message: str,
    conversation_history: List[Dict[str, Any]],
    current_role: str,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Evaluates whether the user's message is a follow-up referring to previous turn state.
    Returns (tool_name, tool_args) or None if message is a fresh standalone query.
    """
    if not conversation_history:
        return None

    msg = message.lower().strip()

    # Find last assistant message and last user message
    last_assistant_msg: Optional[Dict[str, Any]] = None
    last_user_msg: Optional[Dict[str, Any]] = None

    for m in reversed(conversation_history):
        if m.get("sender") == "assistant" and not last_assistant_msg:
            last_assistant_msg = m
        elif m.get("sender") == "user" and not last_user_msg:
            last_user_msg = m
        if last_assistant_msg and last_user_msg:
            break

    if not last_assistant_msg:
        return None

    last_content = last_assistant_msg.get("content", "")
    last_intent = last_assistant_msg.get("intent", "")
    last_tool_calls = last_assistant_msg.get("tool_calls", [])
    last_tool_name = last_tool_calls[0].get("tool") if last_tool_calls else None
    last_tool_args = last_tool_calls[0].get("args", {}) if last_tool_calls else {}

    # ── 0. Faculty Availability Multi-Turn Follow-up ──────────────────────────
    is_prev_fac_avail = (
        last_tool_name == "get_available_faculty"
        or "faculty availability" in last_content.lower()
        or "for which date and time interval" in last_content.lower()
        or ("available faculty" in last_content.lower() and last_tool_name == "get_available_faculty")
    )
    if is_prev_fac_avail:
        from agents.resource_agent.parser import parse_date, parse_time_interval
        from agents.intent.intent_catalog import extract_entities

        req_date = parse_date(message)
        start_t, end_t = parse_time_interval(message)
        ents = extract_entities(message)
        dept_name = ents.get("department_name")

        # Only treat as follow-up if user supplied a date, time, or department/scope refinement
        if req_date or (start_t and end_t) or dept_name:
            merged_args: Dict[str, Any] = dict(last_tool_args) if last_tool_name == "get_available_faculty" else {}
            if req_date:
                merged_args["date"] = req_date.isoformat()
            elif not merged_args.get("date") and last_user_msg:
                prev_d = parse_date(last_user_msg.get("content", ""))
                if prev_d:
                    merged_args["date"] = prev_d.isoformat()

            if start_t and end_t:
                merged_args["start_time"] = start_t.strftime("%H:%M")
                merged_args["end_time"] = end_t.strftime("%H:%M")
            elif (not merged_args.get("start_time") or not merged_args.get("end_time")) and last_user_msg:
                p_st, p_et = parse_time_interval(last_user_msg.get("content", ""))
                if p_st and p_et:
                    merged_args["start_time"] = p_st.strftime("%H:%M")
                    merged_args["end_time"] = p_et.strftime("%H:%M")

            if dept_name:
                merged_args["department_name"] = dept_name

            if merged_args.get("date") and merged_args.get("start_time") and merged_args.get("end_time"):
                return "get_available_faculty", merged_args
            elif merged_args.get("date"):
                return "ambiguous_clarification", {
                    "prompt": f"For which time interval on {merged_args['date']} should I check faculty availability? (e.g., '2 PM to 3 PM')"
                }
            elif merged_args.get("start_time") and merged_args.get("end_time"):
                return "ambiguous_clarification", {
                    "prompt": f"For which date should I check faculty availability from {merged_args['start_time']} to {merged_args['end_time']}?"
                }

    # ── 1. Temporal Follow-Up: "what about tomorrow?", "how about friday?", "on wednesday?"
    day_match = None
    if "today" in msg:
        day_match = "TODAY"
    elif "tomorrow" in msg:
        day_match = "TOMORROW"
    else:
        for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]:
            if d in msg:
                day_match = d.upper()
                break

    is_pure_day_switch = any(
        re.search(pat, msg)
        for pat in [
            r"^(?:what\s+about|how\s+about|and|classes\s+on|schedule\s+on)?\s*(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday)\??$",
            r"^what\s+about\s+(?:tomorrow|friday|monday|tuesday|wednesday|thursday|saturday)\??$",
            r"^how\s+about\s+(?:tomorrow|friday|monday|tuesday|wednesday|thursday|saturday)\??$",
        ]
    )

    if day_match and (is_pure_day_switch or len(msg.split()) <= 4):
        # Check what the previous query was
        if last_tool_name in ("get_my_timetable", "get_student_timetable"):
            return "get_my_timetable", {"day": day_match}
        elif last_tool_name in ("get_faculty_timetable", "get_faculty_schedule"):
            return "get_faculty_timetable", {**last_tool_args, "day": day_match}
        elif last_tool_name in ("get_section_timetable", "get_department_timetable"):
            return "get_section_timetable", {**last_tool_args, "day": day_match}

    # ── 2. Ordinal Reference: "who teaches the first one?", "the second course", "who teaches the first course"
    ordinal_match = re.search(r"\b(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|last)\b", msg)
    if ordinal_match and any(k in msg for k in ["who teaches", "who is the teacher", "faculty for", "instructor", "professor", "tell me about"]):
        ord_word = ordinal_match.group(1).lower()
        ord_idx = 0
        if ord_word in ("second", "2nd"):
            ord_idx = 1
        elif ord_word in ("third", "3rd"):
            ord_idx = 2
        elif ord_word in ("fourth", "4th"):
            ord_idx = 3
        elif ord_word in ("fifth", "5th"):
            ord_idx = 4
        elif ord_word == "last":
            ord_idx = -1

        # Extract items listed in last_content
        # Patterns like: - B25CS0701 - Principles of Federated Learning OR | **EE614** | Intro ... | OR 1. ...
        courses_found = []
        for line in last_content.splitlines():
            line_str = line.strip()
            if line_str.startswith("|:") or "Code |" in line_str or "Course Title" in line_str:
                continue
            m_code = re.search(r"\b([A-Z]{2,4}\s*\d{3,4}[A-Z]?|[A-Z0-9]{4,12})\b", line_str)
            if line_str.startswith("|") and ("**" in line_str or m_code):
                courses_found.append(line_str)
            elif m_code and any(k in line_str.lower() for k in ["course", "subject", "-", "credits", "federated", "learning", "internship", "project", "elective", "intro", "applied"]):
                courses_found.append(line_str)
            elif line_str.startswith("- ") or re.match(r"^\d+\.", line_str):
                courses_found.append(line_str)

        if courses_found:
            idx = ord_idx if ord_idx < len(courses_found) else 0
            target_line = courses_found[idx]
            # Extract code or title
            code_m = re.search(r"\*\*([A-Z0-9\-]+)\*\*", target_line)
            if not code_m:
                code_m = re.search(r"\b([A-Z]{2,4}\s*\d{3,4}[A-Z]?|[A-Z0-9]{4,12})\b", target_line)
            extracted_course = code_m.group(1) if code_m else target_line.replace("-", "").strip()
            return "get_course_faculty", {"course_query": extracted_course}

    # ── 3. Pronoun Continuity for Faculty: "what does she teach?", "which subjects is he assigned"
    if any(k in msg for k in ["what does she teach", "what does he teach", "which subjects does she teach", "which subjects does he teach", "her subjects", "his subjects", "her courses", "his courses"]):
        # Extract faculty name from last content
        fac_m = re.search(r"\b(Dr\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|Prof\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", last_content)
        if fac_m:
            target_fac = fac_m.group(1).strip()
            return "search_faculty_directory", {"search_query": target_fac}

    # ── 4. Section Continuity: "What classes are on Thursday?" following a section timetable query
    if day_match and last_tool_args.get("section_name"):
        return "get_section_timetable", {"section_name": last_tool_args["section_name"], "day": day_match}

    return None
