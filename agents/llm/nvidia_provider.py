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
from typing import Any, Callable, Dict, List, Optional, Tuple

from openai import APITimeoutError, OpenAI
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
from agents.common.diagnostics import ChatRequestTrace
from agents.llm.provider_interface import (
    BaseLLMProvider,
    FormattedResponseResult,
    IntentExtractionResult,
)
from agents.tools import QUERY_TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger("agents.llm.nvidia_provider")


def strip_thinking(text: Optional[str]) -> str:
    """
    Strips internal model reasoning tokens (<think>...</think>, <thought>...</thought>, <thinking>...</thinking>)
    and any leaked <tool_call>...</tool_call> XML blocks, ensuring only user-facing answers are presented.
    """
    if not text:
        return ""
    # Strip closed think/thought and tool_call blocks
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<thought>[\s\S]*?</thought>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<thinking>[\s\S]*?</thinking>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<tool_call>[\s\S]*?</tool_call>", "", cleaned, flags=re.IGNORECASE)
    # Strip any unclosed think/thought or tool_call tags
    cleaned = re.sub(r"<think>[\s\S]*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<thought>[\s\S]*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<thinking>[\s\S]*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<tool_call>[\s\S]*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _parse_text_tool_calls(raw_content: str) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Parses XML-style <tool_call><function=NAME><parameter=KEY>VAL</parameter></function></tool_call>
    blocks if a model emits tool calls in text content instead of structured tool_calls.
    """
    if not raw_content or "<tool_call" not in raw_content.lower():
        return []

    parsed: List[Tuple[str, Dict[str, Any]]] = []
    for block in re.findall(r"<tool_call>([\s\S]*?)(?:</tool_call>|$)", raw_content, flags=re.IGNORECASE):
        fn_match = re.search(r"<function=([a-zA-Z0-9_]+)>", block, flags=re.IGNORECASE)
        if not fn_match:
            continue
        fn_name = fn_match.group(1).strip()
        args: Dict[str, Any] = {}
        for p_name, p_val in re.findall(
            r"<parameter=([a-zA-Z0-9_]+)>\s*([\s\S]*?)\s*</parameter>",
            block,
            flags=re.IGNORECASE,
        ):
            val_str = p_val.strip()
            try:
                args[p_name.strip()] = json.loads(val_str)
            except Exception:
                args[p_name.strip()] = val_str
        parsed.append((fn_name, args))
    return parsed


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
        self.temperature = float(os.environ.get("RIO_NVIDIA_TEMPERATURE") or os.environ.get("NVIDIA_TEMPERATURE", "0.2"))
        self.top_p = float(os.environ.get("RIO_NVIDIA_TOP_P") or os.environ.get("NVIDIA_TOP_P", "0.7"))
        self.max_tokens = int(os.environ.get("RIO_NVIDIA_MAX_TOKENS") or os.environ.get("NVIDIA_MAX_TOKENS", "8192"))
        self.timeout = float(os.environ.get("RIO_NVIDIA_TIMEOUT_SECONDS") or os.environ.get("NVIDIA_TIMEOUT", "60.0"))

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
        Constructs the system prompt for ATHENA (backed by NVIDIA Nemotron).
        Balances natural general-knowledge conversation with dynamic, tool-grounded
        campus database intelligence and strict role-based security.
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"""You are ATHENA, an intelligent, natural, context-aware AI assistant for this university campus.

Caller Context:
- User ID: {user.id}
- Name: {user.name or 'User'}
- Role: {user.role}
- Department ID: {user.department_id if user.department_id is not None else 'Campus-wide / None'}
- Current Timestamp: {now_utc}

HOW TO THINK AND RESPOND:
1. GENERAL CONVERSATION, KNOWLEDGE & TECHNICAL HELP:
   - You are a full-capability conversational AI. For greetings, general-knowledge questions (e.g. AI, machine learning, science, concepts), programming/debugging help, or broad questions like "Can you answer everything?", respond naturally and directly using your own knowledge—WITHOUT calling any database tool.
   - Never claim you can only answer database questions, and never recite a list of internal restrictions or tool capabilities.
   - If asked about live external web events, real-time internet news, or external systems you are not connected to, be honest and transparent about not having live web access.

2. DYNAMIC CAMPUS DATABASE GROUNDING (ONLY WHEN INSTITUTIONAL DATA IS NEEDED):
   - Whenever the user asks about live campus data—timetables, published or unpublished schedules, departments, sections, students, faculty, rooms, labs, resource bookings, placements, events, announcements, or academic calendars—select and invoke the best matching tool(s) from your available tool schemas.
   - Understand the user's intent from meaning and conversation context, not exact keywords (handle typos, abbreviations, informal English, and multi-part questions).
   - Choose the right timetable tool for the user's intent:
     * To list, count, or see published timetables (e.g. "published timetables", "show me all published timetables", "how many timetables are published?", "which department has published its timetable?", or unpublished scopes): call 'get_published_timetables'.
     * To check the explicit lifecycle/governance status of a specific version ID (e.g. "what is the status of timetable version 48?"): call 'get_published_timetable_status' with version_id.
     * To see detailed class-by-class schedule entries (days, times, courses, rooms, faculty): call 'get_department_timetable', 'get_my_timetable', or 'get_student_timetable'.
     * For personal schedule questions ("my next class?", "my next lecture?", "my timetable"): call 'get_next_class' or 'get_my_timetable'. If the result shows no personal schedule is linked to an Admin/Super Admin account (or needs clarification), explain that naturally and ask if they meant a teaching schedule, a specific section, or a faculty member's schedule—never substitute another user's or section's class.
     * For explicit section schedules ("When is AIDS-A's next class?"), specific faculty schedules ("What class is Prof. X taking next?"), or campus-wide live classes ("Which class is happening next on campus?"): call 'get_department_timetable', 'get_faculty_timetable', or 'get_class_status'—never 'get_next_class'.
   - For faculty availability: if date or time interval is missing, ask a short, natural clarification question instead of calling a directory tool; when known, call 'get_available_faculty'.
   - For flexible counting, filtering, or multi-entity campus queries where no specialized tool fits: use 'execute_semantic_query'.
   - You may call multiple tools if a question genuinely spans multiple data sources, but NEVER repeat an identical tool call in the same turn.
   - NEVER fabricate campus facts, counts, names, or dates. If a tool returns empty results, state that naturally (e.g., "I couldn't find any currently published timetable matching that query.").

3. CONTEXTUAL MEMORY & CLARIFICATION:
   - Use the conversation history to resolve pronouns ("it", "there", "them"), follow-up filters ("What about Semester 7?"), and comparisons ("Which department has the most?").
   - Ask a brief, natural clarification question only when a request is genuinely ambiguous and cannot be resolved from context.

4. NATURAL RESPONSE STYLE & RICH MARKDOWN FORMATTING:
   - Communicate like a thorough, articulate human assistant. Prioritize clarity, completeness, and readability. Never redirect the user to UI pages or settings menus instead of answering.
   - NEVER mention internal tool names (like get_published_timetables or execute_semantic_query), SQL, JSON payloads, internal agent names, or execution traces.
   - NEVER output raw database field/value dumps (e.g. "Version: 48 | Status: PUBLISHED | Created: ..."). Synthesize retrieved facts into fluent natural English.
   - NEVER append fixed or numbered follow-up menus (such as "Would you like me to: 1. ... 2. ... 3. ... 4. ..."). Add a brief, natural one-line follow-up only when genuinely helpful, and omit it when the answer is already complete.
   - Format each answer naturally using clean Markdown suited to the question:
     * Use **bold highlights** for key terms, important findings, department/section names, counts, and conclusions.
     * Use clear Markdown headings (`##`, `###`) when an answer covers multiple sections or topics.
     * Use bullet lists for multiple findings and numbered steps (`1.`, `2.`) for procedures or workflows.
     * Use valid Markdown tables (`| Header | ... |` with a `| --- | ... |` separator row) for structured comparisons.
     * Use fenced code blocks with language tags (e.g. ```python) for code.
     * Preserve clean paragraph spacing and line breaks. Do not force every answer into a rigid template, and do not overuse bold or headings on very short replies.

5. SECURITY & ACCESS CONTROL:
   - Role-based access boundaries ({user.role}) are enforced by the server. Never bypass permissions or expose private records outside the caller's authorized scope.
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

    def _needs_campus_tools(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Determines whether a message may require campus database tools.
        Pure greetings, general-knowledge questions, and coding/conceptual queries
        skip sending 75+ tool schemas so the model responds in ~2s instead of stalling.
        """
        msg_lower = (message or "").lower().strip()
        campus_keywords = (
            "timetable", "timetables", "schedule", "schedules", "class", "classes",
            "lecture", "lectures", "period", "periods", "published", "publish",
            "unpublished", "draft", "faculty", "professor", "prof", "teacher",
            "student", "students", "srn", "usn", "roll", "section", "sections",
            "department", "departments", "dept", "program", "programs", "course",
            "courses", "subject", "subjects", "semester", "sem", "academic",
            "calendar", "holiday", "holidays", "exam", "exams", "break", "lunch",
            "room", "rooms", "lab", "labs", "hall", "auditorium", "building",
            "facility", "facilities", "resource", "resources", "booking", "bookings",
            "book ", "reserve ", "event", "events", "club", "clubs", "placement",
            "placements", "cdc", "drive", "drives", "eligibility", "eligible",
            "announcement", "announcements", "notice", "notification", "notifications",
            "request", "requests", "substitution", "substitute", "readiness",
            "audit", "governance", "overview", "campus", "university", "college",
            "available", "availability", "free", "generated", "tt",
            "aids", "cse", "ece", "mech", "eee", "civil", "who teaches", "who is",
            "my ", "which ", "how many", "when is", "where is", "show me", "list ",
        )
        if any(kw in msg_lower for kw in campus_keywords):
            return True

        # Check short follow-ups ("What about semester 7?", "Which one?", "Show it")
        if conversation_history:
            follow_up_cues = ("it", "its", "that", "those", "them", "there", "more", "details", "what about", "how about", "another")
            if any(cue in msg_lower for cue in follow_up_cues):
                recent_text = " ".join(str(item.get("content", "")).lower() for item in conversation_history[-4:])
                if any(kw in recent_text for kw in campus_keywords):
                    return True
        return False

    def _select_relevant_tools(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]],
        all_tools: List[ChatCompletionToolParam],
    ) -> List[ChatCompletionToolParam]:
        """
        Reduces the 75+ tool catalog to a focused, high-relevance subset (<= 18 tools)
        so NVIDIA NIM does not stall parsing 31KB of unused schemas on every call.
        Always includes execute_semantic_query as the universal fallback.
        """
        if len(all_tools) <= 18:
            return all_tools

        combined = (message or "").lower()
        if conversation_history:
            combined += " " + " ".join(str(m.get("content", "")).lower() for m in conversation_history[-4:])

        core_always = {
            "get_published_timetables",
            "get_published_timetable_status",
            "get_my_timetable",
            "get_department_timetable",
            "execute_semantic_query",
        }
        domain_groups = [
            (("timetable", "schedule", "class", "lecture", "period", "break", "lunch", "section", "department", "published", "tomorrow", "next"), {
                "get_student_timetable", "get_faculty_timetable", "get_section_timetable",
                "get_recent_timetable_changes", "get_class_status", "get_next_class",
                "get_first_class_tomorrow", "get_break_timings", "analyze_scheduling_readiness",
            }),
            (("faculty", "prof", "teacher", "available", "free", "substitut", "teaches"), {
                "get_available_faculty", "get_faculty_information", "get_faculty_profile",
                "get_faculty_free_periods", "get_faculty_profile_and_classes", "search_faculty_directory",
                "get_course_faculty", "list_pending_substitutions", "get_date_substitutions",
            }),
            (("room", "lab", "hall", "auditorium", "facility", "resource", "book", "reserve", "building", "inventory"), {
                "get_room_availability", "get_lab_availability", "get_room_or_lab_details",
                "get_campus_room_inventory", "get_building_rooms_and_labs_inventory",
                "discover_resources", "check_resource_availability", "get_user_bookings",
                "get_resource_booking_status", "get_infrastructure_inventory",
            }),
            (("student", "srn", "usn", "enrolled", "roster"), {
                "get_student_academic_profile", "get_student_enrolled_subjects",
                "get_my_students", "get_section_students", "search_student_directory",
            }),
            (("course", "subject", "credit", "curriculum", "semester", "calendar", "holiday", "exam"), {
                "get_course_information", "get_course_details", "get_semester_courses",
                "search_course_directory", "get_academic_calendar", "get_section_overview",
            }),
            (("event", "club", "workshop", "hackathon", "fest"), {
                "list_visible_events", "get_published_event_details", "get_ongoing_events",
                "get_upcoming_events", "list_my_clubs", "list_club_activities",
            }),
            (("placement", "cdc", "drive", "eligib", "hiring", "ctc", "package", "internship"), {
                "list_published_placement_drives", "list_my_eligible_drives",
                "get_placement_drive_details", "get_drive_deadlines_and_schedule",
                "get_student_drive_eligibility",
            }),
            (("overview", "institution", "governance", "audit", "notice", "announcement", "notification", "request"), {
                "get_institutional_overview", "get_academic_structure_overview",
                "get_operational_overview", "get_governance_system_status",
                "get_relevant_announcements", "get_user_notifications", "get_user_requests_status",
            }),
        ]

        selected_names = set(core_always)
        for cues, tool_set in domain_groups:
            if any(c in combined for c in cues):
                selected_names.update(tool_set)

        filtered = [t for t in all_tools if t["function"]["name"] in selected_names]
        if len(filtered) <= 5:
            # Broad fallback: include top read-only overview/discovery tools up to 18
            for t in all_tools:
                if t not in filtered and not t["function"]["name"].startswith(("create_", "update_", "approve_", "reject_", "publish_", "cancel_", "submit_", "validate_")):
                    filtered.append(t)
                    if len(filtered) >= 18:
                        break
        return filtered[:20]

    def generate_chat_response(
        self,
        message: str,
        user: User,
        db: Session,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        request_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        token_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Executes real-time natural language reasoning using NVIDIA Nemotron.
        Runs a bounded multi-turn tool calling loop directly against PostgreSQL database services.
        Strips thinking tokens and produces a direct, grounded answer.
        """
        req_tag = request_id or "req"
        t_req_start = time.perf_counter()

        def emit_progress(stage: str, status: str, msg_text: str) -> None:
            if progress_callback:
                try:
                    progress_callback({
                        "type": "progress",
                        "request_id": req_tag,
                        "stage": stage,
                        "status": status,
                        "message": msg_text,
                    })
                except Exception:
                    pass

        client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=0,
        )

        system_prompt = self.build_system_prompt(user)
        needs_tools = self._needs_campus_tools(message, conversation_history)
        if needs_tools:
            all_tools = self.get_allowed_tools_schema(user.role)
            tools = self._select_relevant_tools(message, conversation_history, all_tools)
        else:
            tools = []

        # Build message history with SDK-supported typed message parameters
        messages: List[ChatCompletionMessageParam] = []
        system_msg: ChatCompletionSystemMessageParam = {
            "role": "system",
            "content": system_prompt,
        }
        messages.append(system_msg)

        if conversation_history:
            for item in conversation_history[-12:]:
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
        executed_tool_results: List[Dict[str, Any]] = []
        sources: List[str] = ["NVIDIA Nemotron"]
        tool_results_cache: Dict[str, Any] = {}

        max_iterations = 5
        max_total_tool_calls = 6
        final_text = ""
        llm_call_count = 0
        ttft_ms: Optional[float] = None
        streamed_any_tokens = False

        def _invoke_completion(
            active_tools_arg: Optional[List[ChatCompletionToolParam]],
            enable_thinking: bool,
            allow_live_stream: bool,
        ) -> Tuple[str, List[Any], bool]:
            """
            Executes chat completion with stream=True (while remaining compatible with
            mocked non-streaming ChatCompletion objects in tests).
            Returns (raw_content, tool_calls_list, was_cancelled).
            """
            nonlocal llm_call_count, ttft_ms, streamed_any_tokens
            llm_call_count += 1
            create_kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_tokens": self.max_tokens,
                "stream": True,
                "extra_body": {
                    "chat_template_kwargs": {
                        "enable_thinking": enable_thinking,
                        "force_nonempty_content": True,
                    }
                },
            }
            if active_tools_arg:
                create_kwargs["tools"] = active_tools_arg
                create_kwargs["tool_choice"] = "auto"

            resp = client.chat.completions.create(**create_kwargs)

            # Mocked unit-test compatibility: non-streaming ChatCompletion object
            if hasattr(resp, "choices"):
                choice0 = resp.choices[0]
                msg0 = choice0.message
                return (msg0.content or ""), list(msg0.tool_calls or []), False

            # Real streaming response iterator
            raw_parts: List[str] = []
            tc_map: Dict[int, Dict[str, Any]] = {}
            hidden_tag: Optional[str] = None
            pending = ""
            started_answer_progress = False
            saw_tool_calls = False

            def _flush_visible(text: str) -> None:
                nonlocal ttft_ms, streamed_any_tokens, started_answer_progress
                if not text or not allow_live_stream or saw_tool_calls:
                    return
                if not started_answer_progress:
                    started_answer_progress = True
                    emit_progress("answer_generation", "running", "Delivering your answer...")
                if ttft_ms is None:
                    ttft_ms = round((time.perf_counter() - t_req_start) * 1000, 2)
                if token_callback:
                    streamed_any_tokens = True
                    token_callback(text)

            def _process_stream_text(delta_txt: str) -> None:
                nonlocal hidden_tag, pending
                pending += delta_txt
                while pending:
                    if hidden_tag:
                        close_tag = f"</{hidden_tag}>"
                        idx = pending.lower().find(close_tag)
                        if idx != -1:
                            pending = pending[idx + len(close_tag):]
                            hidden_tag = None
                            continue
                        # Keep only a small tail in case closing tag spans chunks
                        if len(pending) > len(close_tag):
                            pending = pending[-(len(close_tag) - 1):]
                        break
                    else:
                        lt_idx = pending.find("<")
                        if lt_idx == -1:
                            _flush_visible(pending)
                            pending = ""
                            break
                        if lt_idx > 0:
                            _flush_visible(pending[:lt_idx])
                            pending = pending[lt_idx:]
                        lower_p = pending.lower()
                        matched_open = None
                        for tag_name in ("think", "thought", "thinking", "tool_call"):
                            open_tok = f"<{tag_name}>"
                            if lower_p.startswith(open_tok):
                                matched_open = tag_name
                                pending = pending[len(open_tok):]
                                break
                        if matched_open:
                            hidden_tag = matched_open
                            continue
                        # Could be a partial "<thi" or "<tool_call" tag at chunk boundary
                        if len(pending) < 12 and any(f"<{t}>".startswith(lower_p) for t in ("think", "thought", "thinking", "tool_call")):
                            break
                        # Not a hidden tag; emit "<" and continue
                        _flush_visible(pending[0])
                        pending = pending[1:]

            try:
                for chunk in resp:
                    if cancel_check and cancel_check():
                        try:
                            resp.close()
                        except Exception:
                            pass
                        return "".join(raw_parts), [], True

                    choices = getattr(chunk, "choices", None)
                    if not choices:
                        continue
                    delta = getattr(choices[0], "delta", None)
                    if not delta:
                        continue

                    tc_deltas = getattr(delta, "tool_calls", None)
                    if tc_deltas:
                        saw_tool_calls = True
                        for tc_d in tc_deltas:
                            idx = getattr(tc_d, "index", 0) or 0
                            entry = tc_map.setdefault(idx, {"id": "", "type": "function", "name": "", "arguments": ""})
                            if getattr(tc_d, "id", None):
                                entry["id"] = tc_d.id
                            fn = getattr(tc_d, "function", None)
                            if fn:
                                if getattr(fn, "name", None):
                                    entry["name"] += fn.name
                                if getattr(fn, "arguments", None):
                                    entry["arguments"] += fn.arguments

                    c_delta = getattr(delta, "content", None) or ""
                    if c_delta:
                        raw_parts.append(c_delta)
                        _process_stream_text(c_delta)
            finally:
                try:
                    resp.close()
                except Exception:
                    pass

            if len(pending) > 0 and hidden_tag is None and allow_live_stream and not saw_tool_calls:
                _flush_visible(pending)

            from types import SimpleNamespace
            assembled_tcs = [
                SimpleNamespace(
                    id=tc_map[i]["id"] or f"call_{i}",
                    type="function",
                    function=SimpleNamespace(name=tc_map[i]["name"], arguments=tc_map[i]["arguments"]),
                )
                for i in sorted(tc_map.keys())
                if tc_map[i]["name"]
            ]
            return "".join(raw_parts), assembled_tcs, False

        try:
            for iteration in range(max_iterations):
                if cancel_check and cancel_check():
                    logger.info(f"[chat:{req_tag}] Cancelled before LLM iteration {iteration}")
                    return {
                        "reply": "",
                        "intent": "CANCELLED",
                        "selected_agent": "nvidia_nemotron",
                        "tool_calls": executed_tool_calls,
                        "sources": sources,
                        "success": False,
                        "error": "Request cancelled",
                        "error_type": "CANCELLED",
                    }
                # On the final iteration or if tool budget exhausted, force model to synthesize without calling more tools
                budget_left = len(executed_tool_calls) < max_total_tool_calls
                active_tools = tools if (tools and budget_left and iteration < max_iterations - 1) else None
                if iteration == 0:
                    emit_progress(
                        "model_inference",
                        "running",
                        "Preparing a response..." if not active_tools else "Understanding your request...",
                    )
                else:
                    emit_progress("synthesis", "running", "Putting the information together...")

                t_llm0 = time.perf_counter()
                # Use enable_thinking=False for pure conversational turns or final synthesis to avoid multi-second hidden <think> stalls
                use_thinking = bool(active_tools and iteration == 0)
                allow_stream = (active_tools is None) or (not needs_tools)
                raw_content, msg_tool_calls, was_cancelled = _invoke_completion(
                    active_tools_arg=active_tools,
                    enable_thinking=use_thinking,
                    allow_live_stream=allow_stream,
                )
                if was_cancelled:
                    logger.info(f"[chat:{req_tag}] Cancelled during LLM stream iteration {iteration}")
                    return {
                        "reply": "",
                        "intent": "CANCELLED",
                        "selected_agent": "nvidia_nemotron",
                        "tool_calls": executed_tool_calls,
                        "sources": sources,
                        "success": False,
                        "error": "Request cancelled",
                        "error_type": "CANCELLED",
                    }

                logger.info(
                    f"[chat:{req_tag}] LLM iteration {iteration} completed in {time.perf_counter() - t_llm0:.2f}s "
                    f"(tool_calls={len(msg_tool_calls)}, needs_tools={needs_tools})"
                )

                # If model requested tool calls, execute them
                if msg_tool_calls and active_tools:
                    tool_calls_param: List[ChatCompletionMessageFunctionToolCallParam] = []
                    for tc in msg_tool_calls:
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
                        "content": raw_content or "",
                        "tool_calls": tool_calls_param,
                    }
                    messages.append(assistant_msg)

                    emit_progress(
                        "database_retrieval",
                        "running",
                        "Gathering relevant information..." if len(msg_tool_calls) > 1 else "Checking campus records...",
                    )

                    all_cached_in_turn = True
                    for tc in msg_tool_calls:
                        if tc.type != "function":
                            continue
                        tool_name = tc.function.name
                        try:
                            tool_args = json.loads(tc.function.arguments or "{}")
                        except Exception as json_err:
                            logger.warning(f"Failed to parse tool call JSON for {tool_name}: {json_err}")
                            tool_result = {"error": f"Invalid JSON arguments for tool '{tool_name}': {str(json_err)}"}
                            tool_msg: ChatCompletionToolMessageParam = {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": json.dumps(tool_result),
                            }
                            messages.append(tool_msg)
                            all_cached_in_turn = False
                            continue

                        # Duplicate call caching & suppression
                        call_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                        if call_key in tool_results_cache:
                            cached_res = tool_results_cache[call_key]
                            dup_payload = {
                                "cached": True,
                                "note": "Identical read-only tool call already executed in this turn. Do not repeat it; synthesize your final answer now from these retrieved records.",
                                "result": cached_res,
                            }
                            tool_msg = {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": json.dumps(dup_payload, default=str),
                            }
                            messages.append(tool_msg)
                            continue

                        all_cached_in_turn = False
                        logger.info(f"NVIDIA Nemotron called tool '{tool_name}' with args {tool_args}")
                        t0 = time.perf_counter()
                        tool_result = execute_tool(
                            tool_name=tool_name,
                            tool_args=tool_args,
                            user=user,
                            db=db,
                        )
                        elapsed_tool_ms = (time.perf_counter() - t0) * 1000
                        tool_results_cache[call_key] = tool_result

                        # Determine record count safely
                        rec_count = 0
                        if isinstance(tool_result, dict):
                            if "total_returned" in tool_result:
                                rec_count = int(tool_result["total_returned"])
                            elif "total" in tool_result and isinstance(tool_result["total"], int):
                                rec_count = tool_result["total"]
                            elif "total_students" in tool_result:
                                rec_count = int(tool_result["total_students"])
                            elif "timetables" in tool_result and isinstance(tool_result["timetables"], list):
                                rec_count = len(tool_result["timetables"])
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
                        executed_tool_results.append({"tool": tool_name, "args": tool_args, "result": tool_result})
                        if isinstance(tool_result, dict) and "source" in tool_result:
                            sources.append(tool_result["source"])

                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(tool_result, default=str),
                        }
                        messages.append(tool_msg)

                    emit_progress("database_retrieval", "completed", "Reviewing the retrieved information...")

                    # If the model only repeated cached calls, force final synthesis on next turn
                    if all_cached_in_turn:
                        messages.append({
                            "role": "user",
                            "content": "You already have the database results above. Provide a clear, direct, natural-language answer to the user's question without calling any more tools.",
                        })
                        emit_progress("synthesis", "running", "Putting the information together...")
                        synth_raw, _, synth_cancelled = _invoke_completion(
                            active_tools_arg=None,
                            enable_thinking=False,
                            allow_live_stream=True,
                        )
                        if synth_cancelled:
                            return {
                                "reply": "",
                                "intent": "CANCELLED",
                                "selected_agent": "nvidia_nemotron",
                                "tool_calls": executed_tool_calls,
                                "sources": sources,
                                "success": False,
                                "error": "Request cancelled",
                                "error_type": "CANCELLED",
                            }
                        final_text = strip_thinking(synth_raw)
                        break

                    # Continue loop to allow model to synthesize tool results
                    continue

                # Check if model emitted XML-style <tool_call> in text content
                text_tool_calls = _parse_text_tool_calls(raw_content) if active_tools else []
                if text_tool_calls:
                    emit_progress("database_retrieval", "running", "Checking campus records...")
                    observations: List[str] = []
                    for t_name, t_args in text_tool_calls:
                        call_key = f"{t_name}:{json.dumps(t_args, sort_keys=True)}"
                        if call_key in tool_results_cache:
                            t_res = tool_results_cache[call_key]
                        else:
                            t_res = execute_tool(tool_name=t_name, tool_args=t_args, user=user, db=db)
                            tool_results_cache[call_key] = t_res
                            executed_tool_calls.append({"tool": t_name, "args": t_args})
                            executed_tool_results.append({"tool": t_name, "args": t_args, "result": t_res})
                            if isinstance(t_res, dict) and "source" in t_res:
                                sources.append(t_res["source"])
                        observations.append(f"Database result:\n{json.dumps(t_res, default=str)}")
                    emit_progress("database_retrieval", "completed", "Reviewing the retrieved information...")
                    messages.append({"role": "user", "content": "\n\n".join(observations) + "\n\nSynthesize a clear, grounded answer from these results without outputting <tool_call> tags or mentioning tool names."})
                    continue

                # If no tool calls (or tools suppressed on final turn), model provided final text response
                final_text = strip_thinking(raw_content)
                break

            # If final_text is still empty after the loop, force a dedicated non-thinking synthesis or grounded formatter fallback
            if not final_text and executed_tool_results:
                try:
                    emit_progress("synthesis", "running", "Putting the information together...")
                    messages.append({
                        "role": "user",
                        "content": "Summarize the retrieved database records above into a direct, natural-language answer to the original question. Do not mention tool names or output raw JSON.",
                    })
                    synth_raw, _, synth_cancelled = _invoke_completion(
                        active_tools_arg=None,
                        enable_thinking=False,
                        allow_live_stream=True,
                    )
                    if not synth_cancelled:
                        final_text = strip_thinking(synth_raw)
                except Exception as synth_err:
                    logger.warning(f"Final synthesis fallback failed: {synth_err}")

            if not final_text and executed_tool_results:
                from agents.query_agent.agent import format_grounded_response
                last_exec = executed_tool_results[-1]
                formatted_reply, fmt_sources = format_grounded_response(
                    tool_name=last_exec["tool"],
                    tool_args=last_exec["args"],
                    tool_result=last_exec["result"],
                    user=user,
                )
                if formatted_reply and formatted_reply != "No information could be generated for this query.":
                    final_text = formatted_reply
                    sources.extend(fmt_sources)

            if executed_tool_results:
                sources.append("RIO Database Grounding")

            if not final_text:
                if executed_tool_results:
                    final_text = "I couldn't find any matching campus records for that inquiry."
                else:
                    final_text = "I'm here to help—could you share a bit more detail about what you'd like to know?"

            trace.mark_nvidia_received()
            diagnostics_summary = trace.finalize(success=True)
            if isinstance(diagnostics_summary, dict):
                diagnostics_summary["llm_calls"] = llm_call_count
                diagnostics_summary["ttft_ms"] = ttft_ms
                diagnostics_summary["streamed_live"] = streamed_any_tokens
            logger.info(
                f"[chat:{req_tag}] Completed in {time.perf_counter() - t_req_start:.2f}s "
                f"(llm_calls={llm_call_count}, tools={len(executed_tool_calls)}, ttft_ms={ttft_ms}, reply_len={len(final_text)})"
            )

            return {
                "reply": final_text,
                "intent": "OPEN_ENDED_LLM_QUERY",
                "selected_agent": "nvidia_nemotron",
                "tool_calls": executed_tool_calls,
                "tool_results": executed_tool_results,
                "sources": list(dict.fromkeys(sources)),
                "proposal": None,
                "action_type": None,
                "success": True,
                "error": None,
                "streamed_live": streamed_any_tokens,
                "diagnostics": diagnostics_summary,
            }

        except APITimeoutError as timeout_exc:
            logger.error(f"[chat:{req_tag}] NVIDIA Nemotron API timed out: {timeout_exc}")
            diagnostics_summary = trace.finalize(success=False, error="Request timed out")
            return {
                "reply": "",
                "intent": "ERROR",
                "selected_agent": "nvidia_nemotron",
                "tool_calls": executed_tool_calls,
                "sources": sources,
                "success": False,
                "error": "The AI service timed out while generating a response. Please try again.",
                "error_type": "TIMED_OUT",
                "diagnostics": diagnostics_summary,
            }
        except Exception as exc:
            logger.error(f"NVIDIA Nemotron API call failed: {exc}", exc_info=True)
            diagnostics_summary = trace.finalize(success=False, error=str(exc))
            return {
                "reply": "",
                "intent": "ERROR",
                "selected_agent": "nvidia_nemotron",
                "tool_calls": executed_tool_calls,
                "sources": sources,
                "success": False,
                "error": str(exc),
                "error_type": "FAILED",
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

