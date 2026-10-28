"""
agents/supervisor/agent.py
--------------------------
Supervisor Agent for RIO-MJP using LangGraph.
Orchestrates request-scoped intent classification, role authorization pre-checks,
and dispatch to the Query Agent or controlled polite termination for out-of-scope actions.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Literal, Optional, Tuple, cast
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from backend.models.identity import User
from agents.state.state import AgentState
from agents.query_agent.agent import run_query_agent
from agents.scheduling_agent.agent import run_scheduling_agent
from agents.resource_agent.agent import run_resource_agent
from agents.scheduling_agent.proposal_store import proposal_store
from agents.resource_agent.proposal_store import resource_proposal_store
from agents.common.operation_proposal_store import operation_proposal_store
from agents.action_registry import action_registry
from agents.common.formatter import sanitize_plain_english
from agents.resource_agent.parser import (
    parse_date,
    parse_time_interval,
    extract_resource_details,
)
from agents.tools.faculty_tools import get_available_faculty_data



def classify_intent(message: str) -> str:
    """
    Classifies the user intent into supported and out-of-scope categories.
    """
    msg = message.lower().strip()

    # 1. Operation & Resource Confirmation tokens
    m_op = re.search(r"\b(?:confirm|execute|approve|proceed)\s+(op_prop_[a-zA-Z0-9_-]+)\b", msg)
    if m_op:
        token = m_op.group(1)
        prop = operation_proposal_store.get_proposal(token)
        if prop and "TIMETABLE" in prop.action_name:
            return "TIMETABLE_GENERATION"
        return "RESOURCE_BOOKING"

    if re.search(r"\b(?:confirm|execute|approve|proceed)\s+res_prop_[a-zA-Z0-9_-]+\b", msg):
        return "RESOURCE_BOOKING"

    if re.search(r"\b(?:confirm|execute|approve|proceed)\s+disrupt_prop_[a-zA-Z0-9_-]+\b", msg):
        return "TIMETABLE_GENERATION"

    # 2. Scheduling Readiness Check (Read-only assessment, Admin only)
    readiness_patterns = [
        r"\breadiness\b",
        r"\bready\s+to\s+(?:schedule|generate)\b",
        r"\bready\s+for\s+(?:scheduling|generation)\b",
        r"\bcheck\s+(?:timetable\s+)?readiness\b",
        r"\bscheduling\s+readiness\b",
        r"\btimetable\s+readiness\b",
    ]
    for pat in readiness_patterns:
        if re.search(pat, msg):
            return "TIMETABLE_READINESS"

    # 3. Scheduling / Timetable Generation, Revision, Conflicts, & Faculty Availability requests
    scheduling_patterns = [
        r"\bgenerate\b.*\btimetable\b",
        r"\bcreate\b.*\btimetable\b",
        r"\brun\b.*\bsolver\b",
        r"\boptimize\b.*\bschedule\b",
        r"\bnew\b.*\btimetable\b",
        r"\bfinalize\b.*\btimetable\b",
        r"\bpublish\b.*\btimetable\b",
        r"\bauto-generate\b",
        r"\bconfirm\s+prop_[a-zA-Z0-9_-]+\b",
        r"\bexecute\s+prop_[a-zA-Z0-9_-]+\b",
        r"\bproceed\s+prop_[a-zA-Z0-9_-]+\b",
        r"\bwhy\b.*\b(infeasible|fail|couldn't|could\s+not|cannot|can't|unable|no\s+solution|not\s+create|not\s+generate)\b.*\b(timetable|generate|schedule|solver)\b",
        r"\bcompare\b.*\b(strategies|scheduling|scenarios)\b",
        r"\bscheduling\s+strateg(y|ies)\b",
        r"\bfaculty-comfort\b",
        r"\broom-efficiency\b",
        r"\blab-preference\b",
        r"\b(?:show|view|check|list|inspect|are\s+there\s+any)\b.*?\bconflicts?\b",
        r"\bconflicts?\b.*?\b(before|approve|timetable|schedule)\b",
        r"\bavoid\b.*?\b(labs?|morning|consecutive)\b",
        r"\brevise\b.*?\b(timetable|proposal|schedule|periods|strategy)\b",
        r"\breduce\b.*?\bconsecutive\b",
        r"\b(?:faculty|prof|dr\.?)\b.*?\b(unavailable|available|preferred)\b",
        r"\bunavailable\b.*?\b(monday|tuesday|wednesday|thursday|friday|saturday|afternoon|morning)\b",
        r"\bdisrupt(ion|ions)?\b",
        r"\breschedule\b",
        r"\b(room|lab)\b.*?\bmaintenance\b",
        r"\bmaintenance\b.*?\b(room|lab)\b",
        r"\b(block|close)\b.*?\b(room|lab)\b.*?\bfor\s+maintenance\b",
        r"\b(faculty|prof|dr\.?)\b.*?\b(leave|sick|absence)\b",
    ]
    for pat in scheduling_patterns:
        if re.search(pat, msg):
            return "TIMETABLE_GENERATION"

    # 4. Room metadata updates
    room_update_patterns = [
        r"\b(?:update|change|set|modify)\s+(?:the\s+)?room\b",
        r"\b(?:update|change|set|modify)\s+(?:room\s+)?[a-zA-Z0-9_-]+\s+(?:capacity|type|name)\b",
    ]
    for pat in room_update_patterns:
        if re.search(pat, msg):
            return "RESOURCE_BOOKING"

    # 4.5 Composite Multi-Agent Requests (Resource Booking + Faculty Supervision)
    composite_patterns = [
        r"\b(?:book|reserve)\b.*?\b(?:faculty|prof|professors|teachers?|supervis(?:e|or|ion))\b.*?\b(?:free|available)\b",
        r"\b(?:book|reserve)\b.*?\b(?:who|which)\b.*?\b(?:faculty|prof|teachers?)\b.*?\b(?:free|available|supervise)\b",
        r"\b(?:book|reserve)\b.*?\b(?:tell\s+me|find|show|which|who)\b.*?\b(?:faculty|prof|professors?)\b.*?\b(?:free|available|supervise)\b",
        r"\b(?:faculty|prof|professors?)\b.*?\b(?:free|available|supervise)\b.*?\b(?:book|reserve)\b",
    ]
    for pat in composite_patterns:
        if re.search(pat, msg):
            return "COMPOSITE_BOOKING_SUPERVISION"

    # 5. Resource Agent requests (Discovery, Availability, Booking, Status, Cancellation, Pending queries)
    resource_patterns = [
        r"\bpending\s+(?:resource\s+)?(?:bookings?|requests?)\b",
        r"\b(?:view|show|list|get|check)\s+(?:all\s+)?pending\s+(?:resource\s+)?(?:bookings?|requests?)\b",
        r"\bstatus\s+of\s+pending\s+bookings?\b",
        r"\bbook\b\s+.*",
        r"\breserve\b\s+.*",
        r"\bbook\b.*\b(hall|room|lab|projector|auditorium|facility|resource)\b",
        r"\breserve\b.*\b(hall|room|lab|projector|auditorium|facility|resource)\b",
        r"\bbooking\s+(request|requests|status|details)\b",
        r"\bmy\s+bookings?\b",
        r"\bshow\s+my\s+bookings?\b",
        r"\bcancel\b.*\bbooking\b",
        r"\bapprove\b.*\bbooking\b",
        r"\breject\b.*\bbooking\b",
        r"\b(check|find|search|show|list)\s+.*?\b(available|free|seminar\s+halls?|labs?|auditoriums?|projectors?|facilities|resources)\b",
        r"\bis\b.*\b(available|free)\b",
        r"\bavailability\b",
    ]
    for pat in resource_patterns:
        if re.search(pat, msg):
            return "RESOURCE_BOOKING"

    # 6. Unsupported domain operations (e.g., grades, fees, account deletion)
    unsupported_patterns = [
        (r"\b(?:change|update|edit|modify|submit|enter|post)\b.*?\b(?:grade|grades|marks|gpa|cgpa)\b", "grade management"),
        (r"\b(?:pay|payment|refund|waive|process)\b.*?\b(?:fee|fees|tuition|dues)\b", "fee payment and refund processing"),
        (r"\b(?:delete|drop|remove)\b.*?\b(?:department|departments)\b", "department deletion"),
        (r"\b(?:delete|drop|remove)\b.*?\b(?:courses?|catalog)\b", "course deletion"),
        (r"\b(?:reset|change)\b.*?\bpassword\b", "password management"),
        (r"\b(?:create|delete)\b.*?\buser\s+account\b", "user account creation or deletion"),
    ]
    for pat, desc in unsupported_patterns:
        if re.search(pat, msg):
            return f"UNSUPPORTED:{desc}"

    # 7. Action registry introspection
    if re.search(r"\b(?:what\s+actions|list\s+actions|supported\s+actions|what\s+operations|supported\s+operations)\b", msg):
        return "ACTION_REGISTRY_HELP"

    # 8. Follow-up intent checks
    if re.search(r"^(?:yes|confirm|proceed|confirm it|approve it|do it|yes proceed|yes, proceed)$", msg):
        return "FOLLOW_UP_CONFIRM"

    if re.search(r"^(?:no|cancel|cancel that|no, cancel that|discard|never mind|stop|abort)$", msg):
        return "FOLLOW_UP_CANCEL"

    follow_up_modify_patterns = [
        r"\b(?:change\s+it\s+to|change\s+to|change\s+(?:the\s+)?date\s+to|switch\s+to|move\s+it\s+to|move\s+to)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{4}-\d{2}-\d{2})\b",
        r"\b(?:use\s+.*?instead)\b",
        r"\b(?:show\s+me\s+another\s+option|another\s+option|other\s+options|different\s+option)\b",
        r"\b(?:change\s+the\s+time|change\s+time|another\s+time|different\s+time)\b",
        r"\b(?:change\s+room|change\s+facility|different\s+room)\b",
    ]
    for pat in follow_up_modify_patterns:
        if re.search(pat, msg):
            return "FOLLOW_UP_MODIFY"

    # 9. Informational Queries supported by Query Agent
    query_patterns = [
        "timetable", "schedule", "class", "classes", "lecture", "timing", "when is",
        "ongoing", "upcoming", "next class", "faculty", "professor", "professors", "teacher", "teachers",
        "teach", "teaching", "who is", "who teaches", "dr.", "dr ", "prof",
        "course", "courses", "subject", "subjects", "credits", "syllabus", "room", "rooms", "classroom", "classrooms", "lab", "labs",
        "auditorium", "seminar", "capacity", "where is", "holiday", "exam", "vacation",
        "academic calendar", "events", "department schedule", "calendar"
    ]
    for q in query_patterns:
        if " " in q or "." in q:
            if q in msg:
                return "QUERY_AGENT"
        else:
            if re.search(r"\b" + re.escape(q) + r"\b", msg):
                return "QUERY_AGENT"

    # 10. Greetings and general campus inquiries
    if re.search(r"\b(hi|hello|hey|help|good morning|good afternoon|who are you|what can you do)\b", msg):
        return "CAMPUS_GREETING"

    return "UNKNOWN"


def supervisor_node(state: AgentState) -> AgentState:
    """
    Supervisor entry node: evaluates intent, validates scope, and sets target route.
    Interprets follow-up messages against active proposal context.
    """
    message = state.get("message", "")
    user_id = state.get("user_id")
    role = state.get("role") or "STUDENT"
    intent = classify_intent(message)

    # Handle unsupported operations directly with honest plain English refusal
    if intent.startswith("UNSUPPORTED:"):
        desc = intent.split(":", 1)[1]
        return {
            "intent": "UNSUPPORTED_OPERATION",
            "selected_agent": None,
            "final_response": (
                f"I cannot perform {desc} as there is no backend service supporting this operation "
                "in RIO Campus Assistant. Please contact the academic administration or registrar office directly."
            ),
        }

    # Handle action registry help
    if intent == "ACTION_REGISTRY_HELP":
        actions = action_registry.get_actions_for_role(role)
        read_ops = [a.name for a in actions if not a.requires_confirmation]
        write_ops = [a.name for a in actions if a.requires_confirmation]
        resp_lines = [
            f"Here are the supported operations available for your role ({role}):",
            "",
            "Query and Read Operations:",
            *(f"- {name}" for name in read_ops),
            "",
            "Action and Update Operations (require confirmation):",
            *(f"- {name}" for name in write_ops),
        ]
        return {
            "intent": "ACTION_REGISTRY_HELP",
            "selected_agent": None,
            "final_response": "\n".join(resp_lines),
        }

    # Handle follow-up confirmation: "yes", "confirm", "proceed", "confirm it"
    if intent == "FOLLOW_UP_CONFIRM":
        if user_id:
            op_prop = operation_proposal_store.get_latest_pending_proposal(user_id)
            if op_prop:
                state["message"] = f"confirm {op_prop.proposal_id}"
                if "TIMETABLE" in op_prop.action_name:
                    return {
                        "intent": "TIMETABLE_GENERATION",
                        "selected_agent": "scheduling_agent",
                        "message": f"confirm {op_prop.proposal_id}",
                    }
                else:
                    return {
                        "intent": "RESOURCE_BOOKING",
                        "selected_agent": "resource_agent",
                        "message": f"confirm {op_prop.proposal_id}",
                    }

            res_prop = resource_proposal_store.get_latest_pending_proposal(user_id)
            if res_prop:
                state["message"] = f"confirm {res_prop.proposal_id}"
                return {
                    "intent": "RESOURCE_BOOKING",
                    "selected_agent": "resource_agent",
                    "message": f"confirm {res_prop.proposal_id}",
                }
            sched_prop = proposal_store.get_latest_pending_proposal(user_id)
            if sched_prop:
                state["message"] = f"confirm {sched_prop.proposal_id}"
                return {
                    "intent": "TIMETABLE_GENERATION",
                    "selected_agent": "scheduling_agent",
                    "message": f"confirm {sched_prop.proposal_id}",
                }

        return {
            "intent": "CLARIFICATION_REQUIRED",
            "selected_agent": None,
            "final_response": "There is no pending proposal awaiting your confirmation. Please state the action or schedule you wish to request.",
        }

    # Handle follow-up cancellation: "no", "cancel", "never mind"
    if intent == "FOLLOW_UP_CANCEL":
        discarded = False
        if user_id:
            op_prop = operation_proposal_store.get_latest_pending_proposal(user_id)
            if op_prop:
                operation_proposal_store.discard_proposal(op_prop.proposal_id, user_id)
                discarded = True
            res_prop = resource_proposal_store.get_latest_pending_proposal(user_id)
            if res_prop:
                resource_proposal_store.discard_proposal(res_prop.proposal_id, user_id)
                discarded = True
            sched_prop = proposal_store.get_latest_pending_proposal(user_id)
            if sched_prop:
                proposal_store.discard_proposal(sched_prop.proposal_id, user_id)
                discarded = True

        if discarded:
            return {
                "intent": "PROPOSAL_DISCARDED",
                "selected_agent": None,
                "final_response": "The pending proposal has been discarded. Please let me know what else you would like to do.",
            }
        return {
            "intent": "ACKNOWLEDGEMENT",
            "selected_agent": None,
            "final_response": "Understood. Please let me know if you need assistance with timetables, facilities, or campus directory records.",
        }

    # Handle follow-up modification: "change the time", "show me another option", "use room b204 instead", "change it to thursday"
    if intent == "FOLLOW_UP_MODIFY":
        if re.search(r"^\s*(?:change\s+the\s+time|change\s+time|another\s+time|different\s+time)\s*$", message.lower().strip()):
            return {
                "intent": "CLARIFICATION_REQUIRED",
                "selected_agent": None,
                "final_response": "Please specify the preferred date and time interval you would like to check.",
            }
        if user_id:
            res_prop = resource_proposal_store.get_latest_pending_proposal(user_id)
            if res_prop:
                return {
                    "intent": "RESOURCE_BOOKING",
                    "selected_agent": "resource_agent",
                }
        return {
            "intent": "CLARIFICATION_REQUIRED",
            "selected_agent": None,
            "final_response": "There is no pending booking proposal to modify. Please state the facility or booking you wish to request.",
        }

    if intent in ["TIMETABLE_GENERATION", "TIMETABLE_READINESS"]:
        return {
            "intent": intent,
            "selected_agent": "scheduling_agent",
        }

    elif intent == "COMPOSITE_BOOKING_SUPERVISION":
        return {
            "intent": intent,
            "selected_agent": "composite_coordinator",
        }

    elif intent == "RESOURCE_BOOKING":
        return {
            "intent": intent,
            "selected_agent": "resource_agent",
        }

    elif intent == "CAMPUS_GREETING":
        return {
            "intent": intent,
            "selected_agent": None,
            "final_response": (
                "Hello. I am the RIO Campus Assistant.\n\n"
                "I can help you with:\n"
                "- Your published class timetable and real-time class status.\n"
                "- Campus facility availability, resource discovery, and booking requests.\n"
                "- Faculty directory profiles, course catalog details, and room locations.\n"
                "- University academic calendar events and examination schedules.\n"
                "- Academic timetable generation and optimization (Administrators only).\n\n"
                "How may I assist you today?"
            ),
        }

    elif intent == "QUERY_AGENT":
        return {
            "intent": intent,
            "selected_agent": "query_agent",
        }

    else:
        return {
            "intent": "UNKNOWN",
            "selected_agent": None,
            "final_response": (
                "I could not find a matching campus service for your request.\n\n"
                "You can ask about your published timetable, faculty profiles, room locations, course details, "
                "resource bookings, facility availability, calendar events, or timetable generation (Admin only)."
            ),
        }


def run_composite_booking_supervision(
    state: AgentState,
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Coordinates multi-step composite requests involving both Resource Allocation and Query Agent services:
    e.g., "Book Lab 3 for 2 PM tomorrow and tell me which faculty are free to supervise it."
    Executes authoritative facility availability validation and proposal creation, followed by
    database-grounded faculty schedule inspection, synthesizing a unified, transparent response.
    """
    message = state.get("message", "")
    req_date = parse_date(message)
    req_start, req_end = parse_time_interval(message)
    res_details = extract_resource_details(message)

    tool_calls: List[Dict[str, Any]] = list(state.get("tool_calls", []))
    sources: List[str] = list(state.get("sources", []))

    # Clarification if missing critical date/time/resource
    missing_elements: List[str] = []
    if not res_details.get("resource_name") and not res_details.get("resource_type") and not res_details.get("resource_id"):
        missing_elements.append("the facility or lab name (e.g., Lab 3, Seminar Hall A)")
    if req_date is None:
        missing_elements.append("the target date (e.g., tomorrow or 2026-10-28)")
    if req_start is None or req_end is None:
        missing_elements.append("the time interval (e.g., 2:00 PM to 3:00 PM)")

    if missing_elements or req_date is None or req_start is None or req_end is None:
        clarification_msg = (
            "To check facility availability and identify available supervising faculty, please provide:\n"
            + "\n".join(f"- {m}" for m in missing_elements)
        )
        return {
            "intent": "CLARIFICATION_REQUIRED",
            "selected_agent": "composite_coordinator",
            "action_type": "CLARIFICATION_REQUIRED",
            "final_response": sanitize_plain_english(clarification_msg),
            "tool_calls": tool_calls,
            "sources": ["Supervisor Agent"],
            "success": True,
        }

    # 1. Execute Resource Allocation Agent for booking proposal or alternatives
    res_agent_result = run_resource_agent(state=dict(state), db=db, user=user)
    res_reply = res_agent_result.get("final_response") or ""
    res_tool_calls = res_agent_result.get("tool_calls") or []
    res_proposal = res_agent_result.get("proposal")
    res_action = res_agent_result.get("action_type")

    tool_calls.extend(res_tool_calls)
    sources.append("Resource Allocation Engine")

    # 2. Execute Faculty Availability lookup
    tool_calls.append({
        "tool": "get_available_faculty",
        "args": {
            "date": req_date.isoformat(),
            "start_time": req_start.strftime("%H:%M"),
            "end_time": req_end.strftime("%H:%M"),
        },
    })
    sources.extend(["Published Academic Timetable", "Faculty Directory"])

    faculty_data = get_available_faculty_data(
        db=db,
        date=req_date,
        start_time=req_start,
        end_time=req_end,
    )

    # 3. Synthesize unified response
    faculty_lines: List[str] = []
    if faculty_data["total_available"] > 0:
        faculty_lines.append(
            f"Available Faculty for Supervision ({req_date.isoformat()} from {req_start.strftime('%H:%M')} to {req_end.strftime('%H:%M')}):"
        )
        for f in faculty_data["available_faculty"][:6]:
            faculty_lines.append(f"- {f['name']} ({f['designation']}, {f['department']} - {f['specialization']})")
        if faculty_data["total_available"] > 6:
            faculty_lines.append(f"- ... and {faculty_data['total_available'] - 6} other available faculty members")
    else:
        faculty_lines.append(
            f"No faculty members are currently free of scheduled classes or marked available during this interval "
            f"({req_start.strftime('%H:%M')} - {req_end.strftime('%H:%M')})."
        )

    faculty_section = "\n".join(faculty_lines)
    combined_response = f"{res_reply}\n\n---\n\n{faculty_section}"

    return {
        "intent": "COMPOSITE_BOOKING_SUPERVISION",
        "selected_agent": "composite_coordinator",
        "action_type": res_action or "COMPOSITE_RESPONSE",
        "final_response": sanitize_plain_english(combined_response),
        "proposal": res_proposal,
        "tool_calls": tool_calls,
        "sources": list(dict.fromkeys(sources)),
        "success": res_agent_result.get("success", True),
    }


