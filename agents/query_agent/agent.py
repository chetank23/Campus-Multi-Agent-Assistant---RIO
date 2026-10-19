"""
agents/query_agent/agent.py
---------------------------
Query Agent implementation for RIO-MJP.
Retrieves verified campus information from authorized database tools.
Answers are strictly grounded in PostgreSQL records.
"""

from __future__ import annotations

import datetime
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.models.identity import User
from agents.state.state import AgentState
from agents.tools import QUERY_TOOL_DEFINITIONS, execute_tool


def _extract_intent_and_tool_call(message: str, user: User) -> Tuple[str, Dict[str, Any]]:
    """
    Deterministically extracts the most appropriate tool call from natural language.
    Supports local/offline execution and fallback when no live LLM API key is present.
    """
    msg = message.lower().strip()

    # 1. Class status / Next class / Current class
    if any(k in msg for k in ["class status", "next class", "ongoing class", "current class", "what is my next", "what class is now"]):
        return "get_class_status", {}

    # 2. Student Timetable / My schedule
    day_match = None
    for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
        if d in msg:
            day_match = d.upper()
            break

    if any(k in msg for k in ["my timetable", "my schedule", "my classes", "classes on", "student schedule", "today's classes", "todays classes", "today classes", "what classes"]):
        if user.role == "STUDENT":
            args = {"day": day_match} if day_match else {}
            return "get_student_timetable", args
        elif user.role == "FACULTY":
            args = {"day": day_match} if day_match else {}
            return "get_faculty_schedule", args
        elif user.role == "ADMIN":
            args = {"day": day_match} if day_match else {}
            return "get_student_timetable", args

    # 3. Faculty teaching schedule
    if any(k in msg for k in ["faculty schedule", "teaching schedule", "my teaching", "faculty timetable"]):
        args = {"day": day_match} if day_match else {}
        return "get_faculty_schedule", args

    # 4. Department timetable
    if "department" in msg and any(k in msg for k in ["schedule", "timetable", "classes"]):
        args = {"day": day_match} if day_match else {}
        return "get_department_timetable", args

    # 5. Faculty Directory Profile
    if any(k in msg for k in ["faculty", "professor", "teacher", "who teaches", "profile", "contact for dr", "dr."]):
        # Extract name after keywords
        match = re.search(r"(?:dr\.?|prof\.?|faculty|professor|who is|about)\s+([a-zA-Z\s]+)", message, re.IGNORECASE)
        query = match.group(1).strip() if match else message
        return "get_faculty_profile", {"search_query": query}

    # 6. Course Catalog
    if any(k in msg for k in ["course", "syllabus", "credits", "subject", "curriculum"]):
        match = re.search(r"(?:course|subject|credits for|about)\s+([a-zA-Z0-9\s]+)", message, re.IGNORECASE)
        query = match.group(1).strip() if match else message
        return "get_course_details", {"query_str": query}

    # 7. Room count/inventory query — "how many classrooms", "how many labs available"
    #    Must be matched BEFORE the general room details pattern to avoid the whole
    #    question string being passed as a room search query.
    how_many_room_patterns = [
        r"how many.*(classroom|room|lab|hall|seminar)",
        r"(classroom|room|lab|hall|seminar).*how many",
        r"count.*(classroom|room|lab|hall)",
        r"total.*(classroom|room|lab|hall)",
        r"number of.*(classroom|room|lab|hall)",
    ]
    for pat in how_many_room_patterns:
        if re.search(pat, msg):
            # Determine room type hint
            if "classroom" in msg:
                return "get_campus_room_inventory", {"room_type": "CLASSROOM"}
            elif "lab" in msg:
                return "get_campus_room_inventory", {"room_type": "LAB"}
            elif "seminar" in msg or "hall" in msg:
                return "get_campus_room_inventory", {"room_type": "SEMINAR_HALL"}
            else:
                return "get_campus_room_inventory", {}

    # 7b. Room or Lab details (specific room lookup)
    if any(k in msg for k in ["room", "lab", "classroom", "hall", "where is", "capacity"]):
        match = re.search(r"(?:room|lab|hall|where is)\s+([a-zA-Z0-9\-\s]+)", message, re.IGNORECASE)
        query = match.group(1).strip() if match else message
        return "get_room_or_lab_details", {"room_query": query}

    # 8. Academic Calendar / Holidays / Exams
    if any(k in msg for k in ["holiday", "calendar", "exam", "vacation", "events", "when is the"]):
        ev_type = None
        if "holiday" in msg:
            ev_type = "HOLIDAY"
        elif "exam" in msg:
            ev_type = "EXAM"
        elif "event" in msg:
            ev_type = "EVENT"
        return "get_academic_calendar", {"event_type": ev_type}

    # Default fallback for student/faculty asking for general schedule
    if user.role == "STUDENT":
        return "get_student_timetable", {"day": day_match} if day_match else {}
    elif user.role == "FACULTY":
        return "get_faculty_schedule", {"day": day_match} if day_match else {}

    return "get_academic_calendar", {}


