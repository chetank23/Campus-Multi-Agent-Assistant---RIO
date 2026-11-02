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
from typing import Any, Dict, List, Optional, Tuple, cast
from sqlalchemy.orm import Session

from backend.models.identity import User
from agents.state.state import AgentState
from agents.tools import QUERY_TOOL_DEFINITIONS, execute_tool
from agents.common.formatter import sanitize_plain_english


def _extract_intent_and_tool_call(message: str, user: User) -> Tuple[str, Dict[str, Any]]:
    """
    Deterministically extracts the most appropriate tool call from natural language.
    Supports local/offline execution and fallback when no live LLM API key is present.
    """
    msg = message.lower().strip()

    # 1. Announcements / Campus notices
    if any(k in msg for k in ["announcement", "announcements", "campus notice", "notices", "broadcast"]):
        return "get_relevant_announcements", {}

    # 2. Timetable changes / Rescheduling / Disruptions
    if any(k in msg for k in [
        "timetable changed", "has my timetable changed", "timetable changes",
        "recent changes", "schedule changed", "any changes", "disruption", "disruptions",
    ]):
        return "get_recent_timetable_changes", {}

    # 3. Timetable publication status
    if any(k in msg for k in [
        "timetable status", "published status", "publication status",
        "is the timetable published", "is timetable published", "published timetable",
    ]):
        return "get_published_timetable_status", {}

    # 4. Resource / Lab Booking Status
    if any(k in msg for k in [
        "booking status", "my booking", "my bookings", "status of my booking",
        "status of my resource", "lab booking status", "show my bookings",
    ]):
        return "get_resource_booking_status", {}

    # 5. Class status / Next class / Current class
    if any(k in msg for k in ["class status", "next class", "ongoing class", "current class", "what is my next", "what class is now"]):
        return "get_class_status", {}

    # Day detection helper
    day_match: Optional[str] = None
    if "today" in msg:
        day_match = "TODAY"
    elif "tomorrow" in msg:
        day_match = "TOMORROW"
    else:
        for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            if d in msg:
                day_match = d.upper()
                break

    # Time detection helper
    time_match = re.search(r"\b(\d{1,2}:\d{2})\b", msg)
    start_time_arg = time_match.group(1) if time_match else None

    # 6. Room & Lab Availability queries
    is_lab = any(k in msg for k in ["lab", "labs", "laboratory", "laboratories"])
    if any(k in msg for k in [
        "available room", "available rooms", "free room", "free rooms", "room availability",
        "which rooms are free", "find available room", "available lab", "available labs",
        "free lab", "free labs", "lab availability", "which labs are free", "find available lab",
    ]):
        tool = "get_lab_availability" if is_lab else "get_room_availability"
        args: Dict[str, Any] = {}
        if day_match:
            args["day"] = day_match
        if start_time_arg:
            args["start_time"] = start_time_arg
        return tool, args

    # 7. Department timetable
    if "department" in msg and any(k in msg for k in ["schedule", "timetable", "classes"]):
        args = {"day": day_match} if day_match else {}
        return "get_department_timetable", args

    # 8. Faculty specific teaching schedule (for Admin or queries mentioning specific faculty)
    fac_name_match = re.search(
        r"(?:faculty|prof\.?|professor|dr\.?)\s+([a-zA-Z\s]+?)(?:'s|\s+timetable|\s+schedule|\s*$)",
        message,
        re.IGNORECASE,
    )
    if fac_name_match and any(k in msg for k in ["schedule", "timetable", "classes"]):
        target_name = fac_name_match.group(1).strip()
        args = {"target_faculty_name": target_name}
        if day_match:
            args["day"] = day_match
        return "get_faculty_timetable", args

    # 9. Faculty Directory Profile / Faculty Information
    if any(k in msg for k in ["faculty", "professor", "teacher", "who teaches", "profile", "contact for dr", "dr."]):
        match = re.search(r"(?:dr\.?|prof\.?|faculty|professor|who is|about)\s+([a-zA-Z\s]+)", message, re.IGNORECASE)
        query = match.group(1).strip() if match else message
        return "get_faculty_information", {"search_query": query}

    # 10. Course Information
    if any(k in msg for k in ["course", "syllabus", "credits", "subject", "curriculum"]):
        match = re.search(r"(?:course|subject|credits for|about)\s+([a-zA-Z0-9\s]+)", message, re.IGNORECASE)
        query = match.group(1).strip() if match else message
        return "get_course_information", {"query_str": query}

    # 11. Room count/inventory query
    how_many_room_patterns = [
        r"how many.*(classroom|room|lab|hall|seminar)",
        r"(classroom|room|lab|hall|seminar).*how many",
        r"count.*(classroom|room|lab|hall)",
        r"total.*(classroom|room|lab|hall)",
        r"number of.*(classroom|room|lab|hall)",
    ]
    for pat in how_many_room_patterns:
        if re.search(pat, msg):
            if "classroom" in msg:
                return "get_campus_room_inventory", {"room_type": "CLASSROOM"}
            elif "lab" in msg:
                return "get_campus_room_inventory", {"room_type": "LAB"}
            elif "seminar" in msg or "hall" in msg:
                return "get_campus_room_inventory", {"room_type": "SEMINAR_HALL"}
            else:
                return "get_campus_room_inventory", {}

    # 11b. Room or Lab details (specific room lookup)
    if any(k in msg for k in ["room", "lab", "classroom", "hall", "where is", "capacity"]) and not any(k in msg for k in ["event", "events", "club", "workshop"]):
        match = re.search(r"(?:room|lab|hall|where is)\s+([a-zA-Z0-9\-\s]+)", message, re.IGNORECASE)
        query = match.group(1).strip() if match else message
        return "get_room_or_lab_details", {"room_query": query}

    # 12. Campus Events & Club Activities
    if any(k in msg for k in [
        "ongoing event", "ongoing events", "ongoing", "live events", "live event",
        "happening now", "currently happening", "what events are happening", "what event is happening",
    ]):
        return "get_ongoing_events", {}

    if any(k in msg for k in ["upcoming event", "upcoming events", "upcoming workshop", "upcoming workshops", "upcoming activities"]):
        return "get_upcoming_events", {}

    if any(k in msg for k in ["my clubs", "my club", "show my clubs", "what clubs do i coordinate", "which clubs do i manage"]):
        return "list_my_clubs", {}

    if any(k in msg for k in ["list clubs", "all clubs", "campus clubs", "what clubs are there", "clubs in campus"]):
        return "list_my_clubs" if user.role in ("ADMIN", "FACULTY") else "list_visible_events", {}

    if "club" in msg and any(k in msg for k in ["activit", "events", "workshop"]):
        match = re.search(r"(?:club|in)\s+([a-zA-Z0-9\s]+?)(?:'s|\s+activities|\s+events|\s*$)", message, re.IGNORECASE)
        club_name = match.group(1).strip() if match else None
        return "list_club_activities", {"club_name": club_name}

    if any(k in msg for k in ["event details", "about event", "tell me about event", "details for event"]):
        match = re.search(r"(?:event|about)\s+([a-zA-Z0-9\s]+)", message, re.IGNORECASE)
        title = match.group(1).strip() if match else message
        return "get_published_event_details", {"title": title}

    if any(k in msg for k in [
        "campus event", "campus events", "college event", "college events", "events today",
        "today events", "what events", "list events", "show events", "what is happening on campus",
        "workshops", "workshop", "hackathon", "cultural fest", "fest",
    ]):
        tf = "TODAY" if "today" in msg else None
        return "list_visible_events", {"time_filter": tf}

    # 13. Academic Calendar / Holidays / Exams
    if any(k in msg for k in ["holiday", "calendar", "exam", "vacation", "when is the"]):
        ev_type = None
        if "holiday" in msg:
            ev_type = "HOLIDAY"
        elif "exam" in msg:
            ev_type = "EXAM"
        return "get_academic_calendar", {"event_type": ev_type}

    # 13. My Timetable / Schedule (Default for students and faculty)
    if any(k in msg for k in [
        "my timetable", "my schedule", "my classes", "classes on", "student schedule",
        "today's classes", "todays classes", "today classes", "what classes",
        "timetable today", "timetable tomorrow", "classes today", "classes tomorrow",
    ]):
        args = {"day": day_match} if day_match else {}
        return "get_my_timetable", args

    # Default fallback based on role
    if user.role in ("STUDENT", "FACULTY"):
        return "get_my_timetable", {"day": day_match} if day_match else {}

    return "get_published_timetable_status", {}


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
        return sanitize_plain_english(f"Error: {tool_result['error']}"), sources

    # 1 & 2. Student Timetable & My Timetable
    if tool_name in ("get_my_timetable", "get_student_timetable"):
        sources.append("Official Published Timetable")
        if "message" in tool_result and not tool_result.get("entries"):
            return sanitize_plain_english(tool_result["message"]), sources

        entries = tool_result.get("entries", [])
        if not entries:
            msg = tool_result.get("message", "No classes found for your section in the active published timetable.")
            return sanitize_plain_english(msg), sources

        # If faculty schedule returned via get_my_timetable
        if "total_teaching_slots" in tool_result:
            sources.append("Faculty Teaching Roster")
            lines = [
                f"Teaching Schedule for {tool_result.get('faculty_name', 'Faculty Member')}",
                f"Designation: {tool_result.get('designation', 'Faculty')} | Total Teaching Slots: {len(entries)}",
                "",
            ]
            for e in entries:
                lines.append(
                    f"- {e['day']} {e['start_time']} - {e['end_time']}: {e['course_code']} ({e['course_title']}), "
                    f"Section: {e['section']}, Room: {e['room']} (Status: {e['status']})"
                )
            return sanitize_plain_english("\n".join(lines)), sources

        # Student schedule
        lines = [
            f"Published Class Schedule for {tool_result.get('student_name', 'Student')}",
            f"Section: {tool_result.get('section', 'N/A')} | Batch: {tool_result.get('batch', 'All')} | Total Classes: {len(entries)}",
            "",
        ]
        for e in entries:
            lines.append(
                f"- {e['day']} {e['start_time']} - {e['end_time']}: {e['course_code']} ({e['course_title']}), "
                f"Room: {e['room']}, Faculty: {e['faculty_name']} (Status: {e['status']})"
            )
        return sanitize_plain_english("\n".join(lines)), sources

    # 3. Faculty Timetable
    elif tool_name in ("get_faculty_timetable", "get_faculty_schedule"):
        sources.append("Faculty Teaching Roster")
        entries = tool_result.get("entries", [])
        if not entries:
            msg = tool_result.get("message", "No scheduled classes found in the active published timetable.")
            return sanitize_plain_english(msg), sources

        lines = [
            f"Teaching Schedule for {tool_result.get('faculty_name', 'Faculty Member')}",
            f"Designation: {tool_result.get('designation', 'Faculty')} | Total Slots: {tool_result.get('total_teaching_slots', len(entries))}",
            "",
        ]
        for e in entries:
            lines.append(
                f"- {e['day']} {e['start_time']} - {e['end_time']}: {e['course_code']} ({e['course_title']}), "
                f"Section: {e['section']}, Room: {e['room']} (Status: {e['status']})"
            )
        return sanitize_plain_english("\n".join(lines)), sources

    # 4. Department Timetable
    elif tool_name == "get_department_timetable":
        sources.append("Department Schedule Register")
        entries = tool_result.get("entries", [])
        if not entries:
            return sanitize_plain_english(tool_result.get("message", "No department schedule found.")), sources

        lines = [
            f"Schedule for {tool_result.get('department_name', 'Department')}",
            f"Total Classes Listed: {len(entries)}",
            "",
        ]
        for e in entries[:25]:
            lines.append(
                f"- {e['day']} {e['start_time']} - {e['end_time']}: {e['course']}, "
                f"Section: {e['section']}, Room: {e['room']}, Faculty: {e['faculty']}"
            )
        return sanitize_plain_english("\n".join(lines)), sources

    # 5. Course Information
    elif tool_name in ("get_course_information", "get_course_details"):
        sources.append("University Course Catalog")
        results = tool_result.get("results", [])
        if not results:
            return sanitize_plain_english(tool_result.get("message", "No course found matching query.")), sources

        lines = ["Course Catalog Details:\n"]
        for c in results:
            elective_tag = " (Elective)" if c.get("is_elective") else " (Core)"
            lab_tag = " | Requires Lab: Yes" if c.get("requires_lab") else ""
            lines.append(f"- {c['code']} - {c['title']}{elective_tag}")
            lines.append(f"  Credits: {c['credits']} | Department: {c['department']}{lab_tag}")
            if c.get("assigned_faculty"):
                lines.append(f"  Instructors: {', '.join(c['assigned_faculty'])}")
            lines.append("")
        return sanitize_plain_english("\n".join(lines)), sources

    # 6. Faculty Profile & Information
    elif tool_name in ("get_faculty_information", "get_faculty_profile"):
        sources.append("Campus Academic Directory")
        results = tool_result.get("results", [])
        if not results:
            return sanitize_plain_english(tool_result.get("message", "No matching faculty found.")), sources

        lines = ["Faculty Directory Results:\n"]
        for f in results:
            lines.append(f"{f['name']} ({f['designation']})")
            lines.append(f"- Department: {f['department']}")
            lines.append(f"- Faculty ID: {f['faculty_id']}")
            lines.append(f"- Specialization: {f['specialization']}")
            if f.get("areas_of_interest"):
                lines.append(f"- Areas of Interest: {f['areas_of_interest']}")
            if f.get("contact_number"):
                lines.append(f"- Contact: {f['contact_number']}")
            if f.get("courses_taught"):
                lines.append(f"- Assigned Courses: {', '.join(f['courses_taught'])}")
            lines.append("")
        return sanitize_plain_english("\n".join(lines)), sources

    # 7 & 8. Room and Lab Availability
    elif tool_name in ("get_room_availability", "get_lab_availability"):
        sources.append("Timetable & Facilities Registry")
        avail = tool_result.get("available_rooms", [])
        occupied = tool_result.get("occupied_rooms", [])
        time_win = tool_result.get("time_window", "Requested Time")
        day_str = tool_result.get("day", "Today")

        facility_type = "Laboratory" if tool_name == "get_lab_availability" else "Room"
        lines = [
            f"{facility_type} Availability Overview ({day_str}, Window: {time_win}):",
            f"Available: {len(avail)} | Occupied: {len(occupied)}",
            "",
        ]

        if avail:
            lines.append("Available Facilities:")
            for r in avail[:10]:
                lines.append(f"- Room {r['room_number']} ({r['room_type']}) in {r['building']} (Capacity: {r['capacity']} seats)")
            if len(avail) > 10:
                lines.append(f"... and {len(avail) - 10} more available.")
            lines.append("")

        if occupied:
            lines.append("Occupied Facilities:")
            for r in occupied[:10]:
                conflicts_str = "; ".join(r.get("conflicts", []))
                lines.append(f"- Room {r['room_number']} ({r['room_type']}): {conflicts_str}")
            if len(occupied) > 10:
                lines.append(f"... and {len(occupied) - 10} more occupied.")

        return sanitize_plain_english("\n".join(lines)), sources

    # 9. Resource Booking Status
    elif tool_name in ("get_resource_booking_status", "get_user_bookings"):
        sources.append("Resource Booking System")
        if "booking_id" in tool_result:
            # Single booking
            lines = [
                f"Booking Request #{tool_result['booking_id']} Details:",
                f"- Resource: {tool_result.get('resource_name', 'N/A')} ({tool_result.get('resource_type', 'Facility')})",
                f"- Date & Time: {tool_result.get('date')} {tool_result.get('start_time')} - {tool_result.get('end_time')}",
                f"- Status: {tool_result.get('status', 'PENDING')}",
                f"- Purpose: {tool_result.get('purpose', 'N/A')}",
            ]
            if tool_result.get("requester_name"):
                lines.append(f"- Requester: {tool_result['requester_name']}")
            return sanitize_plain_english("\n".join(lines)), sources

        bookings = tool_result.get("bookings", [])
        if not bookings:
            return sanitize_plain_english("No resource bookings found for your account."), sources

        lines = [f"Resource Bookings ({len(bookings)} record(s)):\n"]
        for b in bookings:
            lines.append(
                f"- Booking #{b['booking_id']}: {b['resource_name']} on {b['date']} "
                f"({b['start_time']} - {b['end_time']}) | Status: {b['status']}"
            )
            if b.get("purpose"):
                lines.append(f"  Purpose: {b['purpose']}")
        return sanitize_plain_english("\n".join(lines)), sources

    # 10. Published Timetable Status
    elif tool_name == "get_published_timetable_status":
        sources.append("Timetable Publishing Governance")
        if user.role == "ADMIN":
            active_v = tool_result.get("active_published_version")
            versions = tool_result.get("versions", [])
            lines = ["Campus Timetable Governance Status (ADMIN):\n"]
            if active_v:
                lines.append(f"Active Published Version: Version {active_v['version_number']} ({active_v['academic_year']})")
                lines.append(f"- Published at: {active_v.get('published_at', 'N/A')}")
                lines.append(f"- Total Entries: {active_v['total_entries']}\n")
            else:
                lines.append("No active published timetable version.\n")

            lines.append(f"Total Timetable Versions: {len(versions)}")
            for v in versions[:5]:
                lines.append(f"- Version {v['version_number']}: Status {v['status']} ({v['total_entries']} entries)")
            return sanitize_plain_english("\n".join(lines)), sources
        else:
            if not tool_result.get("has_published_timetable"):
                return sanitize_plain_english("No published timetable is currently active for this semester."), sources
            lines = [
                "Current Published Timetable Status:",
                f"- Version: Version {tool_result.get('version_number')}",
                f"- Academic Year: {tool_result.get('academic_year')}",
                f"- Published Date: {tool_result.get('published_at')}",
                f"- Total Active Classes: {tool_result.get('total_active_entries')}",
            ]
            return sanitize_plain_english("\n".join(lines)), sources

    # 11. Recent Timetable Changes
    elif tool_name == "get_recent_timetable_changes":
        sources.append("Campus Notifications & Audit Trail")
        recent_notifs = tool_result.get("recent_announcements", [])
        audit_recs = tool_result.get("admin_audit_records", [])

        if not recent_notifs and not audit_recs:
            return sanitize_plain_english("No recent timetable changes, cancellations, or room reassignments found."), sources

        lines = ["Recent Timetable Updates & Changes:\n"]
        for n in recent_notifs:
            lines.append(f"- [{n.get('created_at', '')}] {n.get('title')}: {n.get('message')}")
        if audit_recs:
            lines.append("\nAdministrative Audit Log:")
            for a in audit_recs:
                lines.append(f"- [{a.get('timestamp', '')}] {a.get('action')}")
        return sanitize_plain_english("\n".join(lines)), sources

    # 12. Relevant Announcements
    elif tool_name == "get_relevant_announcements":
        sources.append("University Broadcasts & Calendar")
        announcements = tool_result.get("announcements", [])
        events = tool_result.get("upcoming_calendar_events", [])

        if not announcements and not events:
            return sanitize_plain_english("There are no active campus announcements or upcoming events at this time."), sources

        lines = []
        if announcements:
            lines.append("Official Campus Announcements:\n")
            for a in announcements:
                lines.append(f"- {a['title']} ({a.get('date', '')})")
                if a.get("message"):
                    lines.append(f"  {a['message']}")
            lines.append("")

        if events:
            lines.append("Upcoming Academic Calendar Events:\n")
            for e in events:
                lines.append(f"- {e['date']} [{e['event_type']}]: {e['description']}")

        return sanitize_plain_english("\n".join(lines)), sources

    # Real-time class status
    elif tool_name == "get_class_status":
        sources.append("Live Timetable Tracker")
        ongoing = tool_result.get("ongoing_class")
        next_c = tool_result.get("next_class")
        classes = tool_result.get("classes", [])

        lines = [
            f"Real-time Class Status ({tool_result.get('day', 'Today')}, {tool_result.get('current_time', '')})",
            "",
        ]
        if ongoing:
            lines.append(
                f"Ongoing class now: {ongoing['course_code']} ({ongoing['course_title']}) in Room {ongoing['room']} "
                f"by {ongoing['faculty']} ({ongoing['start_time']} - {ongoing['end_time']})"
            )
        else:
            lines.append("No class is currently in session.")

        if next_c:
            lines.append(
                f"Next upcoming class: {next_c['course_code']} ({next_c['course_title']}) in Room {next_c['room']} "
                f"by {next_c['faculty']} at {next_c['start_time']}"
            )
        else:
            lines.append("No further classes scheduled for today.")

        if classes:
            lines.append("\nToday's Schedule:")
            for c in classes:
                lines.append(
                    f"- {c['start_time']} - {c['end_time']}: {c['course_code']} ({c['course_title']}) "
                    f"in Room {c['room']} (Status: {c['class_status']})"
                )

        return sanitize_plain_english("\n".join(lines)), sources

    # Room or lab specifications
    elif tool_name == "get_room_or_lab_details":
        sources.append("Campus Facilities Register")
        results = tool_result.get("results", [])
        if not results:
            return sanitize_plain_english(tool_result.get("message", "No facility found.")), sources

        lines = ["Room and Lab Details:\n"]
        for r in results:
            active_badge = "Active" if r["is_active"] else "Inactive"
            lines.append(f"- Room {r['room_number']} ({r['room_type']}) - Status: {active_badge}")
            lines.append(f"  Building: {r['building']} | Capacity: {r['capacity']} seats")
        return sanitize_plain_english("\n".join(lines)), sources

    # Academic Calendar
    elif tool_name == "get_academic_calendar":
        sources.append("Official Academic Calendar")
        events = tool_result.get("events", [])
        if not events:
            return sanitize_plain_english(tool_result.get("message", "No scheduled events found.")), sources

        lines = ["Academic Calendar and University Events:\n"]
        for ev in events:
            lines.append(f"- {ev['date']} ({ev['event_type']}): {ev['description']}")
        return sanitize_plain_english("\n".join(lines)), sources

    # Room Inventory
    elif tool_name == "get_campus_room_inventory":
        sources.append("Campus Facilities Register")
        total = tool_result.get("total_active_rooms", 0)
        breakdown = tool_result.get("breakdown", [])
        note = tool_result.get("availability_note", "")

        lines = ["Campus Room Inventory (Active Facilities)\n"]
        lines.append(f"Total Active Rooms: {total}\n")
        lines.append("Breakdown by Room Type:")
        if breakdown:
            for b in breakdown:
                lines.append(f"- {b['room_type'].replace('_', ' ').title()}: {b['count']}")
        lines.append("")
        lines.append(f"Note: {note}")
        return sanitize_plain_english("\n".join(lines)), sources

    # Campus Events: Visible events list
    elif tool_name in ("list_visible_events", "list_events"):
        sources.append("Campus Events Registry")
        events = tool_result.get("events", [])
        if not events:
            return sanitize_plain_english("No campus events found matching your criteria."), sources

        lines = [f"Campus Events ({len(events)} event(s)):\n"]
        for ev in events[:10]:
            venue = ev.get("room_number") or ev.get("venue_name") or "TBA"
            lines.append(f"- **{ev['title']}** ({ev.get('category', 'EVENT')})")
            lines.append(f"  Status: {ev['status']} | Venue: {venue}")
            lines.append(f"  Time: {ev.get('start_time', '')} to {ev.get('end_time', '')}")
            if ev.get("club_name"):
                lines.append(f"  Organized by: {ev['club_name']}")
            if ev.get("description"):
                lines.append(f"  Note: {ev['description']}")
            lines.append("")
        if len(events) > 10:
            lines.append(f"... and {len(events) - 10} more events.")
        return sanitize_plain_english("\n".join(lines)), sources

    # Live & Ongoing Campus Events
    elif tool_name == "get_ongoing_events":
        sources.append("Campus Events Registry")
        events = tool_result.get("ongoing_events", [])
        if not events:
            return sanitize_plain_english("There are no campus events currently ongoing right now."), sources

        lines = [f"Live & Ongoing Campus Events ({len(events)} active now):\n"]
        for ev in events:
            venue = ev.get("room_number") or ev.get("venue_name") or "TBA"
            lines.append(f"- **{ev['title']}** ({ev.get('category', 'EVENT')})")
            lines.append(f"  Location: {venue} | Time: {ev.get('start_time', '')} - {ev.get('end_time', '')}")
            if ev.get("club_name"):
                lines.append(f"  Club: {ev['club_name']}")
            lines.append("")
        return sanitize_plain_english("\n".join(lines)), sources

    # Upcoming Campus Events
    elif tool_name == "get_upcoming_events":
        sources.append("Campus Events Registry")
        events = tool_result.get("upcoming_events", [])
        if not events:
            return sanitize_plain_english("No upcoming campus events scheduled at this time."), sources

        lines = [f"Upcoming Campus Events & Activities ({len(events)} upcoming):\n"]
        for ev in events:
            venue = ev.get("room_number") or ev.get("venue_name") or "TBA"
            lines.append(f"- **{ev['title']}** ({ev.get('category', 'EVENT')})")
            lines.append(f"  Date & Time: {ev.get('start_time', '')} to {ev.get('end_time', '')}")
            lines.append(f"  Venue: {venue}")
            if ev.get("club_name"):
                lines.append(f"  Organizing Club: {ev['club_name']}")
            lines.append("")
        return sanitize_plain_english("\n".join(lines)), sources

    # Published Event Details
    elif tool_name == "get_published_event_details":
        sources.append("Campus Events Registry")
        if not tool_result.get("found"):
            return sanitize_plain_english(tool_result.get("message", "Event not found or not published.")), sources
        ev = tool_result["event"]
        venue = ev.get("room_number") or ev.get("venue_name") or "TBA"
        lines = [
            f"Event Details: {ev['title']}",
            f"- Category: {ev.get('category', 'EVENT')}",
            f"- Status: {ev.get('status', 'PUBLISHED')}",
            f"- Time: {ev.get('start_time', '')} to {ev.get('end_time', '')}",
            f"- Venue: {venue}",
            f"- Target Audience: {ev.get('target_audience', 'ALL')}",
        ]
        if ev.get("club_name"):
            lines.append(f"- Organizing Club: {ev['club_name']}")
        if ev.get("description"):
            lines.append(f"- Description: {ev['description']}")
        return sanitize_plain_english("\n".join(lines)), sources

    # Faculty / Admin Clubs List
    elif tool_name in ("list_my_clubs", "list_all_clubs"):
        sources.append("Club & Activity Registry")
        clubs = tool_result.get("clubs", [])
        if not clubs:
            return sanitize_plain_english("You do not currently have any active club coordinator assignments."), sources

        lines = [f"Clubs ({len(clubs)}):\n"]
        for c in clubs:
            lines.append(f"- **{c['name']}** ({c['code']}) [{c['category']}] - Status: {c['status']}")
            if c.get("description"):
                lines.append(f"  {c['description']}")
        return sanitize_plain_english("\n".join(lines)), sources

    # Club Activities
    elif tool_name == "list_club_activities":
        sources.append("Club & Activity Registry")
        activities = tool_result.get("activities", [])
        if not activities:
            return sanitize_plain_english("No activities or events found for this club."), sources

        lines = [f"Club Activities ({len(activities)}):\n"]
        for a in activities:
            venue = a.get("room_number") or a.get("venue_name") or "TBA"
            lines.append(f"- **{a['title']}** [{a['status']}]")
            lines.append(f"  Date & Time: {a.get('start_time', '')} to {a.get('end_time', '')} | Venue: {venue}")
        return sanitize_plain_english("\n".join(lines)), sources

    # Venue Conflict Check
    elif tool_name == "validate_event":
        sources.append("Venue & Facilities Conflict Engine")
        is_avail = tool_result.get("is_available", False)
        room_id = tool_result.get("room_id")
        conflicts = tool_result.get("conflicts", [])
        if is_avail:
            return sanitize_plain_english(f"The requested venue (Room ID: {room_id}) is available with zero conflicts!"), sources
        lines = [f"The venue has {len(conflicts)} scheduling conflict(s):"]
        for c in conflicts:
            lines.append(f"- [{c.get('type')}] {c.get('reason')} ({c.get('time_window')})")
        return sanitize_plain_english("\n".join(lines)), sources

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

            allowed_tools = [
                t for t in QUERY_TOOL_DEFINITIONS if user.role in t["allowed_roles"]
            ]
            anthropic_tools: list[ToolParam] = [
                {
                    "name": str(t["name"]),
                    "description": str(t["description"]),
                    "input_schema": cast(dict[str, Any], t.get("parameters", {})),
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

            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_args = block.input
                    break

        except Exception:
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