def route_supervisor(state: AgentState) -> Literal["query_agent_node", "scheduling_agent_node", "resource_agent_node", "composite_coordinator_node", "end_node"]:
    """
    Conditional routing function for LangGraph.
    """
    selected = state.get("selected_agent")
    if selected == "query_agent":
        return "query_agent_node"
    elif selected == "scheduling_agent":
        return "scheduling_agent_node"
    elif selected == "resource_agent":
        return "resource_agent_node"
    elif selected == "composite_coordinator":
        return "composite_coordinator_node"
    return "end_node"


def build_supervisor_graph(db: Session, user: User):
    """
    Constructs and compiles the LangGraph StateGraph for the request.
    """
    workflow = StateGraph(cast(Any, AgentState))

    # 1. Add Nodes
    workflow.add_node("supervisor", supervisor_node)

    def query_node_runner(state: AgentState) -> Dict[str, Any]:
        return run_query_agent(state=state, db=db, user=user)

    workflow.add_node("query_agent_node", query_node_runner)

    def scheduling_node_runner(state: AgentState) -> Dict[str, Any]:
        return run_scheduling_agent(state=state, db=db, user=user)

    workflow.add_node("scheduling_agent_node", scheduling_node_runner)

    def resource_node_runner(state: AgentState) -> Dict[str, Any]:
        return run_resource_agent(state=state, db=db, user=user)

    workflow.add_node("resource_agent_node", resource_node_runner)

    def composite_node_runner(state: AgentState) -> Dict[str, Any]:
        return run_composite_booking_supervision(state=state, db=db, user=user)

    workflow.add_node("composite_coordinator_node", composite_node_runner)

    def end_node(state: AgentState) -> Dict[str, Any]:
        return {}

    workflow.add_node("end_node", end_node)

    # 2. Add Edges
    workflow.set_entry_point("supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "query_agent_node": "query_agent_node",
            "scheduling_agent_node": "scheduling_agent_node",
            "resource_agent_node": "resource_agent_node",
            "composite_coordinator_node": "composite_coordinator_node",
            "end_node": "end_node",
        },
    )

    workflow.add_edge("query_agent_node", "end_node")
    workflow.add_edge("scheduling_agent_node", "end_node")
    workflow.add_edge("resource_agent_node", "end_node")
    workflow.add_edge("composite_coordinator_node", "end_node")
    workflow.add_edge("end_node", END)

    return workflow.compile()



