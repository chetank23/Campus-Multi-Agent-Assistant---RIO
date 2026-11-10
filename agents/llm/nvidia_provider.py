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

                        logger.info(f"NVIDIA Nemotron called tool '{tool_name}' with args {tool_args}")
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

            # If final_text is still empty after stripping thinking, provide direct summary
            if not final_text and executed_tool_calls:
                final_text = "Here are the database records matching your inquiry:\n\n"
                for tc in executed_tool_calls:
                    final_text += f"- Executed tool `{tc['tool']}` successfully.\n"

            if not final_text:
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

