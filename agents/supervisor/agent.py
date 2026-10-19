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
from agents.common.formatter import sanitize_plain_english


def classify_intent(message: str) -> str:
    """
    Classifies the user intent into supported and out-of-scope categories.
    """
    msg = message.lower().strip()

    # 1. Resource Confirmation token: confirm res_prop_<hex>
    if re.search(r"\b(?:confirm|execute|approve|proceed)\s+res_prop_[a-zA-Z0-9_-]+\b", msg):
        return "RESOURCE_BOOKING"

    # 2. Scheduling / Timetable Generation requests & confirmation
    scheduling_patterns = [
        r"\bgenerate\b.*\btimetable\b",
        r"\bcreate\b.*\btimetable\b",
        r"\brun\b.*\bsolver\b",
        r"\boptimize\b.*\bschedule\b",
        r"\bnew\b.*\btimetable\b",
        r"\bpublish\b.*\btimetable\b",
        r"\bauto-generate\b",
        r"\bconfirm\s+prop_[a-zA-Z0-9_-]+\b",
        r"\bexecute\s+prop_[a-zA-Z0-9_-]+\b",
        r"\bproceed\s+prop_[a-zA-Z0-9_-]+\b",
        r"\bwhy\b.*\b(infeasible|fail|couldn't|cannot)\b.*\b(timetable|generate|schedule)\b",
        r"\bcompare\b.*\b(strategies|scheduling|scenarios)\b",
        r"\bscheduling\s+strateg(y|ies)\b",
        r"\bfaculty-comfort\b",
        r"\broom-efficiency\b",
        r"\blab-preference\b",
    ]
    for pat in scheduling_patterns:
        if re.search(pat, msg):
            return "TIMETABLE_GENERATION"

    # 3. Resource Agent requests (Discovery, Availability, Booking, Status, Cancellation)
    resource_patterns = [
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

    # 4. Informational Queries supported by Query Agent
    query_patterns = [
        "timetable", "schedule", "class", "classes", "lecture", "timing", "when is",
        "ongoing", "upcoming", "next class", "faculty", "professor", "teacher",
        "teach", "teaching", "who is", "who teaches", "dr.", "dr ", "prof",
        "course", "subject", "credits", "syllabus", "room", "rooms", "classroom", "classrooms", "lab", "labs",
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

    # Follow-up intent checks
    if re.search(r"^(?:yes|confirm|proceed|confirm it|approve it|do it)$", msg):
        return "FOLLOW_UP_CONFIRM"

    if re.search(r"^(?:no|cancel|discard|never mind|stop)$", msg):
        return "FOLLOW_UP_CANCEL"

    if re.search(r"\b(?:change the time|change time|another time|different time|show me another option|another option|other options)\b", msg):
        return "FOLLOW_UP_MODIFY"

    # Greetings and general campus inquiries
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
    intent = classify_intent(message)

    # Handle follow-up confirmation: "yes", "confirm", "proceed", "confirm it"
    if intent == "FOLLOW_UP_CONFIRM":
        if user_id:
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

    # Handle follow-up modification: "change the time", "show me another option"
    if intent == "FOLLOW_UP_MODIFY":
        return {
            "intent": "CLARIFICATION_REQUIRED",
            "selected_agent": None,
            "final_response": "Please specify the preferred date and time interval you would like to check.",
        }

    if intent == "TIMETABLE_GENERATION":
        return {
            "intent": intent,
            "selected_agent": "scheduling_agent",
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


def route_supervisor(state: AgentState) -> Literal["query_agent_node", "scheduling_agent_node", "resource_agent_node", "end_node"]:
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
            "end_node": "end_node",
        },
    )

    workflow.add_edge("query_agent_node", "end_node")
    workflow.add_edge("scheduling_agent_node", "end_node")
    workflow.add_edge("resource_agent_node", "end_node")
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
