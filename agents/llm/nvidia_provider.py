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
        Constructs the system prompt for NVIDIA Nemotron.
        Balances natural general-knowledge conversation with dynamic, tool-grounded
        campus database intelligence and strict role-based security.
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"""You are RIO, an intelligent, natural, context-aware AI assistant for this university campus.

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

    def generate_chat_response(
        self,
        message: str,
        user: User,
        db: Session,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes real-time natural language reasoning using NVIDIA Nemotron.
        Runs a bounded multi-turn tool calling loop directly against PostgreSQL database services.
        Strips thinking tokens and produces a direct, grounded answer.
        """
        req_tag = request_id or "req"
        t_req_start = time.perf_counter()
        client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=0,
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
                    }
                # On the final iteration or if tool budget exhausted, force model to synthesize without calling more tools
                budget_left = len(executed_tool_calls) < max_total_tool_calls
                active_tools = tools if (tools and budget_left and iteration < max_iterations - 1) else None
                t_llm0 = time.perf_counter()
                if active_tools:
                    response = client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        tools=active_tools,
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
                logger.info(f"[chat:{req_tag}] LLM iteration {iteration} completed in {time.perf_counter() - t_llm0:.2f}s (tool_calls={len(msg.tool_calls or [])})")

                # If model requested tool calls, execute them
                if msg.tool_calls and active_tools:
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

                    all_cached_in_turn = True
                    for tc in msg.tool_calls:
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

                    # If the model only repeated cached calls, force final synthesis on next turn
                    if all_cached_in_turn:
                        messages.append({
                            "role": "user",
                            "content": "You already have the database results above. Provide a clear, direct, natural-language answer to the user's question without calling any more tools.",
                        })
                        synth_resp = client.chat.completions.create(
                            model=self.model,
                            messages=messages,
                            temperature=self.temperature,
                            top_p=self.top_p,
                            max_tokens=self.max_tokens,
                            extra_body={"chat_template_kwargs": {"enable_thinking": False, "force_nonempty_content": True}},
                        )
                        final_text = strip_thinking(synth_resp.choices[0].message.content or "")
                        break

                    # Continue loop to allow model to synthesize tool results
                    continue

                # Check if model emitted XML-style <tool_call> in text content
                raw_content = msg.content or ""
                text_tool_calls = _parse_text_tool_calls(raw_content) if active_tools else []
                if text_tool_calls:
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
                    messages.append({"role": "user", "content": "\n\n".join(observations) + "\n\nSynthesize a clear, grounded answer from these results without outputting <tool_call> tags or mentioning tool names."})
                    continue

                # If no tool calls (or tools suppressed on final turn), model provided final text response
                final_text = strip_thinking(raw_content)
                break

            # If final_text is still empty after the loop, force a dedicated non-thinking synthesis or grounded formatter fallback
            if not final_text and executed_tool_results:
                try:
                    messages.append({
                        "role": "user",
                        "content": "Summarize the retrieved database records above into a direct, natural-language answer to the original question. Do not mention tool names or output raw JSON.",
                    })
                    synth_resp = client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=self.temperature,
                        top_p=self.top_p,
                        max_tokens=self.max_tokens,
                        extra_body={"chat_template_kwargs": {"enable_thinking": False, "force_nonempty_content": True}},
                    )
                    final_text = strip_thinking(synth_resp.choices[0].message.content or "")
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
            logger.info(
                f"[chat:{req_tag}] Completed in {time.perf_counter() - t_req_start:.2f}s "
                f"(tools={len(executed_tool_calls)}, reply_len={len(final_text)})"
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