def format_grounded_response(
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Dict[str, Any],
    user: User,
) -> Tuple[str, List[str]]:
    """
    Renders structured, grounded natural-language responses strictly from tool results.
    Never invents campus facts.
    """
    sources: List[str] = []

    if "error" in tool_result:
        return f"⚠️ {tool_result['error']}", sources

    if tool_name == "get_student_timetable":
        sources.append("Official Published Timetable")
        entries = tool_result.get("entries", [])
        if not entries:
            msg = tool_result.get("message", "No classes found for your section in the active published timetable.")
            return f"ℹ️ {msg}", sources

        lines = [
            f"### 📅 Published Class Schedule for {tool_result.get('student_name', 'Student')}",
            f"**Section:** {tool_result.get('section', 'N/A')} | **Batch:** {tool_result.get('batch', 'All')}",
            "",
            "| Day | Time | Course | Room | Faculty | Status |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for e in entries:
            lines.append(
                f"| {e['day']} | {e['start_time']} - {e['end_time']} | {e['course_code']} ({e['course_title']}) | {e['room']} | {e['faculty_name']} | `{e['status']}` |"
            )
        return "\n".join(lines), sources

    elif tool_name == "get_class_status":
        sources.append("Live Timetable Tracker")
        ongoing = tool_result.get("ongoing_class")
        next_c = tool_result.get("next_class")
        classes = tool_result.get("classes", [])

        lines = [
            f"### ⏱️ Real-time Class Status ({tool_result.get('day', 'Today')}, {tool_result.get('current_time', '')})",
            "",
        ]
        if ongoing:
            lines.append(
                f"🟢 **ONGOING CLASS NOW:** **{ongoing['course_code']}** ({ongoing['course_title']}) in **Room {ongoing['room']}** by **{ongoing['faculty']}** ({ongoing['start_time']} - {ongoing['end_time']})"
            )
        else:
            lines.append("⚪ **No class is currently in session right now.**")

        if next_c:
            lines.append(
                f"🟡 **NEXT UPCOMING CLASS:** **{next_c['course_code']}** ({next_c['course_title']}) in **Room {next_c['room']}** by **{next_c['faculty']}** at **{next_c['start_time']}**"
            )
        else:
            lines.append("🏁 **No further classes scheduled for today.**")

        if classes:
            lines.append("\n**Today's Schedule:**")
            for c in classes:
                status_emoji = "🟢" if c["class_status"] == "ONGOING" else ("🟡" if c["class_status"] == "UPCOMING" else "⚪")
                lines.append(
                    f"- {status_emoji} `{c['start_time']} - {c['end_time']}`: **{c['course_code']}** ({c['course_title']}) in Room {c['room']} — *{c['class_status']}*"
                )

        return "\n".join(lines), sources

    elif tool_name == "get_faculty_schedule":
        sources.append("Faculty Teaching Roster")
        entries = tool_result.get("entries", [])
        if not entries:
            msg = tool_result.get("message", "No scheduled classes found in the active published timetable.")
            return f"ℹ️ {msg}", sources

        lines = [
            f"### 👨‍🏫 Teaching Schedule for {tool_result.get('faculty_name', 'Faculty Member')}",
            f"**Designation:** {tool_result.get('designation', 'Faculty')} | **Total Slots:** {tool_result.get('total_teaching_slots', len(entries))}",
            "",
            "| Day | Time | Course | Section | Room | Status |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for e in entries:
            lines.append(
                f"| {e['day']} | {e['start_time']} - {e['end_time']} | {e['course_code']} ({e['course_title']}) | {e['section']} | {e['room']} | `{e['status']}` |"
            )
        return "\n".join(lines), sources

    elif tool_name == "get_faculty_profile":
        sources.append("Campus Academic Directory")
        results = tool_result.get("results", [])
        if not results:
            return tool_result.get("message", "No matching faculty found."), sources

        lines = ["### 👤 Faculty Directory Results\n"]
        for f in results:
            lines.append(f"#### {f['name']} ({f['designation']})")
            lines.append(f"- **Department:** {f['department']}")
            lines.append(f"- **Faculty ID:** {f['faculty_id']}")
            lines.append(f"- **Specialization:** {f['specialization']}")
            lines.append(f"- **Areas of Interest:** {f['areas_of_interest']}")
            if f.get("contact_number"):
                lines.append(f"- **Contact:** {f['contact_number']}")
            lines.append("")
        return "\n".join(lines), sources

    elif tool_name == "get_course_details":
        sources.append("University Course Catalog")
        results = tool_result.get("results", [])
        if not results:
            return tool_result.get("message", "No course found matching query."), sources

        lines = ["### 📚 Course Information\n"]
        for c in results:
            elective_tag = " (Elective)" if c["is_elective"] else " (Core)"
            lines.append(f"- **{c['code']} — {c['title']}**{elective_tag}")
            lines.append(f"  - **Credits:** {c['credits']} | **Department:** {c['department']}")
        return "\n".join(lines), sources

    elif tool_name == "get_room_or_lab_details":
        sources.append("Campus Facilities Register")
        results = tool_result.get("results", [])
        if not results:
            return tool_result.get("message", "No facility found."), sources

        lines = ["### 🏛️ Room & Lab Details\n"]
        for r in results:
            active_badge = "Active" if r["is_active"] else "Inactive"
            lines.append(f"- **Room {r['room_number']}** ({r['room_type']}) — *{active_badge}*")
            lines.append(f"  - **Building:** {r['building']} | **Capacity:** {r['capacity']} seats")
        return "\n".join(lines), sources

    elif tool_name == "get_academic_calendar":
        sources.append("Official Academic Calendar")
        events = tool_result.get("events", [])
        if not events:
            return tool_result.get("message", "No scheduled events found."), sources

        lines = ["### 📆 Academic Calendar & University Events\n"]
        for ev in events:
            type_tag = f"`{ev['event_type']}`"
            lines.append(f"- **{ev['date']}** {type_tag}: {ev['description']}")
        return "\n".join(lines), sources

    elif tool_name == "get_department_timetable":
        sources.append("Department Schedule Register")
        entries = tool_result.get("entries", [])
        if not entries:
            return tool_result.get("message", "No department schedule found."), sources

        lines = [
            f"### 🏢 Schedule for {tool_result.get('department_name', 'Department')}",
            f"**Total Classes Listed:** {len(entries)}",
            "",
            "| Day | Time | Course | Section | Room | Faculty |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for e in entries[:25]:
            lines.append(
                f"| {e['day']} | {e['start_time']} - {e['end_time']} | {e['course']} | {e['section']} | {e['room']} | {e['faculty']} |"
            )
        return "\n".join(lines), sources

    elif tool_name == "get_campus_room_inventory":
        sources.append("Campus Facilities Register")
        total = tool_result.get("total_active_rooms", 0)
        breakdown = tool_result.get("breakdown", [])
        note = tool_result.get("availability_note", "")

        lines = ["### Campus Room Inventory (Active Facilities)\n"]
        lines.append(f"**Total Active Rooms:** {total}\n")
        if breakdown:
            lines.append("| Room Type | Count |")
            lines.append("| :--- | ---: |")
            for b in breakdown:
                lines.append(f"| {b['room_type'].replace('_', ' ').title()} | {b['count']} |")
        lines.append("")
        lines.append(f"> **Note:** {note}")
        return "\n".join(lines), sources

    return "No information could be generated for this query.", sources


def run_query_agent(
    state: AgentState,
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Executes the Query Agent node in the multi-agent graph.
    Selects authorized tools, queries PostgreSQL, and produces grounded responses.
    """
    message = state.get("message", "")

    # 1. Check if ANTHROPIC_API_KEY is configured for LLM tool calling
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    tool_name = None
    tool_args: Dict[str, Any] = {}

    if api_key and not api_key.startswith("mock-") and not api_key.startswith("test-"):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)

            from anthropic.types import ToolParam

            # Filter tools permitted for user's role
            allowed_tools = [
                t for t in QUERY_TOOL_DEFINITIONS if user.role in t["allowed_roles"]
            ]
            anthropic_tools: list[ToolParam] = [
                {
                    "name": str(t["name"]),
                    "description": str(t["description"]),
                    "input_schema": dict(t["parameters"]),
                }
                for t in allowed_tools
            ]

            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                system=(
                    f"You are the RIO-MJP Campus Assistant Query Agent. You answer campus questions strictly "
                    f"by invoking available database tools. Caller identity: User ID {user.id}, Role {user.role}. "
                    f"Never invent campus information. Always call a tool if the user is asking about schedules, "
                    f"faculty, courses, rooms, or calendar events."
                ),
                messages=[{"role": "user", "content": message}],
                tools=anthropic_tools,
            )

            # Check for tool call in response
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_args = block.input
                    break

        except Exception:
            # Fall back to deterministic local resolution on API error
            tool_name = None

    # Fallback / Deterministic extractor
    if not tool_name:
        tool_name, tool_args = _extract_intent_and_tool_call(message, user)

    # 2. Execute tool against database
    tool_result = execute_tool(
        tool_name=tool_name,
        tool_args=tool_args,
        user=user,
        db=db,
    )

    # 3. Format grounded response
    response_text, sources = format_grounded_response(
        tool_name=tool_name,
        tool_args=tool_args,
        tool_result=tool_result,
        user=user,
    )

    tool_calls = state.get("tool_calls", []) + [{"tool": tool_name, "args": tool_args}]
    tool_results = state.get("tool_results", []) + [{"tool": tool_name, "result": tool_result}]

    return {
        "final_response": response_text,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "sources": sources,
    }
