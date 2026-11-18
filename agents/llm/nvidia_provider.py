"""
agents/llm/nvidia_provider.py
------------------------------
NVIDIA NIM LLM Provider for RIO-MJP Multi-Agent Campus Assistant.
Powered by:
- Provider: NVIDIA NIM
- Base URL: https://integrate.api.nvidia.com/v1 (or NVIDIA_BASE_URL)
- Default Model: nvidia/nemotron-3-ultra-550b-a55b (or nvidia/nemotron-3.5-lightning-30b-a3b via NVIDIA_MODEL)
- Official Prototype Config:
    temperature = 1
    top_p = 0.95
    max_tokens = 16384
    extra_body = {"chat_template_kwargs": {"enable_thinking": True, "force_nonempty_content": True}}

Enforces:
- Dynamic natural-language query reasoning (zero regex or keyword gating).
- Multi-step tool calling loop with execution against PostgreSQL database services.
- Removal of internal reasoning tokens (<thought>...</thought>).
- Strict factual grounding and direct answers (never redirect to UI/settings).
- Graceful offline/fallback handling if API key is absent or network fails.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_message_function_tool_call_param import (
    ChatCompletionMessageFunctionToolCallParam,
)
from sqlalchemy.orm import Session

from backend.models.identity import User
from agents.common.diagnostics import (
    ChatRequestTrace,
    sanitize_for_logging,
    sanitize_log_message,
)
from agents.llm.provider_interface import (
    BaseLLMProvider,
    FormattedResponseResult,
    IntentExtractionResult,
)
from agents.tools import QUERY_TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger("agents.llm.nvidia_provider")


def strip_thinking(text: Optional[str]) -> str:
    """
    Strips internal model reasoning tokens (<thought>...</thought> or <thinking>...</thinking>)
    ensuring only user-facing, direct answers are presented.
    """
    if not text:
        return ""
    # Strip closed thought blocks
    cleaned = re.sub(r"<thought>[\s\S]*?</thought>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<thinking>[\s\S]*?</thinking>", "", cleaned, flags=re.IGNORECASE)
    # Strip any unclosed thought tags at the start of output
    cleaned = re.sub(r"^<thought>[\s\S]*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^<thinking>[\s\S]*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def is_unusable_response(text: Optional[str]) -> bool:
    """
    Evaluates whether the model's text response is empty, whitespace-only,
    or generic placeholder trace output that lacks actual data synthesis.
    """
    if not text or not text.strip():
        return True
    t_lower = text.lower().strip()
    # Check for empty or generic fallback trace
    if "executed tool" in t_lower and len(text.splitlines()) <= 5:
        return True
    if "tool 1 executed successfully" in t_lower:
        return True
    if t_lower.startswith("here are the database records matching your inquiry") and "- executed tool" in t_lower:
        return True
    return False


def synthesize_single_tool_result(
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Any,
    user: User,
) -> str:
    """
    Deterministically synthesizes a single tool execution result into a natural,
    database-grounded Markdown response without exposing internal tool names or traces.
    """
    if not isinstance(tool_result, dict):
        if tool_result is None:
            return "No records were returned by the campus database."
        return str(tool_result)

    # 1. Check for errors or access restrictions
    if "error" in tool_result and tool_result["error"]:
        err_msg = str(tool_result["error"])
        if "access denied" in err_msg.lower() or "not authorized" in err_msg.lower() or "forbidden" in err_msg.lower():
            return f"Access Denied: {err_msg}"
        return f"Unable to retrieve the requested information: {err_msg}"

    # 2. Timetable & Schedule Tools
    if tool_name in ("get_my_timetable", "get_student_timetable", "get_faculty_timetable", "get_faculty_schedule", "get_section_timetable"):
        entries = tool_result.get("entries") or tool_result.get("classes") or []
        if not entries:
            msg = tool_result.get("message")
            if msg:
                return msg
            day = tool_args.get("day") or "the requested schedule"
            return f"No scheduled classes were found for {day}."

        lines = [f"### Timetable Schedule ({len(entries)} scheduled classes)\n"]
        for e in entries[:25]:
            day = e.get("day", "")
            st = e.get("start_time", "")
            et = e.get("end_time", "")
            time_str = f"{st} - {et}".strip(" -")
            c_name = e.get("course_name") or e.get("course_title") or e.get("course_code") or "Class"
            c_code = e.get("course_code", "")
            code_str = f" ({c_code})" if c_code and c_code != c_name else ""
            room = e.get("room_number") or e.get("room") or "TBD"
            fac = e.get("faculty_name") or e.get("instructor")
            fac_str = f" | Instructor: {fac}" if fac else ""
            lines.append(f"- **{day} {time_str}**: {c_name}{code_str} in Room **{room}**{fac_str}")
        if len(entries) > 25:
            lines.append(f"- ... and {len(entries) - 25} more scheduled classes.")
        return "\n".join(lines)

    if tool_name == "get_next_class":
        if tool_result.get("has_class"):
            c_name = tool_result.get("course_name", "Class")
            c_code = tool_result.get("course_code", "")
            st = tool_result.get("start_time", "")
            et = tool_result.get("end_time", "")
            room = tool_result.get("room_number", "TBD")
            fac = tool_result.get("faculty_name")
            fac_str = f" taught by **{fac}**" if fac else ""
            return f"Your next scheduled class is **{c_name}** ({c_code}) from **{st}** to **{et}** in **Room {room}**{fac_str}."
        return tool_result.get("message") or "You have no upcoming classes scheduled for the remainder of today."

    if tool_name == "get_first_class_tomorrow":
        if tool_result.get("has_class"):
            c_name = tool_result.get("course_name", "Class")
            c_code = tool_result.get("course_code", "")
            st = tool_result.get("start_time", "")
            room = tool_result.get("room_number", "TBD")
            return f"Your first class tomorrow is **{c_name}** ({c_code}) starting at **{st}** in **Room {room}**."
        return tool_result.get("message") or "No classes scheduled for tomorrow."

    if tool_name == "get_class_status":
        if tool_result.get("has_class"):
            status = tool_result.get("status", "SCHEDULED")
            c_name = tool_result.get("course_name", "")
            c_code = tool_result.get("course_code", "")
            st = tool_result.get("start_time", "")
            et = tool_result.get("end_time", "")
            room = tool_result.get("room_number", "TBD")
            return f"Current schedule status is **{status}**: **{c_name}** ({c_code}) in **Room {room}** ({st} - {et})."
        return tool_result.get("message") or "No classes currently in session."

    if tool_name == "get_department_timetable":
        entries = tool_result.get("entries", [])
        dept_name = tool_result.get("department_name", "the requested Department")
        if not entries:
            return tool_result.get("message") or f"No published timetable entries found for {dept_name}."
        lines = [f"### Timetable for {dept_name} ({len(entries)} entries)\n"]
        for e in entries[:25]:
            day = e.get("day", "")
            st = e.get("start_time", "")
            et = e.get("end_time", "")
            c_name = e.get("course_name", "Course")
            c_code = e.get("course_code", "")
            room = e.get("room_number", "TBD")
            sec = e.get("section_name", "")
            sec_str = f" | Section: {sec}" if sec else ""
            lines.append(f"- **{day} {st}-{et}**: {c_name} ({c_code}) in Room **{room}**{sec_str}")
        if len(entries) > 25:
            lines.append(f"- ... and {len(entries) - 25} more entries.")
        return "\n".join(lines)

    if tool_name == "get_published_timetable_status":
        if tool_result.get("has_published_timetable") is False:
            return tool_result.get("message") or "No published timetable is currently active for this semester."

        active_pub = tool_result.get("active_published_version")
        lines: List[str] = []
        if active_pub:
            v_num = active_pub.get("version_number", 1)
            acad_yr = active_pub.get("academic_year", "Current Year")
            entries_cnt = active_pub.get("total_entries", 0)
            lines.append(f"The active published timetable is **Version {v_num}** ({acad_yr}) with **{entries_cnt}** scheduled entries.")
        elif tool_result.get("has_published_timetable"):
            v_num = tool_result.get("version_number", 1)
            acad_yr = tool_result.get("academic_year", "Current Year")
            entries_cnt = tool_result.get("total_active_entries", 0)
            lines.append(f"The active published timetable is **Version {v_num}** ({acad_yr}) with **{entries_cnt}** scheduled entries.")
        else:
            tot_v = tool_result.get("total_versions", 0)
            lines.append(f"There are **{tot_v}** timetable version(s) recorded in the database, but none are currently published.")

        depts = (
            (active_pub and active_pub.get("departments_with_timetables"))
            or tool_result.get("departments_with_timetables")
            or []
        )
        if depts:
            lines.append("\nDepartments with currently generated timetables:\n" + "\n".join(f"- **{d}**" for d in depts))
        elif active_pub and active_pub.get("total_entries", 0) > 0:
            lines.append("\nTimetable entries have been generated for scheduled academic departments.")
        else:
            lines.append("\nNo departments currently have generated timetables.")
        return "\n".join(lines)

    # 3. People & Directory Tools
    if tool_name == "search_student_directory":
        students = tool_result.get("students", [])
        total = tool_result.get("total_count", len(students))
        if total == 0 or not students:
            return tool_result.get("message") or "No registered students found matching your criteria in the campus directory."
        lines = [f"Found **{total}** registered student(s):\n"]
        for s in students[:20]:
            name = s.get("name", "Student")
            usn = s.get("usn", "N/A")
            dept = s.get("department", "N/A")
            sec = s.get("section", "N/A")
            sem = s.get("semester")
            sem_str = f", Semester: {sem}" if sem else ""
            lines.append(f"- **{name}** (USN: `{usn}`) — Department: {dept}, Section: {sec}{sem_str}")
        if total > 20:
            lines.append(f"- ... and {total - 20} more student records.")
        return "\n".join(lines)

    if tool_name in ("search_faculty_directory", "get_faculty_profile", "get_faculty_information"):
        faculty_list = tool_result.get("faculty") or tool_result.get("results") or []
        total = tool_result.get("total_count", len(faculty_list))
        if total == 0 or not faculty_list:
            return tool_result.get("message") or "No faculty members found matching your query."
        lines = [f"Found **{total}** faculty member(s):\n"]
        for f in faculty_list[:20]:
            name = f.get("name", "Faculty Member")
            desig = f.get("designation", "Faculty")
            dept = f.get("department", "Academic Department")
            spec = f.get("specialization") or f.get("areas_of_interest")
            spec_str = f", Specialization: {spec}" if spec and spec != "N/A" else ""
            courses = f.get("assigned_courses") or f.get("courses_taught") or []
            c_str = f" | Courses: {', '.join(courses[:2])}" if courses else ""
            lines.append(f"- **{name}** ({desig}) — Department: {dept}{spec_str}{c_str}")
        if total > 20:
            lines.append(f"- ... and {total - 20} more faculty members.")
        return "\n".join(lines)

    # 4. Courses & Curriculum Tools
    if tool_name in ("search_course_directory", "get_semester_courses", "get_course_details", "get_course_information"):
        courses = tool_result.get("courses") or tool_result.get("results") or []
        total = tool_result.get("total_courses") or tool_result.get("total_count") or len(courses)
        if total == 0 or not courses:
            return tool_result.get("message") or "No courses found matching the requested criteria."
        sem = tool_result.get("semester_number")
        heading = f"Curriculum Courses for Semester {sem}" if sem else "Curriculum Courses"
        lines = [f"### {heading} ({total} courses)\n"]
        for c in courses[:25]:
            code = c.get("course_code", "N/A")
            title = c.get("course_name") or c.get("course_title") or "Course"
            credits = c.get("credits")
            c_type = c.get("course_type")
            details = []
            if credits:
                details.append(f"{credits} Credits")
            if c_type:
                details.append(c_type)
            det_str = f" ({', '.join(details)})" if details else ""
            lines.append(f"- **{code}**: {title}{det_str}")
        if total > 25:
            lines.append(f"- ... and {total - 25} more courses.")
        return "\n".join(lines)

    # 5. Rooms, Labs & Infrastructure Tools
    if tool_name in ("get_room_availability", "get_lab_availability"):
        avail = tool_result.get("available_rooms") or tool_result.get("rooms") or []
        occ = tool_result.get("occupied_rooms") or []
        if not avail and not occ:
            return tool_result.get("message") or "No active room records found for the specified parameters."
        lines = [f"Found **{len(avail)}** available room(s):\n"]
        for r in avail[:25]:
            r_num = r.get("room_number", "Room")
            bldg = r.get("building", "Main Campus")
            r_type = r.get("room_type", "Classroom")
            cap = r.get("capacity")
            cap_str = f", Capacity: {cap}" if cap else ""
            lines.append(f"- **Room {r_num}** ({bldg}) — Type: {r_type}{cap_str}")
        if len(avail) > 25:
            lines.append(f"- ... and {len(avail) - 25} other available rooms.")
        if occ:
            lines.append(f"\nCurrently occupied: **{len(occ)}** room(s).")
        return "\n".join(lines)

    if tool_name in ("get_building_rooms_and_labs_inventory", "get_infrastructure_inventory", "get_campus_room_inventory"):
        b_name = tool_result.get("building_name") or tool_result.get("building_code") or "Campus Infrastructure"
        lines = [f"### Infrastructure Inventory: {b_name}\n"]
        tot_r = tool_result.get("total_rooms", 0)
        tot_c = tool_result.get("total_classrooms", 0)
        tot_l = tool_result.get("total_labs", 0)
        tot_s = tool_result.get("total_seminar_halls", 0)
        lines.append(f"- Total Rooms: **{tot_r}** (Classrooms: {tot_c}, Labs: {tot_l}, Seminar Halls: {tot_s})")
        return "\n".join(lines)

    # 6. Bookings & Resources Tools
    if tool_name in ("get_user_bookings", "get_resource_booking_status"):
        bookings = tool_result.get("bookings", [])
        if not bookings:
            return "No resource bookings were found matching your criteria."
        lines = [f"Found **{len(bookings)}** resource booking(s):\n"]
        for b in bookings[:20]:
            r_name = b.get("resource_name", "Resource")
            date_str = b.get("date", "")
            st = b.get("start_time", "")
            et = b.get("end_time", "")
            status = b.get("status", "PENDING")
            purpose = b.get("purpose", "Academic use")
            req_by = b.get("requester_name")
            req_str = f" | Requester: {req_by}" if req_by else ""
            lines.append(f"- **{r_name}** on **{date_str}** ({st} - {et}) — Purpose: {purpose} | Status: **{status}**{req_str}")
        if len(bookings) > 20:
            lines.append(f"- ... and {len(bookings) - 20} more bookings.")
        return "\n".join(lines)

    # 7. Semantic Query Planner
    if tool_name == "execute_semantic_query":
        records = tool_result.get("records", [])
        entity = tool_result.get("entity", "records")
        if not records:
            return f"No matching records found in **{entity}**."

        # Check for aggregate result (e.g. single row with count)
        if len(records) == 1:
            row = records[0]
            count_keys = [k for k in row.keys() if "count" in k.lower()]
            if count_keys:
                return f"Total count of **{entity}**: **{row[count_keys[0]]}**."

        lines = [f"Query results for **{entity}** ({len(records)} records returned):\n"]
        for r in records[:15]:
            parts = [f"**{k}**: {v}" for k, v in r.items() if v is not None and not k.startswith("_")]
            lines.append(f"- " + ", ".join(parts))
        if len(records) > 15:
            lines.append(f"- ... and {len(records) - 15} more records.")
        return "\n".join(lines)

    # 8. Super Admin & Institutional Governance
    if tool_name == "get_institutional_overview":
        return (
            "### Institutional Governance Overview\n\n"
            f"- Academic Departments: **{tool_result.get('total_departments', 0)}**\n"
            f"- Degree Programs: **{tool_result.get('total_programs', 0)}**\n"
            f"- Total Enrolled Students: **{tool_result.get('total_students', 0)}**\n"
            f"- Active Faculty: **{tool_result.get('total_faculty', 0)}**\n"
            f"- Curriculum Courses: **{tool_result.get('total_courses', 0)}**\n"
            f"- Published Timetable: **{tool_result.get('timetable_status', 'None active')}**"
        )

    if tool_name == "get_academic_structure_overview":
        return (
            "### Campus Academic Structure\n\n"
            f"- Departments: **{tool_result.get('total_departments', 0)}**\n"
            f"- Programs: **{tool_result.get('total_programs', 0)}**\n"
            f"- Active Batches: **{tool_result.get('total_batches', 0)}**\n"
            f"- Academic Sections: **{tool_result.get('total_sections', 0)}**"
        )

    # 9. Generic Structured Dict Fallback
    summary_parts = []
    for k, v in tool_result.items():
        if k in ("source", "retrieved_at", "success") or k.startswith("_"):
            continue
        if isinstance(v, (str, int, float, bool)):
            summary_parts.append(f"- **{k.replace('_', ' ').capitalize()}**: {v}")
        elif isinstance(v, list) and v:
            summary_parts.append(f"- **{k.replace('_', ' ').capitalize()}**: {len(v)} item(s)")

    if summary_parts:
        return "### Verified Campus Records\n\n" + "\n".join(summary_parts)

    return "The campus database query completed, but no detailed record fields were returned."


def synthesize_tool_results_answer(
    user: User,
    user_message: str,
    executed_tool_records: List[Dict[str, Any]],
) -> str:
    """
    Synthesizes the overall user-facing answer from multiple executed tool records.
    Provides natural language transitions, highlights verified details,
    and cleanly distinguishes partial failures without leaking internal tool traces.
    """
    if not executed_tool_records:
        return "I processed your inquiry against the campus database, but no matching records were found."

    # If only one tool was executed, return its synthesized response directly
    if len(executed_tool_records) == 1:
        rec = executed_tool_records[0]
        return synthesize_single_tool_result(
            tool_name=rec["tool"],
            tool_args=rec.get("args", {}),
            tool_result=rec.get("result"),
            user=user,
        )

    # Multi-tool execution
    success_sections: List[str] = []
    failure_notices: List[str] = []

    for rec in executed_tool_records:
        t_name = rec["tool"]
        t_args = rec.get("args", {})
        t_res = rec.get("result")
        err = rec.get("error")

        if err or (isinstance(t_res, dict) and t_res.get("error")):
            failure_notices.append(f"Unable to retrieve records for {t_name.replace('_', ' ')}: {err or t_res.get('error')}")
        else:
            section_text = synthesize_single_tool_result(
                tool_name=t_name,
                tool_args=t_args,
                tool_result=t_res,
                user=user,
            )
            success_sections.append(section_text)

    output_parts: List[str] = []
    if success_sections:
        output_parts.append("\n\n---\n\n".join(success_sections))
    if failure_notices:
        notice_block = "\n".join(f"*Notice: {n}*" for n in failure_notices)
        output_parts.append(notice_block)

    return "\n\n".join(output_parts) if output_parts else "No records could be retrieved from the campus database."


class NvidiaNemotronProvider(BaseLLMProvider):
    """
    NVIDIA Nemotron Provider implementation connecting to NVIDIA NIM API.
    Interprets open-ended campus queries in real time and grounds answers via database tools.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = (api_key or os.environ.get("NVIDIA_API_KEY", "")).strip()
        self.base_url = (base_url or os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")).strip()
        self.model = (
            model
            or os.environ.get("NVIDIA_MODEL")
            or "nvidia/nemotron-3-ultra-550b-a55b"
        ).strip()
        self.temperature = float(os.environ.get("NVIDIA_TEMPERATURE", "1"))
        self.top_p = float(os.environ.get("NVIDIA_TOP_P", "0.95"))
        self.max_tokens = int(os.environ.get("NVIDIA_MAX_TOKENS", "16384"))

    def is_available(self) -> bool:
        """
        Checks if NVIDIA Nemotron provider is enabled and configured with a valid API key.
        """
        enabled = os.environ.get("RIO_CHAT_LLM_ENABLED", "false").strip().lower() in ("true", "1", "yes")
        provider_type = os.environ.get("RIO_CHAT_LLM_PROVIDER", "nvidia").strip().lower()

        if not enabled:
            return False
        if provider_type != "nvidia":
            return False
        if not self.api_key:
            return False
        if self.api_key.startswith("mock-") or self.api_key.startswith("test-") or self.api_key == "your_nvidia_api_key_here":
            return False

        return True

    def build_system_prompt(self, user: User) -> str:
        """
        Constructs the authoritative system prompt for NVIDIA Nemotron.
        Mandates direct answers, factual grounding, and role-based data access.
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"""You are the official RIO Campus Assistant, an intelligent, factual AI assistant for campus operations, academic schedules, facilities, and university records.

Caller Identity:
- User ID: {user.id}
- Name: {user.name or 'User'}
- Role: {user.role}
- Department ID: {user.department_id if user.department_id is not None else 'Campus-wide / None'}
- Current Timestamp: {now_utc}

CORE OPERATING MANDATES:
1. DIRECT FACTUAL ANSWERS ONLY:
   - You must NEVER give evasive non-answers or redirect the user to UI pages, portals, or settings menus.
   - NEVER say "You can view your timetable by navigating to the timetable page" or "Check the system settings".
   - Fetch the actual records using your available database tools and state the verified facts directly with exact numbers, names, locations, and timings.

2. TOOL CALLING & DATABASE GROUNDING:
   - Every single campus fact MUST be grounded in tool results. Never invent, assume, or synthesize facts.
   - For personal upcoming schedule questions (e.g. "When is my next class?"): call 'get_next_class' or 'get_class_status'.
   - For availability / free period questions (e.g. "When am I free?"): call 'get_faculty_free_periods'.
   - For faculty student roster questions (e.g. "Who are my students?"): call 'get_my_students'.
   - For flexible data querying, filtering, counting, aggregation, joins across entities: call 'execute_semantic_query'.
   - If a tool returns an empty result or indicates no records exist, report that honestly to the user. Never manufacture data or fill gaps with pretraining guesses.

3. STRICT ROLE-BASED ACCESS & PERMISSIONS:
   - The server enforces strict data isolation based on the caller's role ({user.role}).
   - Students cannot access other students' private records.
   - Non-admins cannot access system audit logs.
   - Respect institutional scope boundaries.

4. OUTPUT FORMATTING:
   - Deliver clear, well-structured markdown answers.
   - Use markdown bullet points, tables, or bold headers where helpful.
   - Keep answers direct, professional, and helpful.
"""

    def get_allowed_tools_schema(self, user_role: str) -> List[ChatCompletionToolParam]:
        """
        Filters and converts tool definitions to the standard OpenAI function tool format.
        """
        openai_tools: List[ChatCompletionToolParam] = []

        for t in QUERY_TOOL_DEFINITIONS:
            allowed = set(t.get("allowed_roles", []))
            # Super Admin has access to Admin tools
            if "ADMIN" in allowed and user_role == "SUPER_ADMIN":
                is_permitted = True
            else:
                is_permitted = user_role in allowed

            if not is_permitted:
                continue

            tool_entry: ChatCompletionToolParam = {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            openai_tools.append(tool_entry)

        return openai_tools

    def generate_chat_response(
        self,
        message: str,
        user: User,
        db: Session,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Executes real-time natural language reasoning using NVIDIA Nemotron.
        Runs a multi-turn tool calling loop directly against PostgreSQL database services.
        Strips thinking tokens and produces a direct, grounded answer.
        """
        client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=30.0,
            max_retries=2,
        )

        system_prompt = self.build_system_prompt(user)
        tools = self.get_allowed_tools_schema(user.role)

        # Build message history with SDK-supported typed message parameters
        messages: List[ChatCompletionMessageParam] = []
        system_msg: ChatCompletionSystemMessageParam = {
            "role": "system",
            "content": system_prompt,
        }
        messages.append(system_msg)

        if conversation_history:
            for item in conversation_history[-8:]:
                sender = item.get("sender")
                content = item.get("content", "")
                if content:
                    if sender == "user":
                        user_hist_msg: ChatCompletionUserMessageParam = {
                            "role": "user",
                            "content": content,
                        }
                        messages.append(user_hist_msg)
                    else:
                        assistant_hist_msg: ChatCompletionAssistantMessageParam = {
                            "role": "assistant",
                            "content": content,
                        }
                        messages.append(assistant_hist_msg)

        current_user_msg: ChatCompletionUserMessageParam = {
            "role": "user",
            "content": message,
        }
        messages.append(current_user_msg)

        trace = ChatRequestTrace(
            user_id=user.id,
            role=user.role,
            message_length=len(message),
            provider="nvidia",
            model=self.model,
            llm_mode=True,
        )
        trace.mark_nvidia_start(self.model)

        executed_tool_calls: List[Dict[str, Any]] = []
        executed_tool_records: List[Dict[str, Any]] = []
        sources: List[str] = ["NVIDIA Nemotron", "RIO Database Grounding"]

        max_iterations = 5
        final_text = ""

        try:
            for iteration in range(max_iterations):
                if tools:
                    response = client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        tools=tools,
                        tool_choice="auto",
                        temperature=self.temperature,
                        top_p=self.top_p,
                        max_tokens=self.max_tokens,
                        extra_body={
                            "chat_template_kwargs": {
                                "enable_thinking": True,
                                "force_nonempty_content": True,
                            }
                        },
                    )
                else:
                    response = client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=self.temperature,
                        top_p=self.top_p,
                        max_tokens=self.max_tokens,
                        extra_body={
                            "chat_template_kwargs": {
                                "enable_thinking": True,
                                "force_nonempty_content": True,
                            }
                        },
                    )

                choice = response.choices[0]
                msg = choice.message

                # If model requested tool calls, execute them
                if msg.tool_calls:
                    tool_calls_param: List[ChatCompletionMessageFunctionToolCallParam] = []
                    for tc in msg.tool_calls:
                        if tc.type == "function":
                            tool_calls_param.append({
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            })

                    assistant_msg: ChatCompletionAssistantMessageParam = {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": tool_calls_param,
                    }
                    messages.append(assistant_msg)

                    for tc in msg.tool_calls:
                        if tc.type != "function":
                            continue
                        tool_name = tc.function.name
                        try:
                            tool_args = json.loads(tc.function.arguments or "{}")
                        except Exception:
                            tool_args = {}

                        safe_args = sanitize_for_logging(tool_args)
                        logger.info("NVIDIA Nemotron called tool '%s' with sanitized args %s", tool_name, safe_args)
                        t0 = time.perf_counter()
                        tool_result = execute_tool(
                            tool_name=tool_name,
                            tool_args=tool_args,
                            user=user,
                            db=db,
                        )
                        elapsed_tool_ms = (time.perf_counter() - t0) * 1000

                        # Determine record count safely
                        rec_count = 0
                        if isinstance(tool_result, dict):
                            if "total_returned" in tool_result:
                                rec_count = int(tool_result["total_returned"])
                            elif "total_students" in tool_result:
                                rec_count = int(tool_result["total_students"])
                            elif "records" in tool_result and isinstance(tool_result["records"], list):
                                rec_count = len(tool_result["records"])
                            elif "students" in tool_result and isinstance(tool_result["students"], list):
                                rec_count = len(tool_result["students"])
                            elif "classes" in tool_result and isinstance(tool_result["classes"], list):
                                rec_count = len(tool_result["classes"])
                            elif "entries" in tool_result and isinstance(tool_result["entries"], list):
                                rec_count = len(tool_result["entries"])
                            elif tool_result.get("found") is True:
                                rec_count = 1

                        tool_err = tool_result.get("error") if isinstance(tool_result, dict) else None
                        trace.record_tool_call(
                            tool_name=tool_name,
                            args=tool_args,
                            records_count=rec_count,
                            duration_ms=elapsed_tool_ms,
                            success=tool_err is None,
                            error=tool_err,
                        )

                        executed_tool_calls.append({"tool": tool_name, "args": tool_args})
                        executed_tool_records.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result": tool_result,
                            "records_count": rec_count,
                            "error": tool_err,
                        })
                        if isinstance(tool_result, dict) and "source" in tool_result:
                            sources.append(tool_result["source"])

                        tool_msg: ChatCompletionToolMessageParam = {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(tool_result, default=str),
                        }
                        messages.append(tool_msg)

                    # Continue loop to allow model to synthesize tool results
                    continue

                # If no tool calls, model provided the final text response
                raw_content = msg.content or ""
                final_text = strip_thinking(raw_content)
                break

            # If final_text is empty or generic trace, synthesize from executed tool data
            if is_unusable_response(final_text):
                if executed_tool_records:
                    final_text = synthesize_tool_results_answer(
                        user=user,
                        user_message=message,
                        executed_tool_records=executed_tool_records,
                    )
                else:
                    final_text = (
                        "I processed your inquiry against the campus database, but no matching records were found."
                    )

            trace.mark_nvidia_received()
            diagnostics_summary = trace.finalize(success=True)

            return {
                "reply": final_text,
                "intent": "OPEN_ENDED_LLM_QUERY",
                "selected_agent": "nvidia_nemotron",
                "tool_calls": executed_tool_calls,
                "sources": list(dict.fromkeys(sources)),
                "proposal": None,
                "action_type": None,
                "success": True,
                "error": None,
                "diagnostics": diagnostics_summary,
            }

        except Exception as exc:
            safe_exc_msg = sanitize_log_message(str(exc))
            logger.error("NVIDIA Nemotron API call failed: %s", safe_exc_msg, exc_info=True)
            if executed_tool_records:
                logger.info(
                    "Synthesizing deterministic answer from %d executed tools despite LLM error",
                    len(executed_tool_records),
                )
                final_text = synthesize_tool_results_answer(
                    user=user,
                    user_message=message,
                    executed_tool_records=executed_tool_records,
                )
                diagnostics_summary = trace.finalize(success=True)
                return {
                    "reply": final_text,
                    "intent": "OPEN_ENDED_LLM_QUERY",
                    "selected_agent": "nvidia_nemotron",
                    "tool_calls": executed_tool_calls,
                    "sources": list(dict.fromkeys(sources)),
                    "proposal": None,
                    "action_type": None,
                    "success": True,
                    "error": None,
                    "diagnostics": diagnostics_summary,
                }
            diagnostics_summary = trace.finalize(success=False, error=safe_exc_msg)
            return {
                "reply": "",
                "intent": "ERROR",
                "selected_agent": "nvidia_nemotron",
                "tool_calls": executed_tool_calls,
                "sources": sources,
                "success": False,
                "error": str(exc),
                "diagnostics": diagnostics_summary,
            }

    def extract_intent_and_entities(
        self,
        message: str,
        role: str,
        conversation_history: List[Dict[str, Any]],
    ) -> IntentExtractionResult:
        """Protocol compliance implementation."""
        return IntentExtractionResult(
            intent="NVIDIA_NEMOTRON_DYNAMIC_REASONING",
            confidence=1.0,
        )

    def format_grounded_response(
        self,
        query: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_result: Dict[str, Any],
        role: str,
        user_name: str,
    ) -> FormattedResponseResult:
        """Protocol compliance implementation."""
        return FormattedResponseResult(
            content="",
            sources=["NVIDIA Nemotron"],
            confidence=1.0,
        )

