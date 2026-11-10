"""
agents/intent/intent_catalog.py
-------------------------------
Structured intent catalog and entity extraction engine for RIO-MJP.
Deterministically classifies incoming user requests, normalizes natural-language variants,
extracts academic entities (USN, Faculty, Course, Section, Building, Room, Day/Time),
and verifies role-level authorization boundaries.
Detects ambiguous queries and prompts the user for clarification based on their role.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.models.identity import User


@dataclass
class IntentMatch:
    intent_name: str
    tool_name: Optional[str]
    tool_args: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    is_ambiguous: bool = False
    clarification_prompt: Optional[str] = None
    extracted_entities: Dict[str, Any] = field(default_factory=dict)


def normalize_text(text: str) -> str:
    """Normalizes whitespace, punctuation, and capitalization."""
    t = text.lower().strip()
    # Normalize punctuation except hyphens in codes like AIDS-A, SMV-BLK-01
    t = re.sub(r"[^\w\s\-\.]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def extract_entities(text: str) -> Dict[str, Any]:
    """
    Extracts structured institutional entities:
    - USN (e.g. R23EH001, STU82357)
    - Section (e.g. AIDS-A, AIDS A)
    - Building (e.g. SMV block, Vishwesh block)
    - Room Number (e.g. 208, 807, B204)
    - Semester (e.g. semester 7, sem 7, 7th sem)
    - Day (e.g. TODAY, TOMORROW, MONDAY..SATURDAY)
    - Faculty Honorific/Name
    - Course code / keywords
    """
    entities: Dict[str, Any] = {}
    norm = normalize_text(text)

    # 1. USN / SRN (e.g., R23EH001..R23EH060, STU\d+)
    usn_m = re.search(r"\b(r23eh\d{3}|stu\d+)\b", norm, re.IGNORECASE)
    if usn_m:
        entities["usn"] = usn_m.group(1).upper()
        entities["student_usn"] = usn_m.group(1).upper()

    # 2. Section
    sec_m = re.search(r"\b(aids\s*-?\s*[a-d]|cse\s*-?\s*[a-d]|sec\s*[a-d])\b", norm, re.IGNORECASE)
    if sec_m:
        raw_sec = sec_m.group(1).upper().replace(" ", "")
        if "AIDS" in raw_sec and "-" not in raw_sec:
            raw_sec = raw_sec.replace("AIDS", "AIDS-")
        entities["section_name"] = raw_sec

    # 3. Semester number
    sem_m = re.search(r"\b(?:sem|semester)\s*([1-8])\b|\b([1-8])(?:st|nd|rd|th)?\s*(?:sem|semester)\b", norm)
    if sem_m:
        entities["semester_number"] = int(sem_m.group(1) or sem_m.group(2))

    # 4. Day of the week
    if "today" in norm:
        entities["day"] = "TODAY"
    elif "tomorrow" in norm:
        entities["day"] = "TOMORROW"
    else:
        for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]:
            if d in norm:
                entities["day"] = d.upper()
                break

    # 5. Building
    if any(k in norm for k in ["smv", "vishwesh", "sir m v"]):
        entities["building"] = "SMV-BLK-01"

    # 6. Specific room number
    rm_m = re.search(r"\b(?:room|lab|classroom)\s*([a-z0-9\-]+)\b", norm)
    if rm_m:
        entities["room_number"] = rm_m.group(1).upper()

    # 7. Faculty honorific
    fac_m = re.search(r"(?:dr\.?|prof\.?|professor|faculty member|faculty)\s+([a-z]+(?:\s+[a-z]+)*)", norm)
    if fac_m:
        entities["faculty_name"] = fac_m.group(1).title()

    return entities


def match_intent(
    message: str,
    user: User,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> IntentMatch:
    """
    Evaluates message against structured intent rules with role awareness.
    """
    msg = normalize_text(message)
    entities = extract_entities(message)
    role = user.role

    # ── Ambiguity Check ────────────────────────────────────────────────────────
    # e.g., Bare query "Show the timetable."
    if msg in ["show the timetable", "show timetable", "view timetable", "timetable"]:
        if role in ("ADMIN", "SUPER_ADMIN"):
            return IntentMatch(
                intent_name="AMBIGUOUS_TIMETABLE_REQUEST",
                tool_name=None,
                is_ambiguous=True,
                clarification_prompt=(
                    "Which timetable would you like to view?\n"
                    "- The timetable for a specific section (e.g. AIDS-A)\n"
                    "- A faculty member's teaching schedule\n"
                    "- Overall timetable publication status"
                ),
            )
        elif role == "FACULTY":
            return IntentMatch(
                intent_name="AMBIGUOUS_TIMETABLE_REQUEST",
                tool_name=None,
                is_ambiguous=True,
                clarification_prompt=(
                    "Would you like to view your personal teaching timetable or your assigned section's timetable (AIDS-A)?"
                ),
            )
        elif role == "STUDENT":
            # For students, "show timetable" directly defaults to their personal timetable
            return IntentMatch(
                intent_name="STUDENT_TIMETABLE",
                tool_name="get_my_timetable",
                tool_args={},
            )

    # ── Super Admin Intents ────────────────────────────────────────────────────
    if role == "SUPER_ADMIN":
        if any(k in msg for k in [
            "institutional overview", "institution overview", "campus overview", "university overview",
            "how many students are registered", "how many faculty", "how many departments", "how many programs",
            "how many courses are registered", "how many buildings",
        ]):
            return IntentMatch(
                intent_name="SUPER_ADMIN_INSTITUTIONAL_OVERVIEW",
                tool_name="get_institutional_overview",
                tool_args={},
            )

        if any(k in msg for k in [
            "academic structure", "structural overview", "which departments are configured",
            "academic overview", "departments configured",
        ]):
            return IntentMatch(
                intent_name="SUPER_ADMIN_ACADEMIC_STRUCTURE",
                tool_name="get_academic_structure_overview",
                tool_args={},
            )

        if any(k in msg for k in [
            "operational overview", "how many timetables are published", "how many timetables are currently published",
            "unpublished timetable previews", "scheduling operations", "operational status",
        ]):
            return IntentMatch(
                intent_name="SUPER_ADMIN_OPERATIONAL_OVERVIEW",
                tool_name="get_operational_overview",
                tool_args={},
            )

        if any(k in msg for k in [
            "audit activity", "recent audit", "governance status", "system configuration status",
            "incomplete institutional configuration", "system health", "governance",
        ]):
            return IntentMatch(
                intent_name="SUPER_ADMIN_GOVERNANCE_STATUS",
                tool_name="get_governance_system_status",
                tool_args={},
            )

    # ── Admin & Super Admin Shared Lookups ─────────────────────────────────────
    if role in ("ADMIN", "SUPER_ADMIN"):
        # 1. Student directory search
        if any(k in msg for k in ["find student", "lookup student", "search student", "show student", "show students"]):
            target_query = entities.get("usn")
            if not target_query:
                # check if name or code is in query
                m = re.search(r"(?:student|find)\s+([a-z0-9\-]+)", msg)
                target_query = m.group(1).upper() if m else None
            return IntentMatch(
                intent_name="ADMIN_STUDENT_LOOKUP",
                tool_name="search_student_directory",
                tool_args={
                    "search_query": target_query,
                    "section_name": entities.get("section_name"),
                    "semester_number": entities.get("semester_number"),
                },
                extracted_entities=entities,
            )

        # 2. Faculty directory search
        if any(k in msg for k in ["find faculty", "lookup faculty", "search faculty", "list faculty", "faculty member"]):
            name_q = entities.get("faculty_name")
            if not name_q:
                m = re.search(r"(?:faculty member|faculty|prof\.?|dr\.?)\s+([a-z]+(?:\s+[a-z]+)*)", msg)
                name_q = m.group(1).title() if m else None
            return IntentMatch(
                intent_name="ADMIN_FACULTY_LOOKUP",
                tool_name="search_faculty_directory",
                tool_args={"search_query": name_q},
                extracted_entities=entities,
            )

        # 3. Course directory search
        if any(k in msg for k in [
            "which courses belong", "how many subjects are registered", "show subjects for",
            "course assignments", "list courses", "show courses", "show registered courses",
            "registered courses", "all courses", "list all courses",
        ]):
            dept_q = "AI & DS" if any(k in msg for k in ["ai & ds", "aids", "ai and ds"]) else None
            return IntentMatch(
                intent_name="ADMIN_COURSE_LOOKUP",
                tool_name="search_course_directory",
                tool_args={
                    "department_name": dept_q,
                    "semester_number": entities.get("semester_number"),
                },
                extracted_entities=entities,
            )

        # 4. Infrastructure lookup
        if any(k in msg for k in ["how many rooms", "rooms in building", "show rooms", "room inventory", "which labs are configured", "room capacity"]):
            r_type = "LAB" if "lab" in msg else ("CLASSROOM" if "room" in msg or "classroom" in msg else None)
            return IntentMatch(
                intent_name="ADMIN_INFRASTRUCTURE_LOOKUP",
                tool_name="get_infrastructure_inventory",
                tool_args={
                    "building_name_or_code": entities.get("building") or "SMV-BLK-01",
                    "room_type": r_type,
                },
                extracted_entities=entities,
            )

        # 5. Section Timetable lookup
        if any(k in msg for k in ["timetable for", "schedule for"]) and entities.get("section_name"):
            return IntentMatch(
                intent_name="ADMIN_SECTION_TIMETABLE",
                tool_name="get_section_timetable",
                tool_args={
                    "section_name": entities.get("section_name", "AIDS-A"),
                    "day": entities.get("day"),
                },
                extracted_entities=entities,
            )

    # ── Faculty Personalized Queries ───────────────────────────────────────────
    if role == "FACULTY":
        # Free periods
        if any(k in msg for k in ["free period", "free periods", "free slots", "breaks", "when am i free"]):
            return IntentMatch(
                intent_name="FACULTY_FREE_PERIODS",
                tool_name="get_faculty_free_periods",
                tool_args={"day": entities.get("day")},
            )

        # First class today / tomorrow
        if "first class" in msg:
            return IntentMatch(
                intent_name="FACULTY_FIRST_CLASS",
                tool_name="get_first_class_tomorrow",
                tool_args={},
            )

        # Own teaching profile
        if any(k in msg for k in ["my faculty profile", "my profile", "which department am i", "my department"]):
            return IntentMatch(
                intent_name="FACULTY_OWN_PROFILE",
                tool_name="get_faculty_profile_and_classes",
                tool_args={},
            )

        # Courses taught
        if any(k in msg for k in ["which courses do i teach", "what courses do i teach", "what subjects do i teach", "which subjects am i assigned", "my course assignments"]):
            return IntentMatch(
                intent_name="FACULTY_ASSIGNED_COURSES",
                tool_name="get_faculty_profile_and_classes",
                tool_args={},
            )

        # Own timetable
        if any(k in msg for k in ["my timetable", "my schedule", "what classes do i have", "my teaching schedule", "classes today", "classes tomorrow"]):
            return IntentMatch(
                intent_name="FACULTY_TIMETABLE",
                tool_name="get_my_timetable",
                tool_args={"day": entities.get("day")},
                extracted_entities=entities,
            )

    # ── Student Personalized Queries ───────────────────────────────────────────
    if role == "STUDENT":
        # Student profile
        if (
            any(k in msg for k in ["my profile", "who am i", "what is my usn", "my usn", "what is my srn", "my srn", "which section am i"])
            or ("profile" in msg and ("student" in msg or entities.get("usn")))
        ):
            target_srn = entities.get("usn")
            return IntentMatch(
                intent_name="STUDENT_OWN_PROFILE",
                tool_name="get_student_academic_profile",
                tool_args={"target_srn": target_srn},
                extracted_entities=entities,
            )

        # Class teacher
        if "class teacher" in msg:
            return IntentMatch(
                intent_name="STUDENT_CLASS_TEACHER",
                tool_name="get_student_academic_profile",
                tool_args={},
            )

        # Enrolled subjects
        if any(k in msg for k in ["what subjects do i have", "my subjects", "which courses are part of my semester", "enrolled subjects"]):
            return IntentMatch(
                intent_name="STUDENT_ENROLLED_SUBJECTS",
                tool_name="get_student_enrolled_subjects",
                tool_args={},
            )

        # Next class / where is my class
        if any(k in msg for k in ["what is my next class", "next class", "which room is assigned to my next class", "which room should i go", "where is my next class"]):
            return IntentMatch(
                intent_name="STUDENT_NEXT_CLASS",
                tool_name="get_class_status",
                tool_args={},
            )

        # Own timetable
        if any(k in msg for k in ["my timetable", "my schedule", "what class do i have", "classes today", "classes tomorrow", "show my monday timetable"]):
            return IntentMatch(
                intent_name="STUDENT_TIMETABLE",
                tool_name="get_my_timetable",
                tool_args={"day": entities.get("day")},
                extracted_entities=entities,
            )

    # ── Shared User Queries (Notifications, Requests) ──────────────────────────
    if any(k in msg for k in ["notification", "notifications", "unread notification", "unread notifications", "notice", "notices"]):
        return IntentMatch(
            intent_name="USER_NOTIFICATIONS",
            tool_name="get_user_notifications",
            tool_args={"unread_only": "unread" in msg},
        )

    if any(k in msg for k in ["my request", "my requests", "submitted requests", "status of my request"]):
        return IntentMatch(
            intent_name="USER_REQUESTS_STATUS",
            tool_name="get_user_requests_status",
            tool_args={},
        )

    # ── Universal Course Faculty Queries ───────────────────────────────────────
    if any(k in msg for k in ["who teaches", "who is the faculty for", "faculty for", "instructor for"]):
        cq = msg
        m = re.search(r"(?:who teaches|faculty for|instructor for|professor for)\s+([a-z0-9\s\-]+?)(?:\?|$)", msg)
        if m:
            cq = m.group(1).strip()
        return IntentMatch(
            intent_name="COURSE_FACULTY_LOOKUP",
            tool_name="get_course_faculty",
            tool_args={"course_query": cq},
            extracted_entities=entities,
        )

    return IntentMatch(
        intent_name="FALLBACK",
        tool_name=None,
    )