def execute_supervisor(
    message: str,
    user: User,
    db: Session,
) -> Dict[str, Any]:
    """
    Main invocation entry point for the Supervisor.
    Initializes request-scoped AgentState and executes the compiled LangGraph workflow.
    """
    initial_state: AgentState = {
        "user_id": user.id,
        "role": user.role,
        "department_id": user.department_id,
        "message": message,
        "intent": None,
        "selected_agent": None,
        "tool_calls": [],
        "tool_results": [],
        "final_response": None,
        "error": None,
    }

    try:
        app = build_supervisor_graph(db=db, user=user)
        final_state = app.invoke(initial_state)

        raw_reply = final_state.get("final_response") or "No response could be generated."
        return {
            "reply": sanitize_plain_english(raw_reply),
            "intent": final_state.get("intent"),
            "selected_agent": final_state.get("selected_agent"),
            "tool_calls": final_state.get("tool_calls", []),
            "sources": final_state.get("sources", []),
            "proposal": final_state.get("proposal"),
            "action_type": final_state.get("action_type"),
            "success": True,
            "error": None,
        }

    except Exception as exc:
        return {
            "reply": (
                "The Campus Assistant encountered a temporary internal error while processing your request. "
                "Please try again or contact system support."
            ),
            "intent": "ERROR",
            "selected_agent": None,
            "tool_calls": [],
            "sources": [],
            "success": False,
            "error": str(exc),
        }
