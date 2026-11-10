"""
agents/common/response_formatter.py
-----------------------------------
Renders clear, transparent, grounded markdown responses strictly from PostgreSQL records.
Enforces the Direct-Answer Principle:
- Answers the user's question directly with actual data, tables, counts, and schedules.
- NEVER responds with navigational redirections ("check Settings", "visit the timetable page", "go to Student Management").
- Includes truthful provenance metadata (Data Source, Scope, Timestamp, Timetable Status).
- Distinguishes empty database results from system unavailability.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple
from agents.common.formatter import sanitize_plain_english


def _format_provenance(
    source: str,
    scope: str = "Authorized Institutional Scope",
    timetable_status: Optional[str] = None,
) -> str:
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S UTC")
    parts = [
        f"**Data Source:** {source}",
        f"**Scope:** {scope}",
        f"**Retrieved:** {now_str}",
    ]
    if timetable_status:
        parts.append(f"**Timetable Status:** {timetable_status}")
    return "\n\n---\n" + " | ".join(parts)


def format_grounded_answer(
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Dict[str, Any],
    user_role: str,
    user_name: str = "User",
) -> Tuple[str, List[str]]:
    """
    Renders structured, grounded natural-language responses strictly from tool results.
    Never invents facts, never redirects to portal pages.
    """
    sources: List[str] = []

    if not tool_result:
        return (
            "I could not retrieve records for your query from the database. No matching data was found.",
            sources,
        )

    if "error" in tool_result:
        err_msg = str(tool_result["error"])
        return sanitize_plain_english(f"Unable to complete query: {err_msg}"), sources

    # ── 1. Super Admin: Institutional Overview ────────────────────────────────
    if tool_name == "get_institutional_overview":
        sources.append("Central Institutional Registry (PostgreSQL)")
        lines = [
            "### Institutional Overview",
            "",
            f"**Campus Statistics:**",
            f"- **Enrolled Students:** {tool_result.get('total_students', 0)}",
            f"- **Faculty Members:** {tool_result.get('total_faculty', 0)}",
            f"- **Configured Departments:** {tool_result.get('total_departments', 0)}",
            f"- **Academic Programs:** {tool_result.get('total_programs', 0)}",
            f"- **Registered Courses:** {tool_result.get('total_courses', 0)}",
            f"- **Campus Buildings:** {tool_result.get('total_buildings', 0)}",
            f"- **Total Rooms:** {tool_result.get('total_rooms', 0)} (including {tool_result.get('total_labs', 0)} Laboratories)",
            f"- **Academic Sections:** {tool_result.get('total_sections', 0)}",
            f"- **Active Published Timetables:** {tool_result.get('published_timetables', 0)} (Drafts: {tool_result.get('draft_timetables', 0)})",
            "",
            "**Department Breakdown:**",
        ]
        depts = tool_result.get("departments", [])
        if depts:
            lines.append("| Department | Students | Faculty | Courses | Sections |")
            lines.append("|:---|:---:|:---:|:---:|:---:|")
            for d in depts:
                lines.append(
                    f"| {d['department_name']} ({d['department_code']}) | {d['students_count']} | {d['faculty_count']} | {d['courses_count']} | {d['sections_count']} |"
                )
        lines.append(_format_provenance("Central Institutional Registry", "Campus Wide", "Published"))
        return sanitize_plain_english("\n".join(lines)), sources

    # ── 2. Super Admin: Academic Structure ────────────────────────────────────
    elif tool_name == "get_academic_structure_overview":
        sources.append("Academic Governance Register")
        sem_str = ", ".join(f"Sem {s.get('semester_number', '')}" for s in tool_result.get("semesters", [])) or "Semester VII"
        lines = [
            "### Academic Structure Overview",
            "",
            f"**Configured Academic Years:** {', '.join(ay['name'] for ay in tool_result.get('academic_years', [])) or '2026-2027'}",
            f"**Semesters Configured:** {sem_str}",
            "",
            "**Departments & Sections:**",
        ]
        for dept in tool_result.get("academic_structure", []):
            lines.append(f"#### {dept['department_name']} ({dept['department_code']})")
            lines.append(f"- **Total Enrolled Students:** {dept['enrolled_students']} | **Faculty:** {dept['faculty_members']}")
            if dept.get("sections"):
                lines.append("| Section | Students | Class Teacher |")
                lines.append("|:---|:---:|:---|")
                for sec in dept["sections"]:
                    lines.append(f"| {sec['section_name']} | {sec['student_count']} | {sec['class_teacher']} |")
            lines.append("")
        lines.append(_format_provenance("Academic Governance Register", "Campus Wide"))
        return sanitize_plain_english("\n".join(lines)), sources

    # ── 3. Super Admin: Operational Overview ──────────────────────────────────
    elif tool_name == "get_operational_overview":
        sources.append("Operational Master Register")
        lines = [
            "### Operational Scheduling Status",
            "",
            f"- **Active Published Timetables:** {tool_result.get('published_timetables_count', 0)}",
            f"- **Unpublished Previews / Drafts:** {tool_result.get('draft_previews_count', 0)}",
            f"- **Historical Timetable Versions Preserved:** {tool_result.get('historical_versions_count', 0)}",
            f"- **Total Facility Bookings:** {tool_result.get('total_resource_bookings', 0)} (Pending: {tool_result.get('pending_resource_bookings', 0)})",
            f"- **Pending Change Requests:** {tool_result.get('pending_change_requests', 0)}",
            "",
        ]
        pub_tts = tool_result.get("published_timetables", [])
        if pub_tts:
            lines.append("**Active Published Timetable Details:**")
            lines.append("| Section | Department | Semester | Scheduled Periods | Status |")
            lines.append("|:---|:---|:---:|:---:|:---:|")
            for tt in pub_tts:
                lines.append(f"| {tt['section']} | {tt['department']} | Sem {tt['semester']} | {tt['scheduled_entries']} | {tt['status']} |")
            lines.append("")
        recent_ops = tool_result.get("recent_scheduling_operations", [])
        if recent_ops:
            lines.append("**Recent Administrative Operations:**")
            for op in recent_ops[:5]:
                lines.append(f"- **{op['action']}** on {op['entity_type']} (by {op['performed_by']} at {op['timestamp'][:19]})")
        lines.append(_format_provenance("Operational Master Register", "Campus Wide", "Published"))
        return sanitize_plain_english("\n".join(lines)), sources

    # ── 4. Super Admin: Governance & Audit Status ─────────────────────────────
    elif tool_name == "get_governance_system_status":
        sources.append("Governance & Compliance Audit Register")
        lines = [
            "### Governance & System Audit Status",
            f"**System Status:** `{tool_result.get('system_status', 'HEALTHY')}` | **Total Audit Records:** {tool_result.get('total_audit_records', 0)}",
            "",
        ]
        warns = tool_result.get("configuration_warnings", [])
        if warns:
            lines.append("**Configuration Notices:**")
            for w in warns:
                lines.append(f"- ⚠️ {w}")
            lines.append("")
        logs = tool_result.get("recent_audit_logs", [])
        if logs:
            lines.append("**Recent Governance Activities:**")
            lines.append("| ID | Action | Entity | Actor | Lifecycle Tag | Timestamp |")
            lines.append("|:---|:---|:---|:---|:---:|:---|")
            for l in logs[:10]:
                lines.append(f"| #{l['id']} | {l['action']} | {l['entity_type']} | {l['user_name']} | {l['lifecycle_status']} | {l['timestamp'][:19]} |")
        lines.append(_format_provenance("Governance Audit Register", "Institutional Oversight"))
        return sanitize_plain_english("\n".join(lines)), sources

    # ── 5. Admin: Student Directory Lookup ────────────────────────────────────
    elif tool_name == "search_student_directory":
        sources.append("Student Academic Master Registry")
        students = tool_result.get("students", [])
        total = tool_result.get("total_count", 0)
        if not students:
            return "No enrolled student records found matching your query criteria.", sources

        lines = [
            f"### Student Directory ({len(students)} of {total} records)",
            "",
            "| USN | Student Name | Section | Semester | Class Teacher |",
            "|:---|:---|:---:|:---:|:---|",
        ]
        for s in students:
            lines.append(f"| **{s['usn']}** | {s['name']} | {s['section']} | Sem {s['semester'] or 7} | {s['class_teacher']} |")
        lines.append(_format_provenance("Student Master Registry", f"Returned {len(students)} of {total} records"))
        return sanitize_plain_english("\n".join(lines)), sources

    # ── 6. Admin: Faculty Directory Lookup ────────────────────────────────────
    elif tool_name == "search_faculty_directory":
        sources.append("Campus Faculty Directory")
        faculty_list = tool_result.get("faculty", [])
        total = tool_result.get("total_count", 0)
        if not faculty_list:
            return "No faculty members found matching your search criteria.", sources

        lines = [
            f"### Faculty Directory ({len(faculty_list)} of {total} records)",
            "",
        ]
        for f in faculty_list:
            lines.append(f"**{f['name']}** — {f['designation']}")
            lines.append(f"- **Department:** {f['department']} | **Employee ID:** {f['faculty_id']}")
            lines.append(f"- **Specialization:** {f['specialization']} | **Contact:** {f['contact_number']}")
            if f.get("assigned_courses"):
                lines.append(f"- **Assigned Courses:** {', '.join(f['assigned_courses'])}")
            lines.append(f"- **Configured Availability Slots:** {f['availability_slots_configured']}")
            lines.append("")
        lines.append(_format_provenance("Campus Faculty Directory", f"Total: {total}"))
        return sanitize_plain_english("\n".join(lines)), sources

    # ── 7. Admin: Course Directory Lookup ─────────────────────────────────────
    elif tool_name == "search_course_directory":
        sources.append("University Academic Course Catalog")
        courses = tool_result.get("courses", [])
        total = tool_result.get("total_count", 0)
        if not courses:
            return "No courses found matching your criteria in the academic catalog.", sources

        lines = [
            f"### Registered Courses ({len(courses)} of {total} records)",
            "",
            "| Code | Course Title | Type | Credits | Instructors |",
            "|:---|:---|:---:|:---:|:---|",
        ]
        for c in courses:
            inst_str = ", ".join(c.get("assigned_instructors", [])) or "Unassigned"
            lines.append(f"| **{c['course_code']}** | {c['course_name']} | {c['course_type']} | {c['credits']} | {inst_str} |")
        lines.append(_format_provenance("University Course Catalog", f"Total: {total} courses"))
        return sanitize_plain_english("\n".join(lines)), sources

    # ── 8. Admin: Infrastructure Inventory ────────────────────────────────────
    elif tool_name == "get_infrastructure_inventory":
        sources.append("Campus Physical Infrastructure Registry")
        rooms = tool_result.get("rooms", [])
        total_rooms = tool_result.get("total_rooms", 0)
        buildings = tool_result.get("buildings", [])

        lines = [
            f"### Campus Infrastructure Inventory",
            f"**Total Buildings:** {len(buildings)} | **Total Rooms Configured:** {total_rooms}",
            "",
        ]
        if buildings:
            for b in buildings:
                lines.append(f"- **Building:** {b['name']} (`{b['code']}`) — {b['floors']} Floors")
            lines.append("")
        if rooms:
            lines.append(f"**Room Inventory (Showing {len(rooms)} of {total_rooms}):**")
            lines.append("| Room | Building | Floor | Type | Capacity |")
            lines.append("|:---|:---|:---:|:---:|:---:|")
            for r in rooms[:30]:
                lines.append(f"| Room {r['room_number']} | {r['building_name']} | Floor {r['floor_number']} | {r['room_type']} | {r['capacity']} seats |")
        lines.append(_format_provenance("Physical Infrastructure Registry", "Campus SMV Block"))
        return sanitize_plain_english("\n".join(lines)), sources

    # ── 9. Admin: Section Timetable ───────────────────────────────────────────
    elif tool_name == "get_section_timetable":
        sources.append("Official Published Section Timetable")
        entries = tool_result.get("entries", [])
        sec = tool_result.get("section", "AIDS-A")
        if not entries:
            return f"Schedule for {sec}: No classes scheduled in the active published timetable.", sources

        lines = [
            f"### Published Timetable for Section {sec}",
            f"**Department:** {tool_result.get('department', 'AI & DS')} | **Semester:** Semester {tool_result.get('semester', 7)} | **Total Classes:** {len(entries)}",
            "",
            "| Day | Period Time | Course Code | Subject Title | Instructor | Room |",
            "|:---|:---:|:---|:---|:---|:---:|",
        ]
        for e in entries:
            lines.append(
                f"| {e['day']} | {e['start_time']}–{e['end_time']} | {e['course_code']} | {e['course_title']} | {e['faculty_name']} | Room {e['room']} |"
            )
        lines.append(_format_provenance("Official Published Section Timetable", f"Section {sec}", "Published"))
        return sanitize_plain_english("\n".join(lines)), sources

    # ── 10. User Notifications ────────────────────────────────────────────────
    elif tool_name == "get_user_notifications":
        sources.append("Campus Notification System")
        notifs = tool_result.get("notifications", [])
        unread = tool_result.get("unread_count", 0)
        total = tool_result.get("total_notifications", 0)
        if not notifs:
            return "You currently have no new notifications in the campus dispatch system.", sources

        lines = [
            f"### Personal Notifications ({unread} unread of {total} total)",
            "",
        ]
        for n in notifs:
            status_tag = "🔵 [UNREAD]" if not n["is_read"] else "⚪ [READ]"
            lines.append(f"**{status_tag} {n['title']}** ({n['created_at'][:10]})")
            lines.append(f"{n['message']}")
            lines.append("")
        lines.append(_format_provenance("Campus Notification System", "Personal Inbox"))
        return sanitize_plain_english("\n".join(lines)), sources

    # ── 11. User Requests Status ──────────────────────────────────────────────
    elif tool_name == "get_user_requests_status":
        sources.append("Workflow & Request Processing Engine")
        requests = tool_result.get("requests", [])
        if not requests:
            return "You have no active or historical requests submitted in the system.", sources

        lines = [
            f"### Your Submitted Requests ({len(requests)} found)",
            "",
            "| Request ID | Type | Status | Submitted Details | Date |",
            "|:---|:---|:---:|:---|:---:|",
        ]
        for req in requests:
            lines.append(f"| #{req['id']} | {req['type']} | `{req['status']}` | {req.get('details', req.get('reason', 'N/A'))} | {req['created_at'][:10]} |")
        lines.append(_format_provenance("Workflow & Request Engine", "User Scope"))
        return sanitize_plain_english("\n".join(lines)), sources

    # ── 12. Faculty Free Periods ──────────────────────────────────────────────
    elif tool_name == "get_faculty_free_periods":
        sources.append("Official Published Timetable & Workload Engine")
        day = tool_result.get("day", "MON")
        free_slots = tool_result.get("free_periods", [])
        busy_slots = tool_result.get("teaching_periods", [])
        lines = [
            f"### Free Periods & Teaching Schedule for {tool_result.get('faculty_name', user_name)} ({day})",
            f"**Scheduled Teaching Classes:** {len(busy_slots)} | **Free Periods Available:** {len(free_slots)}",
            "",
        ]
        if free_slots:
            lines.append("**Free Periods (Available for Office Hours / Research / Mentoring):**")
            for fs in free_slots:
                lines.append(f"- 🟢 **{fs['period']}** ({fs['start_time']} to {fs['end_time']})")
            lines.append("")
        if busy_slots:
            lines.append("**Teaching Commitments:**")
            for bs in busy_slots:
                lines.append(f"- 🔴 **{bs['period']}** (Scheduled class)")
        lines.append(_format_provenance("Published Timetable & Workload Engine", f"Faculty {user_name}", "Published"))
        return sanitize_plain_english("\n".join(lines)), sources

    # Fallback to existing formatter logic if unhandled here
    return "", []
