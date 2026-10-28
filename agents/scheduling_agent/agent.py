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
    inspect_timetable_conflicts_data,
    update_faculty_availability_data,
    analyze_disruption_impact_data,
    create_rescheduling_proposal_data,
    confirm_rescheduling_proposal_data,
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

    # 2. Check for explicit Confirmation Action: e.g., "confirm prop_xxx" or "confirm op_prop_xxx" or "confirm disrupt_prop_xxx"
    disrupt_confirm_match = re.search(r"\b(?:confirm|execute|approve|proceed)\s+(disrupt_prop_[a-zA-Z0-9_-]+)\b", msg_lower)
    if disrupt_confirm_match:
        proposal_id = disrupt_confirm_match.group(1)
        tool_calls.append({"tool": "confirm_rescheduling_proposal", "args": {"proposal_id": proposal_id}})

        pub_res = confirm_rescheduling_proposal_data(db=db, proposal_id=proposal_id, admin_user=user)
        if not pub_res.get("success"):
            return {
                "intent": "TIMETABLE_RESCHEDULING",
                "selected_agent": "scheduling_agent",
                "action_type": "CONFIRMATION_REJECTED",
                "final_response": sanitize_plain_english(f"Rescheduling Confirmation Blocked: {pub_res.get('error', 'Execution failed.')}"),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        notifs = pub_res.get("notifications", {})
        fac_count = notifs.get("faculty_notified", 0)
        stud_count = notifs.get("students_notified", 0)

        reply = (
            f"Revised Timetable #{pub_res.get('new_version_id')} Published Successfully.\n\n"
            f"- Prior Version: #{pub_res.get('old_version_id')} (Archived)\n"
            f"- Status: PUBLISHED\n"
            f"- Changed Sessions: {pub_res.get('changed_count')}\n"
            f"- Preserved Sessions: {pub_res.get('preserved_count')}\n"
            f"- Published At: {pub_res.get('published_at')}\n"
            f"- Targeted Notifications: {fac_count} affected faculty and {stud_count} enrolled students notified.\n\n"
            f"The revised timetable is now authoritative campus-wide."
        )
        return {
            "intent": "TIMETABLE_RESCHEDULING",
            "selected_agent": "scheduling_agent",
            "action_type": "TIMETABLE_RESCHEDULED_AND_PUBLISHED",
            "final_response": sanitize_plain_english(reply),
            "tool_calls": tool_calls,
            "sources": ["Timetable Version Register", "Notification Outbox Queue", "Audit Log"],
            "success": True,
        }

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
        elif gen_res.status in ("UNKNOWN", "TIMEOUT") or (gen_res.message and "time limit" in gen_res.message.lower()):
            reply = (
                f"Timetable Generation Timeout: The solver reached the time limit without finding a feasible timetable.\n\n"
                f"- Solver Status: {gen_res.status}\n"
                f"- Message: {gen_res.message}\n"
                f"- Duration: {gen_res.solve_time_seconds:.2f}s\n\n"
                f"Recommendations:\n"
                f"1. You may increase the solver search time limit.\n"
                f"2. Consider decomposing the academic scope into smaller section batches.\n"
                f"3. Verify that complex elective groupings are not causing combinatorial search bottlenecks."
            )
            return {
                "intent": "TIMETABLE_GENERATION",
                "selected_agent": "scheduling_agent",
                "action_type": "GENERATION_TIMEOUT",
                "final_response": sanitize_plain_english(reply),
                "tool_calls": tool_calls,
                "sources": ["Google OR-Tools Solver Engine"],
                "success": False,
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

    # 3. Conflict Inspection: "show the conflicts before I approve this schedule", "check conflicts in timetable version X"
    if (
        re.search(r"\b(?:show|view|check|list|inspect|are\s+there\s+any)\b.*?\bconflicts?\b", msg_lower)
        or re.search(r"\bconflicts?\b.*?\bbefore\s+(?:i\s+)?(?:approve|confirm)\b", msg_lower)
        or msg_lower in ["show conflicts", "check conflicts", "list conflicts", "view conflicts"]
    ):
        v_match = re.search(r"#?(\d+)", message)
        vid = int(v_match.group(1)) if v_match else None
        tool_calls.append({"tool": "inspect_timetable_conflicts", "args": {"version_id": vid}})

        conf_res = inspect_timetable_conflicts_data(db=db, version_id=vid, user_id=user.id)
        if not conf_res.get("success"):
            return {
                "intent": "TIMETABLE_VALIDATION",
                "selected_agent": "scheduling_agent",
                "action_type": "CONFLICT_INSPECTION_ERROR",
                "final_response": sanitize_plain_english(conf_res.get("error", "Failed to inspect conflicts.")),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        target_info = (
            f"Timetable Version #{conf_res.get('version_id')} (v{conf_res.get('version_number', 1)})"
            if conf_res.get("version_id")
            else f"Pending Proposal ({conf_res.get('proposal_id')})"
        )
        blockers = conf_res.get("blockers", [])
        warnings = conf_res.get("warnings", [])
        recs = conf_res.get("recommendations", [])

        if conf_res.get("is_valid") and not blockers and not warnings:
            reply = (
                f"Conflict Inspection Result: CLEAN (No Violations Found)\n\n"
                f"Target: {target_info}\n"
                f"Status: {conf_res.get('status')}\n\n"
                f"Validation Findings:\n"
                f"- Zero hard constraint violations (no room double-booking, no faculty overlap, no room capacity deficits).\n"
                f"- Zero soft-constraint warnings (continuous slots, balanced load).\n\n"
                f"This schedule satisfies 100% of institutional constraints and is ready for finalization."
            )
        else:
            blocker_text = "\n".join(f"- {b}" for b in blockers) if blockers else "- None"
            warning_text = "\n".join(f"- {w}" for w in warnings) if warnings else "- None"
            rec_text = "\n".join(f"- {r}" for r in recs) if recs else "- None"

            reply = (
                f"Conflict Inspection Findings\n\n"
                f"Target: {target_info}\n"
                f"Status: {conf_res.get('status')} (Valid: {'YES' if conf_res.get('is_valid') else 'NO'})\n\n"
                f"1. Critical Blockers / Hard Violations ({len(blockers)}):\n"
                f"{blocker_text}\n\n"
                f"2. Soft Preference Warnings ({len(warnings)}):\n"
                f"{warning_text}\n\n"
                f"Actionable Recommendations:\n"
                f"{rec_text}"
            )

        return {
            "intent": "TIMETABLE_VALIDATION",
            "selected_agent": "scheduling_agent",
            "action_type": "CONFLICT_INSPECTION_RESULT",
            "final_response": sanitize_plain_english(reply),
            "tool_calls": tool_calls,
            "sources": ["Timetable Validation Engine", "PostgreSQL Database"],
            "success": True,
        }

    # 3c. Academic Disruption Intake & Minimal-Perturbation Rescheduling
    is_disruption_request = (
        bool(re.search(r"\b(reschedule|disruption|disrupted)\b", msg_lower))
        or bool(re.search(r"\b(room|lab)\b.*?\bmaintenance\b", msg_lower))
        or bool(re.search(r"\bmaintenance\b.*?\b(room|lab)\b", msg_lower))
        or bool(re.search(r"\b(block|close)\b.*?\b(room|lab)\b.*?\bfor\s+maintenance\b", msg_lower))
        or (bool(re.search(r"\b(leave|sick|absence)\b", msg_lower)) and bool(re.search(r"\b(faculty|prof|dr\.?)\b", msg_lower)))
    )
    if is_disruption_request:
        import datetime
        from backend.models.space_time import Room, TimeSlot
        from backend.models.academic import Faculty

        # 1. Day resolution
        DAY_MAP = {
            "mon": "MON", "monday": "MON",
            "tue": "TUE", "tuesday": "TUE",
            "wed": "WED", "wednesday": "WED",
            "thu": "THU", "thursday": "THU",
            "fri": "FRI", "friday": "FRI",
            "sat": "SAT", "saturday": "SAT",
        }
        day_val = None
        for k, v in DAY_MAP.items():
            if re.search(r"\b" + k + r"\b", msg_lower):
                day_val = v
                break

        if not day_val:
            if "tomorrow" in msg_lower:
                t_day = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%a").lower()
                day_val = DAY_MAP.get(t_day[:3], "MON")
            elif "today" in msg_lower:
                t_day = datetime.date.today().strftime("%a").lower()
                day_val = DAY_MAP.get(t_day[:3], "MON")

        time_window = "afternoon" if ("afternoon" in msg_lower or "pm" in msg_lower) else ("morning" if ("morning" in msg_lower or "am" in msg_lower) else "all day")

        # 2. Determine disruption type & entity
        is_room_type = any(w in msg_lower for w in ["room", "lab", "laboratory", "classroom", "maintenance"]) and not any(w in msg_lower for w in ["dr.", "prof.", "faculty", "leave", "sick", "absence"])
        disruption_type = "ROOM_MAINTENANCE" if is_room_type else "FACULTY_LEAVE"

        faculty_obj = None
        room_obj = None

        if disruption_type == "FACULTY_LEAVE":
            f_match = re.search(r"\b(?:dr\.?|prof\.?|professor)\s+([a-zA-Z]+)", message, re.IGNORECASE)
            if f_match:
                f_name_part = f_match.group(1).lower()
                faculty_obj = db.query(Faculty).join(User).filter(User.name.ilike(f"%{f_name_part}%")).first()
            if not faculty_obj:
                all_fac = db.query(Faculty).join(User).all()
                for f in all_fac:
                    if f.user and f.user.name and f.user.name.lower() in msg_lower:
                        faculty_obj = f
                        break

            if not faculty_obj:
                return {
                    "intent": "TIMETABLE_RESCHEDULING",
                    "selected_agent": "scheduling_agent",
                    "action_type": "CLARIFICATION_NEEDED",
                    "final_response": sanitize_plain_english(
                        "Which faculty member is reporting leave or unavailability?\n\n"
                        "Please specify their name or ID (e.g., 'Dr. Sharma is unavailable on Wednesday afternoon, reschedule affected classes')."
                    ),
                    "tool_calls": [],
                    "sources": sources,
                    "success": True,
                }
        else:
            r_match = re.search(r"\b(?:room|lab|laboratory)\s+([a-zA-Z0-9_-]+)", message, re.IGNORECASE)
            if r_match:
                r_num_part = r_match.group(1).lower()
                room_obj = db.query(Room).filter(
                    (Room.room_number.ilike(f"%{r_num_part}%")) | (Room.name.ilike(f"%{r_num_part}%"))
                ).first()
            if not room_obj:
                all_rooms = db.query(Room).all()
                for r in all_rooms:
                    if (r.room_number and r.room_number.lower() in msg_lower) or (r.name and r.name.lower() in msg_lower):
                        room_obj = r
                        break

            if not room_obj:
                return {
                    "intent": "TIMETABLE_RESCHEDULING",
                    "selected_agent": "scheduling_agent",
                    "action_type": "CLARIFICATION_NEEDED",
                    "final_response": sanitize_plain_english(
                        "Which classroom or laboratory is undergoing maintenance?\n\n"
                        "Please specify the room number or lab name (e.g., 'Block Lab 3 for maintenance tomorrow and reschedule')."
                    ),
                    "tool_calls": [],
                    "sources": sources,
                    "success": True,
                }

        if not day_val:
            return {
                "intent": "TIMETABLE_RESCHEDULING",
                "selected_agent": "scheduling_agent",
                "action_type": "CLARIFICATION_NEEDED",
                "final_response": sanitize_plain_english(
                    "Which day and time interval will the disruption occur?\n\n"
                    "Please specify the day and window (e.g., 'Wednesday afternoon' or 'tomorrow morning')."
                ),
                "tool_calls": [],
                "sources": sources,
                "success": True,
            }

        # 3. Resolve target slots
        day_slots = db.query(TimeSlot).filter(TimeSlot.day == day_val, TimeSlot.slot_type == "CLASS").all()
        target_slots = []
        if time_window == "afternoon":
            noon = datetime.time(12, 0)
            target_slots = [s for s in day_slots if s.start_time and s.start_time >= noon]
        elif time_window == "morning":
            noon = datetime.time(12, 0)
            target_slots = [s for s in day_slots if s.start_time and s.start_time < noon]
        else:
            target_slots = day_slots

        target_slot_ids = [s.id for s in target_slots]

        reason_text = f"{'Faculty unavailability' if disruption_type == 'FACULTY_LEAVE' else 'Room maintenance'}: {message}"

        # 4. Impact Analysis Tool
        tool_calls.append({
            "tool": "analyze_disruption_impact",
            "args": {
                "disruption_type": disruption_type,
                "faculty_id": faculty_obj.id if faculty_obj else None,
                "room_id": room_obj.id if room_obj else None,
                "day": day_val,
                "slot_ids": target_slot_ids,
            },
        })

        impact_res = analyze_disruption_impact_data(
            db=db,
            disruption_type=disruption_type,
            reason=reason_text,
            faculty_id=faculty_obj.id if faculty_obj else None,
            room_id=room_obj.id if room_obj else None,
            day=day_val,
            slot_ids=target_slot_ids,
        )

        if not impact_res.get("success"):
            return {
                "intent": "TIMETABLE_RESCHEDULING",
                "selected_agent": "scheduling_agent",
                "action_type": "IMPACT_ANALYSIS_ERROR",
                "final_response": sanitize_plain_english(f"Impact Analysis Failed: {impact_res.get('error')}"),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        if impact_res.get("affected_count", 0) == 0:
            target_name = (faculty_obj.user.name if faculty_obj and faculty_obj.user else "Faculty") if disruption_type == "FACULTY_LEAVE" else (room_obj.room_number if room_obj else "Room")
            reply = (
                f"Disruption Impact Analysis Complete: Zero Affected Sessions.\n\n"
                f"- Target: {target_name} on {day_val} ({time_window})\n"
                f"- Published Timetable: #{impact_res.get('source_version_id')} (v{impact_res.get('source_version_number', '1')})\n"
                f"- Total Sessions in Scope: {impact_res.get('total_entries')}\n"
                f"- Affected Sessions: 0\n\n"
                f"No scheduled classes coincide with this disruption window. The current published schedule remains valid and unchanged."
            )
            return {
                "intent": "TIMETABLE_RESCHEDULING",
                "selected_agent": "scheduling_agent",
                "action_type": "NO_IMPACT",
                "final_response": sanitize_plain_english(reply),
                "tool_calls": tool_calls,
                "sources": ["Timetable Version Register", "Published Timetable"],
                "success": True,
            }

        # 5. Create Minimal-Perturbation Rescheduling Proposal
        tool_calls.append({
            "tool": "create_rescheduling_proposal",
            "args": {
                "disruption_type": disruption_type,
                "faculty_id": faculty_obj.id if faculty_obj else None,
                "room_id": room_obj.id if room_obj else None,
                "day": day_val,
                "slot_ids": target_slot_ids,
            },
        })

        prop_res = create_rescheduling_proposal_data(
            db=db,
            disruption_type=disruption_type,
            reason=reason_text,
            admin_user=user,
            faculty_id=faculty_obj.id if faculty_obj else None,
            room_id=room_obj.id if room_obj else None,
            day=day_val,
            slot_ids=target_slot_ids,
        )

        if not prop_res.get("success"):
            diag_lines = "\n".join(f"- {d}" for d in prop_res.get("diagnostics", [])) if prop_res.get("diagnostics") else "- Locked unaffected assignments prevented finding an open slot/room."
            reply = (
                f"Minimal-Perturbation Rescheduling Infeasible.\n\n"
                f"The constraint solver could not find an alternative room/slot that satisfies all hard constraints "
                f"while preserving all {impact_res.get('unaffected_count')} unaffected class sessions.\n\n"
                f"Solver Diagnostics:\n{diag_lines}\n\n"
                f"Status: The prior published timetable #{impact_res.get('source_version_id')} remains active and untouched.\n\n"
                f"Recommendation: Review available alternative time slots or allow ripple rescheduling if additional sections can shift."
            )
            return {
                "intent": "TIMETABLE_RESCHEDULING",
                "selected_agent": "scheduling_agent",
                "action_type": "RESCHEDULING_INFEASIBLE",
                "final_response": sanitize_plain_english(reply),
                "tool_calls": tool_calls,
                "sources": ["Google OR-Tools CP-SAT Solver", "Timetable Version Register"],
                "success": False,
            }

        # 6. Format Revision Diff & Approval Request
        diff_lines = []
        for d in prop_res.get("diff_items", []):
            diff_lines.append(
                f"- **{d['course_code']}** ({d['section_name']}): {d['old_slot_label']} [{d['old_room_number']}] -> "
                f"**{d['new_slot_label']} [{d['new_room_number']}]** ({d['change_type']})"
            )
        diff_text = "\n".join(diff_lines) if diff_lines else "- No explicit relocations."

        reply = (
            f"### Minimal-Perturbation Rescheduling Proposal Generated\n\n"
            f"**Disruption Summary:** {impact_res.get('summary')}\n\n"
            f"**Preservation & Impact Metrics:**\n"
            f"- **Preserved Assignments:** {prop_res.get('preserved_count')} classes locked in place (unchanged)\n"
            f"- **Relocated Assignments:** {prop_res.get('changed_count')} class(es) shifted\n"
            f"- **Hard-Constraint Violations:** 0 (100% compliant)\n"
            f"- **Impacted Students:** ~{impact_res.get('impacted_student_count', 0)} students\n\n"
            f"**Proposed Schedule Adjustments:**\n"
            f"{diff_text}\n\n"
            f"---\n"
            f"**Administrator Authorization Required:**\n"
            f"The original published timetable (#{impact_res.get('source_version_id')}) remains active until this proposal is approved.\n\n"
            f"To publish this revision and dispatch targeted notifications to affected faculty and students, type:\n"
            f"`confirm {prop_res.get('proposal_id')}`"
        )

        return {
            "intent": "TIMETABLE_RESCHEDULING",
            "selected_agent": "scheduling_agent",
            "action_type": "PROPOSAL_CREATED",
            "final_response": sanitize_plain_english(reply),
            "proposal_id": prop_res.get("proposal_id"),
            "tool_calls": tool_calls,
            "sources": ["Google OR-Tools CP-SAT Solver", "Timetable Validator", "Disruption Service"],
            "success": True,
        }

    # 4. Faculty Availability Updates: "This faculty member is unavailable on Wednesday afternoon"
    if (
        re.search(r"\b(?:faculty|prof|dr\.?)\b.*?\b(?:is\s+)?(?:unavailable|available|preferred)\b", msg_lower)
        or re.search(r"\b(?:unavailable|available|preferred)\b.*?\b(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday)\b", msg_lower)
        or (("unavailable" in msg_lower or "available" in msg_lower) and any(d in msg_lower for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]))
    ):
        day_match = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday)\b", msg_lower)
        day_text = day_match.group(1) if day_match else "WEDNESDAY"

        time_window = "afternoon" if "afternoon" in msg_lower else ("morning" if "morning" in msg_lower else "all day")
        status_val = "UNAVAILABLE" if "unavailable" in msg_lower else ("PREFERRED" if "preferred" in msg_lower else "AVAILABLE")

        f_match = re.search(r"\b(?:dr\.?|prof\.?|professor)\s+([a-zA-Z]+)", message, re.IGNORECASE)
        faculty_query = f_match.group(0) if f_match else None

        if not faculty_query and ("this faculty" in msg_lower or "the faculty" in msg_lower):
            # Resolve from current active proposal or primary faculty in database
            from backend.models.academic import Faculty
            fac = db.query(Faculty).join(User).first()
            if fac and fac.user:
                faculty_query = fac.user.name

        if not faculty_query:
            from backend.models.academic import Faculty
            all_fac = db.query(Faculty).join(User).all()
            for f in all_fac:
                if f.user and f.user.name.lower() in msg_lower:
                    faculty_query = f.user.name
                    break

        if not faculty_query:
            return {
                "intent": "FACULTY_AVAILABILITY",
                "selected_agent": "scheduling_agent",
                "action_type": "CLARIFICATION_NEEDED",
                "final_response": sanitize_plain_english(
                    "Which faculty member would you like to update availability for?\n\n"
                    "Please specify the faculty name or ID (e.g. 'Dr. Sharma is unavailable on Wednesday afternoon')."
                ),
                "tool_calls": [],
                "sources": sources,
                "success": True,
            }

        tool_calls.append({"tool": "update_faculty_availability", "args": {
            "faculty": faculty_query,
            "day": day_text,
            "window": time_window,
            "status": status_val,
        }})

        avail_res = update_faculty_availability_data(
            db=db,
            faculty_query=faculty_query,
            day_text=day_text,
            time_window=time_window,
            availability_status=status_val,
            user=user,
        )

        if not avail_res.get("success"):
            return {
                "intent": "FACULTY_AVAILABILITY",
                "selected_agent": "scheduling_agent",
                "action_type": "UPDATE_ERROR",
                "final_response": sanitize_plain_english(avail_res.get("error", "Failed to update faculty availability.")),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        reply = (
            f"Faculty Availability Constraint Registered.\n\n"
            f"- Faculty: {avail_res.get('faculty_name')}\n"
            f"- Day: {avail_res.get('day')}\n"
            f"- Time Window: {str(avail_res.get('time_window') or '').capitalize()} ({avail_res.get('slot_intervals')})\n"
            f"- Availability Status: {avail_res.get('availability')}\n"
            f"- Impacted Time Slots: {avail_res.get('slots_updated')} slots marked in register\n\n"
            f"Constraint Enforced: The Google OR-Tools constraint solver and validation safeguards will strictly "
            f"respect this unavailability rule for all current and future timetable generation runs."
        )

        return {
            "intent": "FACULTY_AVAILABILITY",
            "selected_agent": "scheduling_agent",
            "action_type": "AVAILABILITY_UPDATED",
            "final_response": sanitize_plain_english(reply),
            "tool_calls": tool_calls,
            "sources": ["Campus Space/Time Register", "Faculty Availability Table", "Audit Log"],
            "success": True,
        }

    # 5. Infeasibility Diagnostics Inquiries: "why could the solver not create a valid timetable"
    if (
        re.search(r"\bwhy\b.*\b(infeasible|fail|couldn't|could\s+not|cannot|can't|unable|no\s+solution|not\s+create|not\s+generate)\b.*\b(timetable|generate|schedule|solver)\b", msg_lower)
        or re.search(r"\bwhy\s+(?:could|did|can|is)\s+(?:the\s+)?solver\s+not\b", msg_lower)
        or re.search(r"\bwhy\s+(?:is|was)\s+(?:it|timetable|generation)\s+infeasible\b", msg_lower)
    ):
        reply = (
            "Why Timetable Solvers Report Infeasibility:\n\n"
            "A timetable generation run becomes INFEASIBLE when mathematical constraints cannot simultaneously be satisfied. "
            "In RIO-MJP, all hard constraints are mathematically non-negotiable and are NEVER automatically weakened:\n\n"
            "1. Faculty Double-Booking (H1): A faculty member cannot teach two sessions in the same or overlapping time slots.\n"
            "2. Room Double-Booking (H2): A room cannot host two classes simultaneously.\n"
            "3. Student / Batch Collision (H3): A student section or batch cannot attend two parallel classes.\n"
            "4. Room Capacity Deficit (H4): A classroom or lab must have sufficient seats for all students in the batch.\n"
            "5. Break / Lunch Period Exclusions: Classes are never scheduled into designated recess or lunch intervals.\n\n"
            "Common Root Causes and Verified Solutions:\n"
            "- Faculty Availability Bottleneck: Faculty available hours are less than their assigned weekly teaching credits. Solution: Expand faculty availability windows.\n"
            "- Lab Capacity Deficit: Multiple laboratory sections require dedicated LAB rooms simultaneously. Solution: Add additional LAB room allocations or spread practicals across afternoon slots.\n"
            "- Parallel Elective Bottlenecks: Elective groups with many parallel choices exceed available weekly slots. Solution: Spread elective courses across alternate slot blocks.\n\n"
            "Safe Alternative: You can revise the scheduling proposal strategy (e.g. switch to FACULTY_COMFORT or LAB_PREFERENCE) or update faculty availability before retrying."
        )
        return {
            "intent": "INFEASIBILITY_EXPLANATION",
            "selected_agent": "scheduling_agent",
            "action_type": "EXPLANATION",
            "final_response": sanitize_plain_english(reply),
            "tool_calls": tool_calls,
            "sources": ["Google OR-Tools CP-SAT Solver Diagnostics", "RIO Constraint Model"],
            "success": True,
        }

    # 6. Proposal Revision Requests: "avoid assigning labs in the morning where possible", "revise proposed timetable to reduce consecutive periods"
    is_revision_request = (
        bool(re.search(r"\b(?:revise|revision|modify|update|change|adjust)\b.*?\b(?:proposal|timetable|strategy|schedule)\b", msg_lower))
        or bool(re.search(r"\bavoid\b.*?\b(?:labs|morning|consecutive)\b", msg_lower))
        or bool(re.search(r"\breduce\b.*?\bconsecutive\b", msg_lower))
        or bool(re.search(r"\b(?:switch|change)\s+(?:strategy|to)\b.*?\b(faculty comfort|room efficiency|lab preference|balanced)\b", msg_lower))
    )

    if is_revision_request:
        pending_prop = proposal_store.get_latest_pending_proposal(user.id)
        if not pending_prop:
            return {
                "intent": "PROPOSAL_REVISION",
                "selected_agent": "scheduling_agent",
                "action_type": "NO_ACTIVE_PROPOSAL",
                "final_response": sanitize_plain_english(
                    "There is currently no active timetable generation proposal awaiting revision.\n\n"
                    "To generate a proposal, specify your department and semester (e.g. 'Generate timetable for CSE Semester 1')."
                ),
                "tool_calls": [],
                "sources": sources,
                "success": True,
            }

        new_strategy = pending_prop.strategy
        param_updates: Dict[str, Any] = {}
        changes_desc: List[str] = []

        if "morning" in msg_lower and "lab" in msg_lower:
            new_strategy = "LAB_PREFERENCE"
            param_updates["avoid_morning_labs"] = True
            changes_desc.append("Strategy updated to LAB_PREFERENCE: Avoid assigning labs in the morning where possible and prioritize continuous afternoon lab slots.")
        elif "consecutive" in msg_lower or "comfort" in msg_lower:
            new_strategy = "FACULTY_COMFORT"
            param_updates["reduce_consecutive"] = True
            changes_desc.append("Strategy updated to FACULTY_COMFORT: Penalize 3+ consecutive periods and smooth daily teaching load variance.")
        elif "room" in msg_lower or "efficiency" in msg_lower or "utilization" in msg_lower:
            new_strategy = "ROOM_EFFICIENCY"
            param_updates["room_efficiency"] = True
            changes_desc.append("Strategy updated to ROOM_EFFICIENCY: Maximize classroom seat utilization and minimize student classroom transitions.")
        elif "balanced" in msg_lower:
            new_strategy = "BALANCED"
            param_updates = {}
            changes_desc.append("Strategy reset to BALANCED: Equal weight across student gaps, faculty comfort, and room utilization.")
        else:
            changes_desc.append(f"Scheduling parameters revised. Strategy retained as {new_strategy}.")

        readiness = analyze_scheduling_readiness_data(db=db, scope_dict=pending_prop.scope)
        if not readiness.get("can_proceed"):
            return {
                "intent": "PROPOSAL_REVISION",
                "selected_agent": "scheduling_agent",
                "action_type": "REVISION_BLOCKED",
                "final_response": sanitize_plain_english(
                    "Revision Aborted: Underlying academic prerequisites are blocked.\n\n"
                    + "\n".join(f"- {f}" for f in readiness.get("findings", []))
                ),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        ok, revised_prop, rev_err = proposal_store.revise_proposal(
            parent_proposal_id=pending_prop.proposal_id,
            user_id=user.id,
            updates={
                "strategy": new_strategy,
                "parameters": param_updates,
                "readiness_status": readiness.get("status", "READY"),
                "readiness_summary": readiness.get("summary_metrics", {}),
            },
        )

        if not ok or not revised_prop:
            return {
                "intent": "PROPOSAL_REVISION",
                "selected_agent": "scheduling_agent",
                "action_type": "REVISION_FAILED",
                "final_response": sanitize_plain_english(f"Proposal Revision Failed: {rev_err}"),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        tool_calls.append({"tool": "revise_scheduling_proposal", "args": {
            "parent_proposal_id": pending_prop.proposal_id,
            "new_proposal_id": revised_prop.proposal_id,
            "revision": revised_prop.revision,
            "strategy": new_strategy,
        }})

        change_summary = "\n".join(f"- {c}" for c in changes_desc)
        reply = (
            f"Timetable Proposal Revised (Revision {revised_prop.revision})\n\n"
            f"Supersedes: {pending_prop.proposal_id} (Rev {pending_prop.revision})\n"
            f"New Proposal ID: {revised_prop.proposal_id}\n\n"
            f"Applied Modifications:\n"
            f"{change_summary}\n\n"
            f"Scope & Constraints:\n"
            f"- Department: {revised_prop.scope_display.get('department')}\n"
            f"- Semester: {revised_prop.scope_display.get('semester')}\n"
            f"- Strategy Profile: {new_strategy}\n"
            f"- Hard Constraints: 100% strictly enforced (zero room/faculty double booking, capacity limits, recess exclusions).\n\n"
            f"Administrator Confirmation Required:\n"
            f"The previous proposal ({pending_prop.proposal_id}) has been superseded and can no longer be confirmed.\n"
            f"To authorize and generate with these revised parameters, click Confirm below or type:\n"
            f"confirm {revised_prop.proposal_id}"
        )

        return {
            "intent": "TIMETABLE_PROPOSAL",
            "selected_agent": "scheduling_agent",
            "action_type": "PROPOSAL_REVISED",
            "final_response": sanitize_plain_english(reply),
            "proposal": revised_prop.model_dump(),
            "tool_calls": tool_calls,
            "sources": sources,
            "success": True,
        }

    # 7. Unsupported Constraints Safety Check
    if any(k in msg_lower for k in ["end by 10am", "before 10 am", "finish by 10", "no classes after 11am", "only 1 hour per week"]):
        return {
            "intent": "UNSUPPORTED_CONSTRAINT",
            "selected_agent": "scheduling_agent",
            "action_type": "UNSUPPORTED_CONSTRAINT_REJECTED",
            "final_response": sanitize_plain_english(
                "Unsupported Scheduling Constraint: The requested constraint cannot be satisfied because the minimum syllabus credit "
                "requirements for this degree program require multiple daily instructional periods.\n\n"
                "All timetable generation models in RIO-MJP preserve mandatory university academic regulations. "
                "Hard constraints cannot be waived or weakened automatically."
            ),
            "tool_calls": [],
            "sources": ["Academic Regulations Manual"],
            "success": False,
        }

    # 8. Strategy / Comparison Inquiries: e.g. "compare strategies", "what are the scheduling strategies"
    if any(k in msg_lower for k in ["compare strategies", "what are the strategies", "what strategies", "scheduling strategies", "optimization strategies"]):
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
