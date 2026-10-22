"""
agents/scheduling_agent/agent.py
--------------------------------
Advanced Intelligent Scheduling Agent for RIO-MJP.
Orchestrates:
- SCHEDULE_REQUEST & SCOPE_RESOLUTION (natural language understanding of department, program, semester)
- READINESS_ANALYSIS (pre-flight validation before solver invocation)
- OPTIMIZATION_ADVISORY (comparison of strategies: BALANCED, FACULTY_COMFORT, ROOM_EFFICIENCY, LAB_PREFERENCE)
- INFEASIBILITY_DIAGNOSTICS (explanation of real solver bottlenecks)
- PROPOSAL (preparation of single-use, bounded generation proposal with idempotency token)
- CONFIRMATION & EXECUTION (delegation to backend/services/timetable_service.py)
- RESULT_ANALYSIS (grounded summary of score, solver status, solve time, and draft version link)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.models.identity import User
from backend.models.timetable import TimetableVersion
from backend.schemas.timetable_generation import GenerationScope
from backend.services.timetable_service import execute_timetable_generation
from agents.state.state import AgentState
from agents.scheduling_agent.proposal_store import proposal_store
from agents.common.operation_proposal_store import operation_proposal_store
from agents.common.formatter import sanitize_plain_english
from agents.tools.scheduling_tools import (
    resolve_academic_scope_data,
    analyze_scheduling_readiness_data,
    execute_finalize_timetable_data,
    execute_publish_timetable_data,
)


def run_scheduling_agent(
    state: AgentState,
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Main entry point for Scheduling Agent.
    Strictly verifies user.role == 'ADMIN' before allowing mutation operations.
    """
    message = state.get("message", "").strip()
    msg_lower = message.lower()

    tool_calls: List[Dict[str, Any]] = []
    sources: List[str] = ["Academic Master Register", "Campus Facilities Register"]

    is_readiness = (
        state.get("intent") == "TIMETABLE_READINESS"
        or bool(re.search(r"\breadiness\b", msg_lower))
        or bool(re.search(r"\bready\s+(?:to|for)\s+(?:schedule|scheduling|generate|generation)\b", msg_lower))
    )

    # 1. Non-Admin check: Guard rail
    if user.role != "ADMIN":
        return {
            "intent": "TIMETABLE_READINESS" if is_readiness else "TIMETABLE_GENERATION",
            "selected_agent": "scheduling_agent",
            "final_response": sanitize_plain_english(
                "Access Restricted: Only university Administrators are authorized to evaluate "
                "timetable scheduling readiness or initiate academic timetables.\n\n"
                "As a Faculty or Student, you can view your published schedules or submit requests through "
                "your dedicated portal workspace."
            ),
            "tool_calls": [],
            "sources": sources,
            "success": True,
        }

    # 2. Check for explicit Confirmation Action: e.g., "confirm prop_xxx" or "confirm op_prop_xxx"
    op_confirm_match = re.search(r"\b(?:confirm|execute|approve|proceed)\s+(op_prop_[a-zA-Z0-9_-]+)\b", msg_lower)
    if op_confirm_match:
        proposal_id = op_confirm_match.group(1)
        tool_calls.append({"tool": "confirm_operation_proposal", "args": {"proposal_id": proposal_id}})

        success, op, err_msg = operation_proposal_store.consume_proposal(
            proposal_id=proposal_id,
            user_id=user.id,
        )
        if not success or not op:
            return {
                "intent": "TIMETABLE_LIFECYCLE",
                "selected_agent": "scheduling_agent",
                "action_type": "CONFIRMATION_REJECTED",
                "final_response": sanitize_plain_english(f"Confirmation Blocked: {err_msg}"),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        if op.action_name == "FINALIZE_TIMETABLE":
            fin_res = execute_finalize_timetable_data(db=db, version_id=op.entity_id, user=user)
            if not fin_res.get("success"):
                return {
                    "intent": "TIMETABLE_LIFECYCLE",
                    "selected_agent": "scheduling_agent",
                    "action_type": "FINALIZATION_ERROR",
                    "final_response": sanitize_plain_english(f"Finalization Failed: {fin_res.get('error')}"),
                    "tool_calls": tool_calls,
                    "sources": sources,
                    "success": False,
                }
            reply = (
                f"Timetable version #{fin_res['version_id']} (v{fin_res.get('version_number', '1')}) "
                f"has been finalized successfully.\n\n"
                f"- Status: FINALIZED\n"
                f"- Confirmed By: {user.name} ({user.email})\n\n"
                f"All entries are locked against manual edits. To publish campus-wide, ask: "
                f"Publish timetable version {fin_res['version_id']}."
            )
            return {
                "intent": "TIMETABLE_LIFECYCLE",
                "selected_agent": "scheduling_agent",
                "action_type": "TIMETABLE_FINALIZED",
                "final_response": sanitize_plain_english(reply),
                "tool_calls": tool_calls,
                "sources": ["Timetable Version Register", "Audit Log"],
                "success": True,
            }

        elif op.action_name == "PUBLISH_TIMETABLE":
            pub_res = execute_publish_timetable_data(db=db, version_id=op.entity_id, user=user)
            if not pub_res.get("success"):
                return {
                    "intent": "TIMETABLE_LIFECYCLE",
                    "selected_agent": "scheduling_agent",
                    "action_type": "PUBLICATION_ERROR",
                    "final_response": sanitize_plain_english(f"Publication Failed: {pub_res.get('error')}"),
                    "tool_calls": tool_calls,
                    "sources": sources,
                    "success": False,
                }
            reply = (
                f"Timetable version #{pub_res['version_id']} (v{pub_res.get('version_number', '1')}) "
                f"is now published and active campus-wide.\n\n"
                f"- Status: PUBLISHED\n"
                f"- Published At: {pub_res.get('published_at', 'Now')}\n"
                f"- Published By: {user.name} ({user.email})\n\n"
                f"Students and Faculty can now view their official schedules in their respective portals."
            )
            return {
                "intent": "TIMETABLE_LIFECYCLE",
                "selected_agent": "scheduling_agent",
                "action_type": "TIMETABLE_PUBLISHED",
                "final_response": sanitize_plain_english(reply),
                "tool_calls": tool_calls,
                "sources": ["Timetable Version Register", "Audit Log"],
                "success": True,
            }

    confirm_match = re.search(r"\b(?:confirm|execute|approve|proceed)\s+(prop_[a-zA-Z0-9_-]+)\b", msg_lower)
    if confirm_match:
        proposal_id = confirm_match.group(1)
        tool_calls.append({"tool": "confirm_scheduling_proposal", "args": {"proposal_id": proposal_id}})

        success, proposal, err_msg = proposal_store.consume_proposal(
            proposal_id=proposal_id,
            user_id=user.id,
        )
        if not success or not proposal:
            return {
                "intent": "TIMETABLE_GENERATION",
                "selected_agent": "scheduling_agent",
                "action_type": "CONFIRMATION_REJECTED",
                "final_response": sanitize_plain_english(f"Confirmation Blocked: {err_msg}"),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        # Re-validate scope and readiness freshness
        scope_dict = proposal.scope
        readiness = analyze_scheduling_readiness_data(db=db, scope_dict=scope_dict)
        if not readiness.get("can_proceed"):
            return {
                "intent": "TIMETABLE_GENERATION",
                "selected_agent": "scheduling_agent",
                "action_type": "GENERATION_ABORTED",
                "final_response": sanitize_plain_english(
                    "Generation Aborted: Academic prerequisites have changed since the proposal was created.\n\n"
                    + "\n".join(f"- {f}" for f in readiness.get("findings", []))
                ),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        # Invoke real solver pipeline via shared service
        try:
            scope = GenerationScope(**scope_dict)
            gen_res = execute_timetable_generation(
                db=db,
                scope=scope,
                current_user=user,
                strategy=proposal.strategy,
            )
        except Exception as exc:
            return {
                "intent": "TIMETABLE_GENERATION",
                "selected_agent": "scheduling_agent",
                "action_type": "GENERATION_ERROR",
                "final_response": sanitize_plain_english(f"Solver Execution Failed: {str(exc)}"),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        if gen_res.success:
            score_val = f"{gen_res.score.total_score:.1f}/100" if gen_res.score else "N/A"
            util_val = f"{gen_res.score.room_utilization_pct:.1f}%" if gen_res.score else "N/A"
            dur_val = f"{gen_res.solve_time_seconds:.2f}s" if gen_res.solve_time_seconds else "N/A"

            reply = (
                f"Timetable Successfully Generated and Persisted.\n\n"
                f"- Version ID: #{gen_res.version_id} (Status: GENERATED / DRAFT)\n"
                f"- Solver Status: {gen_res.status} in {dur_val}\n"
                f"- Schedule Quality Score: {score_val} (Room Utilization: {util_val})\n"
                f"- Loaded Elements: {gen_res.loaded_sections} sections, {gen_res.loaded_courses} courses, "
                f"{gen_res.loaded_faculty} faculty, {gen_res.loaded_rooms} rooms, {gen_res.loaded_time_slots} slots.\n\n"
                f"Next Action: Review and finalize this draft in the Admin Timetable Review Workspace "
                f"at /admin/timetable/versions."
            )
            return {
                "intent": "TIMETABLE_GENERATION",
                "selected_agent": "scheduling_agent",
                "action_type": "GENERATION_SUCCESS",
                "final_response": sanitize_plain_english(reply),
                "tool_calls": tool_calls,
                "sources": ["Google OR-Tools CP-SAT Solver", "Timetable Scorer", "PostgreSQL Database"],
                "success": True,
            }
        else:
            diag_lines = "\n".join(f"- {d}" for d in gen_res.diagnostics) if gen_res.diagnostics else "- No specific diagnostics returned."
            reply = (
                f"Timetable Generation Infeasible: The solver could not satisfy all required constraints.\n\n"
                f"Solver Status: {gen_res.status}\n"
                f"Message: {gen_res.message}\n\n"
                f"Constraint Diagnostics:\n{diag_lines}\n\n"
                f"Recommendations:\n"
                f"1. Check if faculty weekly teaching loads are exceeded or availability slots are too narrow.\n"
                f"2. Ensure lab rooms have adequate capacities for the scheduled batch sizes.\n"
                f"3. Verify elective groups do not force conflicting parallel slot allocations."
            )
            return {
                "intent": "TIMETABLE_GENERATION",
                "selected_agent": "scheduling_agent",
                "action_type": "GENERATION_INFEASIBLE",
                "final_response": sanitize_plain_english(reply),
                "tool_calls": tool_calls,
                "sources": ["Google OR-Tools Solver Diagnostics"],
                "success": False,
            }

    # 3. Strategy / Comparison Inquiries: e.g. "compare strategies", "what are the scheduling strategies"
    if any(k in msg_lower for k in ["strategy", "strategies", "compare", "profiles", "optimization options", "consecutive"]):
        reply = (
            "Available Optimization Strategies in RIO-MJP:\n\n"
            "1. BALANCED (Default):\n"
            "   - Optimizes both student gap minimizations and faculty workload distributions evenly.\n"
            "   - Applies balanced penalty weights across room changes and late labs.\n\n"
            "2. FACULTY_COMFORT:\n"
            "   - Prioritizes registered faculty preferred time slots and minimizes mid-day teaching gaps.\n"
            "   - Smooths daily workload variance so faculty avoid 4 or more consecutive lectures.\n\n"
            "3. ROOM_EFFICIENCY:\n"
            "   - Maximizes room capacity utilization and minimizes unnecessary classroom switching for students.\n\n"
            "4. LAB_PREFERENCE:\n"
            "   - Prioritizes continuous 2-hour or 3-hour practical lab slots before late afternoon hours.\n\n"
            "All strategies enforce 100% of hard constraints (zero faculty or room double-booking). "
            "To generate using a specific strategy, mention it: Generate timetable for CSE Sem 1 with faculty comfort strategy."
        )
        return {
            "intent": "OPTIMIZATION_ADVISORY",
            "selected_agent": "scheduling_agent",
            "action_type": "ADVISORY",
            "final_response": sanitize_plain_english(reply),
            "tool_calls": tool_calls,
            "sources": ["Optimization Engine Specification"],
            "success": True,
        }

    # 3b. Lifecycle Actions: Finalize / Publish Timetable Version
    if re.search(r"\bfinalize\b.*?\b(?:timetable|version)\b", msg_lower) or re.search(r"\b(?:timetable|version)\b.*?\bfinalize\b", msg_lower):
        v_match = re.search(r"#?(\d+)", message)
        if not v_match:
            return {
                "intent": "TIMETABLE_LIFECYCLE",
                "selected_agent": "scheduling_agent",
                "action_type": "CLARIFICATION_NEEDED",
                "final_response": sanitize_plain_english(
                    "Which timetable version would you like to finalize?\n\n"
                    "Please specify the version ID (e.g. Finalize timetable version 3)."
                ),
                "tool_calls": [],
                "sources": sources,
                "success": True,
            }

        vid = int(v_match.group(1))
        version = db.query(TimetableVersion).filter(TimetableVersion.id == vid).first()
        if not version:
            return {
                "intent": "TIMETABLE_LIFECYCLE",
                "selected_agent": "scheduling_agent",
                "action_type": "VERSION_NOT_FOUND",
                "final_response": sanitize_plain_english(f"Timetable version #{vid} was not found."),
                "tool_calls": [],
                "sources": sources,
                "success": False,
            }

        if version.status == "FINALIZED":
            return {
                "intent": "TIMETABLE_LIFECYCLE",
                "selected_agent": "scheduling_agent",
                "action_type": "INFO",
                "final_response": sanitize_plain_english(f"Timetable version #{vid} (v{version.version_number}) is already finalized."),
                "tool_calls": [],
                "sources": sources,
                "success": True,
            }

        if version.status != "VALIDATED":
            return {
                "intent": "TIMETABLE_LIFECYCLE",
                "selected_agent": "scheduling_agent",
                "action_type": "STATUS_INVALID",
                "final_response": sanitize_plain_english(
                    f"Cannot finalize timetable version #{vid} because its current status is '{version.status}'. "
                    f"Timetables must pass constraint validation (status VALIDATED) in the Admin Review Workspace before finalization."
                ),
                "tool_calls": [],
                "sources": sources,
                "success": False,
            }

        consequences = f"Locks all entries of version #{version.id} against manual modifications and marks schedule ready for official campus publication."
        op_prop = operation_proposal_store.create_proposal(
            user_id=user.id,
            role=user.role,
            action_name="FINALIZE_TIMETABLE",
            entity_type="TimetableVersion",
            entity_id=version.id,
            entity_name=f"Timetable Version #{version.id} (v{version.version_number})",
            changes={"status": "FINALIZED"},
            consequences=consequences,
            proposal_data={"version_id": version.id, "version_number": version.version_number},
        )

        reply = (
            f"Timetable Finalization Proposal ({op_prop.proposal_id})\n\n"
            f"Affected Entity:\n"
            f"- Version: #{version.id} (v{version.version_number})\n"
            f"- Current Status: VALIDATED\n\n"
            f"Requested Change:\n"
            f"- Transition status from VALIDATED to FINALIZED.\n\n"
            f"Consequences:\n"
            f"- {consequences}\n\n"
            f"Administrator Confirmation Required:\n"
            f"To execute finalization, click Confirm below or type:\n"
            f"confirm {op_prop.proposal_id}\n"
            f"or say 'Yes, proceed'."
        )
        return {
            "intent": "TIMETABLE_LIFECYCLE",
            "selected_agent": "scheduling_agent",
            "action_type": "PROPOSAL_CREATED",
            "final_response": sanitize_plain_english(reply),
            "proposal": op_prop.model_dump(),
            "tool_calls": [{"tool": "prepare_finalize_timetable", "args": {"version_id": version.id}}],
            "sources": sources,
            "success": True,
        }

    # Publish Timetable request
    if re.search(r"\bpublish\b.*?\b(?:timetable|version)\b", msg_lower) or re.search(r"\b(?:timetable|version)\b.*?\bpublish\b", msg_lower):
        v_match = re.search(r"#?(\d+)", message)
        if not v_match:
            return {
                "intent": "TIMETABLE_LIFECYCLE",
                "selected_agent": "scheduling_agent",
                "action_type": "CLARIFICATION_NEEDED",
                "final_response": sanitize_plain_english(
                    "Which timetable version would you like to publish?\n\n"
                    "Please specify the version ID (e.g. Publish timetable version 3)."
                ),
                "tool_calls": [],
                "sources": sources,
                "success": True,
            }

        vid = int(v_match.group(1))
        version = db.query(TimetableVersion).filter(TimetableVersion.id == vid).first()
        if not version:
            return {
                "intent": "TIMETABLE_LIFECYCLE",
                "selected_agent": "scheduling_agent",
                "action_type": "VERSION_NOT_FOUND",
                "final_response": sanitize_plain_english(f"Timetable version #{vid} was not found."),
                "tool_calls": [],
                "sources": sources,
                "success": False,
            }

        if version.status == "PUBLISHED":
            return {
                "intent": "TIMETABLE_LIFECYCLE",
                "selected_agent": "scheduling_agent",
                "action_type": "INFO",
                "final_response": sanitize_plain_english(
                    f"Timetable version #{vid} (v{version.version_number}) is already published and active campus-wide."
                ),
                "tool_calls": [],
                "sources": sources,
                "success": True,
            }

        if version.status != "FINALIZED":
            return {
                "intent": "TIMETABLE_LIFECYCLE",
                "selected_agent": "scheduling_agent",
                "action_type": "STATUS_INVALID",
                "final_response": sanitize_plain_english(
                    f"Cannot publish timetable version #{vid} because its current status is '{version.status}'. "
                    f"Versions must be finalized (status FINALIZED) by an Administrator before campus publication."
                ),
                "tool_calls": [],
                "sources": sources,
                "success": False,
            }

        consequences = f"Makes version #{version.id} the official active schedule campus-wide across all student and faculty portals."
        op_prop = operation_proposal_store.create_proposal(
            user_id=user.id,
            role=user.role,
            action_name="PUBLISH_TIMETABLE",
            entity_type="TimetableVersion",
            entity_id=version.id,
            entity_name=f"Timetable Version #{version.id} (v{version.version_number})",
            changes={"status": "PUBLISHED"},
            consequences=consequences,
            proposal_data={"version_id": version.id, "version_number": version.version_number},
        )

        reply = (
            f"Timetable Publication Proposal ({op_prop.proposal_id})\n\n"
            f"Affected Entity:\n"
            f"- Version: #{version.id} (v{version.version_number})\n"
            f"- Current Status: FINALIZED\n\n"
            f"Requested Change:\n"
            f"- Transition status from FINALIZED to PUBLISHED.\n\n"
            f"Consequences:\n"
            f"- {consequences}\n\n"
            f"Administrator Confirmation Required:\n"
            f"To publish this schedule campus-wide, click Confirm below or type:\n"
            f"confirm {op_prop.proposal_id}\n"
            f"or say 'Yes, proceed'."
        )
        return {
            "intent": "TIMETABLE_LIFECYCLE",
            "selected_agent": "scheduling_agent",
            "action_type": "PROPOSAL_CREATED",
            "final_response": sanitize_plain_english(reply),
            "proposal": op_prop.model_dump(),
            "tool_calls": [{"tool": "prepare_publish_timetable", "args": {"version_id": version.id}}],
            "sources": sources,
            "success": True,
        }

    # 4. Scope Resolution & Readiness Pipeline
    tool_calls.append({"tool": "resolve_academic_scope", "args": {"query_text": message}})
    scope_res = resolve_academic_scope_data(db=db, query_text=message)

    if not scope_res["resolved"]:
        missing_str = ", ".join(scope_res["missing_parameters"])
        clarifications = []
        if "Department" in scope_res["missing_parameters"]:
            clarifications.append("Which academic department would you like to check? (e.g. Computer Science / CSE, Mechanical)")
        if "Semester" in scope_res["missing_parameters"]:
            clarifications.append("Which semester number would you like to evaluate? (e.g. Semester 1, Semester 5)")
        if "Program" in scope_res["missing_parameters"]:
            clarifications.append("Which degree program should be checked? (e.g. B.Tech Computer Science and Engineering)")
        prompt = " ".join(clarifications) if clarifications else (scope_res.get("clarification_prompt") or "Please provide the missing academic parameters.")
        action_verb = "evaluate timetable readiness" if is_readiness else "schedule timetable generation"
        reply = (
            f"Academic Scope Clarification Needed\n\n"
            f"I could not resolve all required scheduling parameters ({missing_str}) to {action_verb}.\n\n"
            f"{prompt}"
        )
        return {
            "intent": "TIMETABLE_READINESS" if is_readiness else "SCOPE_RESOLUTION",
            "selected_agent": "scheduling_agent",
            "action_type": "CLARIFICATION_NEEDED",
            "final_response": sanitize_plain_english(reply),
            "tool_calls": tool_calls,
            "sources": sources,
            "success": True,
        }

    resolved_scope = scope_res["scope"]
    display_info = scope_res["display"]

    # Analyze Readiness
    tool_calls.append({"tool": "analyze_scheduling_readiness", "args": {"scope": resolved_scope}})
    readiness = analyze_scheduling_readiness_data(db=db, scope_dict=resolved_scope)
    readiness_status = readiness.get("status", "BLOCKED")

    # Read-only readiness assessment: Report findings directly without generating proposals or tokens
    if is_readiness:
        findings_text = "\n".join(f"- {f}" for f in readiness.get("findings", []))
        dept_name = display_info.get("department", "Unknown Department")
        sem_name = display_info.get("semester", "Unknown Semester")
        prog_name = display_info.get("program", "Unknown Program")
        ay_name = display_info.get("academic_year", "Unknown Year")
        sec_count = display_info.get("sections_count", "0")
        sec_names = display_info.get("section_names", "None")

        if readiness_status == "BLOCKED":
            reply = (
                f"Timetable Scheduling Readiness: BLOCKED\n\n"
                f"Academic Scope:\n"
                f"- Department: {dept_name}\n"
                f"- Program: {prog_name}\n"
                f"- Semester: {sem_name}\n"
                f"- Academic Year: {ay_name}\n"
                f"- Sections: {sec_count} section(s) ({sec_names})\n\n"
                f"Readiness Findings and Blockers:\n"
                f"{findings_text}\n\n"
                f"Action Required: Resolve the missing prerequisites in the Admin Portal before attempting generation."
            )
            action_type = "READINESS_BLOCKED"
        elif readiness_status == "READY_WITH_WARNINGS":
            reply = (
                f"Timetable Scheduling Readiness: READY_WITH_WARNINGS\n\n"
                f"Academic Scope:\n"
                f"- Department: {dept_name}\n"
                f"- Program: {prog_name}\n"
                f"- Semester: {sem_name}\n"
                f"- Academic Year: {ay_name}\n"
                f"- Sections: {sec_count} section(s) ({sec_names})\n\n"
                f"Readiness Findings:\n"
                f"{findings_text}\n\n"
                f"The academic scope meets all mandatory scheduling constraints and can proceed to generation. "
                f"To generate a timetable, ask: Generate timetable for {dept_name} {sem_name}."
            )
            action_type = "READINESS_READY_WITH_WARNINGS"
        else:
            reply = (
                f"Timetable Scheduling Readiness: READY\n\n"
                f"Academic Scope:\n"
                f"- Department: {dept_name}\n"
                f"- Program: {prog_name}\n"
                f"- Semester: {sem_name}\n"
                f"- Academic Year: {ay_name}\n"
                f"- Sections: {sec_count} section(s) ({sec_names})\n\n"
                f"Readiness Findings:\n"
                f"{findings_text}\n\n"
                f"All prerequisites are verified and the scope is fully ready for timetable generation. "
                f"To generate a timetable, ask: Generate timetable for {dept_name} {sem_name}."
            )
            action_type = "READINESS_READY"

        return {
            "intent": "TIMETABLE_READINESS",
            "selected_agent": "scheduling_agent",
            "action_type": action_type,
            "final_response": sanitize_plain_english(reply),
            "proposal": None,
            "tool_calls": tool_calls,
            "sources": sources,
            "success": True,
        }

    # Detect requested strategy in message
    selected_strategy = "BALANCED"
    if "faculty" in msg_lower and ("comfort" in msg_lower or "preference" in msg_lower or "consecutive" in msg_lower):
        selected_strategy = "FACULTY_COMFORT"
    elif "room" in msg_lower and ("efficiency" in msg_lower or "utilization" in msg_lower):
        selected_strategy = "ROOM_EFFICIENCY"
    elif "lab" in msg_lower and ("preference" in msg_lower or "practical" in msg_lower):
        selected_strategy = "LAB_PREFERENCE"

    # If Blocked: Explain blockers honestly without creating proposals
    if not readiness.get("can_proceed"):
        blocker_lines = "\n".join(f"- {f}" for f in readiness.get("findings", []))
        reply = (
            f"Data Readiness Check Failed (BLOCKED)\n\n"
            f"Cannot schedule {display_info.get('department')} - {display_info.get('semester')} due to missing prerequisites:\n\n"
            f"{blocker_lines}\n\n"
            f"Required Action: Please configure the missing academic entities in the Admin Portal before attempting generation."
        )
        return {
            "intent": "READINESS_ANALYSIS",
            "selected_agent": "scheduling_agent",
            "action_type": "READINESS_BLOCKED",
            "final_response": sanitize_plain_english(reply),
            "tool_calls": tool_calls,
            "sources": sources,
            "success": True,
        }

    # If Ready / Ready with warnings: Create explicit Proposal
    proposal = proposal_store.create_proposal(
        user_id=user.id,
        role=user.role,
        scope=resolved_scope,
        scope_display=display_info,
        readiness_status=readiness.get("status", "READY"),
        readiness_summary=readiness.get("summary_metrics", {}),
        strategy=selected_strategy,
    )

    findings_text = "\n".join(f"- {f}" for f in readiness.get("findings", []))
    reply = (
        f"Timetable Generation Proposal ({proposal.proposal_id})\n\n"
        f"Resolved Scope:\n"
        f"- Department: {display_info.get('department')}\n"
        f"- Program: {display_info.get('program')}\n"
        f"- Semester: {display_info.get('semester')}\n"
        f"- Academic Year: {display_info.get('academic_year')}\n"
        f"- Sections: {display_info.get('sections_count')} section(s) ({display_info.get('section_names')})\n"
        f"- Strategy: {selected_strategy}\n\n"
        f"Readiness Status: {readiness.get('status')}\n"
        f"{findings_text}\n\n"
        f"Administrator Confirmation Required:\n"
        f"Generation runs the Google OR-Tools constraint solver and creates a new DRAFT version.\n"
        f"To proceed, click Confirm & Generate below or type:\n"
        f"confirm {proposal.proposal_id}"
    )

    return {
        "intent": "TIMETABLE_PROPOSAL",
        "selected_agent": "scheduling_agent",
        "action_type": "PROPOSAL_CREATED",
        "final_response": sanitize_plain_english(reply),
        "proposal": proposal.model_dump(),
        "tool_calls": tool_calls,
        "sources": sources,
        "success": True,
    }
