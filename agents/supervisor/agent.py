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
from typing import Any, Dict, List, Literal, Optional, Tuple
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from backend.models.identity import User
from agents.state.state import AgentState
from agents.query_agent.agent import run_query_agent
from agents.scheduling_agent.agent import run_scheduling_agent
from agents.resource_agent.agent import run_resource_agent


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
        "course", "subject", "credits", "syllabus", "room", "lab",
        "auditorium", "seminar", "capacity", "where is", "holiday", "exam", "vacation",
        "academic calendar", "events", "department schedule", "calendar"
    ]
    if any(q in msg for q in query_patterns):
        return "QUERY_AGENT"

    # Greetings and general campus inquiries
    if re.search(r"\b(hi|hello|hey|help|good morning|good afternoon|who are you|what can you do)\b", msg):
        return "CAMPUS_GREETING"

    return "UNKNOWN"


def supervisor_node(state: AgentState) -> AgentState:
    """
    Supervisor entry node: evaluates intent, validates scope, and sets target route.
    """
    message = state.get("message", "")
    intent = classify_intent(message)

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
                "👋 Hello! I am the **RIO Campus Assistant**.\n\n"
                "I can help you with verified campus operations, including:\n"
                "- 📅 **Your Published Schedule**: *'What classes do I have on Monday?'*\n"
                "- ⏱️ **Class Status**: *'What is my next class?'*\n"
                "- 🏛️ **Resource Booking**: *'Book Seminar Hall A tomorrow 2pm to 4pm'* or *'Find seminar halls'*\n"
                "- 🤖 **Timetable Generation**: *'Generate a timetable for CSE Semester 1'* (Admin only)\n"
                "- 📍 **Campus Facilities**: *'Where is Room 101?'*\n"
                "- 📚 **Course Catalog**: *'What are the credits for CS101?'*\n"
                "- 👨‍🏫 **Faculty Directory**: *'Who is teaching Dr. Allison Hill?'*\n"
                "- 📆 **University Calendar**: *'When are the upcoming holidays?'*\n\n"
                "How can I assist you today?"
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
                "🤔 I could not find a matching campus service for your request.\n\n"
                "You can ask me about your published timetable, real-time class status, faculty profiles, "
                "classroom locations, course credits, resource bookings and facility availability, university calendar events, or timetable generation (Admin only)."
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
    workflow = StateGraph(AgentState)

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

        return {
            "reply": final_state.get("final_response") or "No response could be generated.",
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
                "⚠️ The Campus Assistant encountered a temporary internal error while processing your request. "
                "Please try again or contact system support."
            ),
            "intent": "ERROR",
            "selected_agent": None,
            "tool_calls": [],
            "sources": [],
            "success": False,
            "error": str(exc),
        }
