"""
agents/resource_agent/agent.py
------------------------------
Advanced Intelligent Resource Agent for RIO-MJP.
Orchestrates:
- RESOURCE_DISCOVERY: Searching facilities by type, capacity, building, and location.
- AVAILABILITY_CHECK: Authoritative interval conflict detection against approved bookings and timetable classes.
- CONFLICT_EXPLANATION: Grounded breakdown of overlapping events with genuine alternatives.
- BOOKING_PROPOSAL: High-entropy, single-use, bounded proposal creation (`res_prop_<hex>`).
- CONFIRMATION & EXECUTION: Atomic freshness check and booking creation (`PENDING`) through backend domain service.
- STATUS & TRACKING: Detailed booking lookup and history inspection with role-based privacy masking.
- CANCELLATION: Owner and Admin authorized cancellation with state guards.
- ROLE GUARD: Strict enforcement preventing non-admin users from approving or rejecting bookings.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.services.resource_booking_service import find_alternative_resources
from agents.state.state import AgentState
from agents.resource_agent.proposal_store import resource_proposal_store
from agents.common.formatter import sanitize_plain_english
from agents.resource_agent.parser import (
    parse_date,
    parse_time_interval,
    extract_resource_details,
)
from agents.tools.resource_tools import (
    discover_resources_data,
    check_resource_availability_data,
    get_user_bookings_data,
    get_booking_details_data,
    execute_create_booking_data,
    execute_cancel_booking_data,
)


def run_resource_agent(
    state: AgentState,
    db: Session,
    user: User,
) -> Dict[str, Any]:
    """
    Main invocation entry point for the Resource Agent.
    Operates within the request-scoped LangGraph execution workflow.
    """
    message = state.get("message", "").strip()
    msg_lower = message.lower()

    tool_calls: List[Dict[str, Any]] = []
    sources: List[str] = ["Campus Facilities Register", "Resource Allocation Engine"]

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Proposal Confirmation (res_prop_<hex>)
    # ──────────────────────────────────────────────────────────────────────────
    confirm_match = re.search(r"\b(?:confirm|execute|approve|proceed)\s+(res_prop_[a-zA-Z0-9_-]+)\b", msg_lower)
    if confirm_match:
        proposal_id = confirm_match.group(1)
        tool_calls.append({"tool": "confirm_resource_proposal", "args": {"proposal_id": proposal_id}})

        # Atomically check and consume proposal
        success, proposal, err_msg = resource_proposal_store.consume_proposal(
            proposal_id=proposal_id,
            user_id=user.id,
        )
        if not success or not proposal:
            return {
                "intent": "RESOURCE_BOOKING",
                "selected_agent": "resource_agent",
                "action_type": "CONFIRMATION_REJECTED",
                "final_response": sanitize_plain_english(f"Booking Confirmation Blocked: {err_msg}"),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        # Authoritative freshness check: Revalidate availability right before writing
        try:
            d = datetime.date.fromisoformat(proposal.date)
            st = datetime.time.fromisoformat(proposal.start_time)
            et = datetime.time.fromisoformat(proposal.end_time)
        except (ValueError, TypeError) as format_err:
            return {
                "intent": "RESOURCE_BOOKING",
                "selected_agent": "resource_agent",
                "action_type": "CONFIRMATION_REJECTED",
                "final_response": sanitize_plain_english(f"Booking Confirmation Blocked: Proposal contains invalid date or time format ({format_err})."),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        if et <= st:
            return {
                "intent": "RESOURCE_BOOKING",
                "selected_agent": "resource_agent",
                "action_type": "CONFIRMATION_REJECTED",
                "final_response": "Booking Confirmation Blocked: Proposal time interval is invalid (end time is before or equal to start time).",
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        fresh_avail = check_resource_availability_data(
            db=db,
            resource_id=proposal.resource_id,
            date=d,
            start_time=st,
            end_time=et,
        )

        if not fresh_avail.get("available"):
            conflicts_desc = "\n".join(f"- {c['description']}" for c in fresh_avail.get("conflicts", []))
            alts_desc = "\n".join(
                f"- {a['name']} ({a['resource_type']}, Location: {a.get('location', 'N/A')}, Capacity: {a.get('capacity', 'N/A')})"
                for a in fresh_avail.get("alternatives", [])
            )
            reply = (
                f"Booking Confirmation Aborted: Resource Is No Longer Available\n\n"
                f"A conflicting booking or timetable entry was registered for {proposal.resource_name} "
                f"after this proposal was created:\n\n"
                f"{conflicts_desc}\n\n"
            )
            if alts_desc:
                reply += f"Recommended Alternatives:\n{alts_desc}\n\n"
            reply += "Please select an alternative or request a different time slot."

            return {
                "intent": "RESOURCE_BOOKING",
                "selected_agent": "resource_agent",
                "action_type": "CONFIRMATION_REJECTED",
                "final_response": sanitize_plain_english(reply),
                "tool_calls": tool_calls,
                "sources": ["Resource Allocation Engine", "Published Timetable"],
                "success": False,
            }

        # Execute booking creation through domain service
        booking_result = execute_create_booking_data(
            db=db,
            resource_id=proposal.resource_id,
            date=d,
            start_time=st,
            end_time=et,
            purpose=proposal.purpose,
            user=user,
        )

        if not booking_result.get("success"):
            return {
                "intent": "RESOURCE_BOOKING",
                "selected_agent": "resource_agent",
                "action_type": "BOOKING_ERROR",
                "final_response": sanitize_plain_english(f"Booking Execution Failed: {booking_result.get('error')}"),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        booking_id = booking_result["booking_id"]
        status_val = booking_result["status"]
        reply = (
            f"Resource booking request submitted successfully.\n\n"
            f"- Booking ID: #{booking_id}\n"
            f"- Facility: {proposal.resource_name} ({proposal.resource_type})\n"
            f"- Location: {proposal.location or 'Main Campus'}\n"
            f"- Capacity: {proposal.capacity or 'Standard'} seats\n"
            f"- Date: {proposal.date}\n"
            f"- Time Interval: {proposal.start_time[:5]} - {proposal.end_time[:5]}\n"
            f"- Purpose: {proposal.purpose}\n"
            f"- Status: {status_val}\n\n"
            f"Next Steps: Your booking request is now queued for administrator review. "
            f"You will see it in your My Bookings dashboard, or you can ask: Status of booking #{booking_id}."
        )

        return {
            "intent": "RESOURCE_BOOKING",
            "selected_agent": "resource_agent",
            "action_type": "BOOKING_CREATED",
            "final_response": sanitize_plain_english(reply),
            "tool_calls": tool_calls,
            "sources": ["Resource Booking Register", "Audit Log"],
            "success": True,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Administrative Action Guard (Approve / Reject booking)
    # ──────────────────────────────────────────────────────────────────────────
    if re.search(r"\b(approve|reject)\b.*?\bbooking\b", msg_lower):
        if user.role != "ADMIN":
            return {
                "intent": "RESOURCE_ADMIN",
                "selected_agent": "resource_agent",
                "action_type": "ACCESS_DENIED",
                "final_response": sanitize_plain_english(
                    f"Administrative Privilege Required\n\n"
                    f"Only university Administrators possess the authority to approve or reject campus resource bookings.\n\n"
                    f"As a {user.role.capitalize()}, you can view your submitted requests, check real-time facility availability, "
                    f"or request reservations through this assistant."
                ),
                "tool_calls": [],
                "sources": sources,
                "success": True,
            }
        else:
            return {
                "intent": "RESOURCE_ADMIN",
                "selected_agent": "resource_agent",
                "action_type": "ADMIN_GUIDANCE",
                "final_response": sanitize_plain_english(
                    "Administrative Booking Review\n\n"
                    "Resource booking approvals and rejections require institutional verification of physical room arrangements, "
                    "power and AV readiness, and conflict histories.\n\n"
                    "Please finalize approvals and rejections directly in the Admin Resource Management Workspace at /admin/resources."
                ),
                "tool_calls": [],
                "sources": sources,
                "success": True,
            }

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Booking Cancellation
    # ──────────────────────────────────────────────────────────────────────────
    cancel_match = re.search(r"\bcancel\b.*?\bbooking\b.*?#?(\d+)", msg_lower) or re.search(r"\bbooking\b.*?#?(\d+).*?\bcancel\b", msg_lower)
    if cancel_match:
        bid = int(cancel_match.group(1))
        tool_calls.append({"tool": "execute_cancel_booking", "args": {"booking_id": bid}})

        cancel_res = execute_cancel_booking_data(db=db, booking_id=bid, user=user)
        if cancel_res.get("success"):
            return {
                "intent": "RESOURCE_BOOKING",
                "selected_agent": "resource_agent",
                "action_type": "BOOKING_CANCELLED",
                "final_response": sanitize_plain_english(
                    f"Booking Request Cancelled\n\n"
                    f"Booking #{bid} for {cancel_res.get('resource_name')} has been marked as CANCELLED.\n"
                    f"Any scheduled reservations for this slot have been released."
                ),
                "tool_calls": tool_calls,
                "sources": ["Resource Booking Register", "Audit Log"],
                "success": True,
            }
        else:
            return {
                "intent": "RESOURCE_BOOKING",
                "selected_agent": "resource_agent",
                "action_type": "CANCELLATION_FAILED",
                "final_response": sanitize_plain_english(f"Cancellation Failed: {cancel_res.get('error')}"),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

    if re.search(r"\bcancel\b.*?\b(my\s+)?booking\b", msg_lower):
        # User wants to cancel but didn't provide booking ID
        my_bookings = get_user_bookings_data(db=db, user=user, status_filter="PENDING")
        if my_bookings["count"] == 0:
            my_bookings = get_user_bookings_data(db=db, user=user)

        if my_bookings["count"] == 0:
            return {
                "intent": "RESOURCE_BOOKING",
                "selected_agent": "resource_agent",
                "action_type": "INFO",
                "final_response": "You currently do not have any active resource booking requests to cancel.",
                "tool_calls": tool_calls,
                "sources": sources,
                "success": True,
            }

        list_lines = "\n".join(
            f"- Booking #{b['booking_id']}: {b['resource_name']} on {b['date']} ({b['start_time'][:5]} - {b['end_time'][:5]}) - Status: {b['status']}"
            for b in my_bookings["bookings"][:5]
        )
        return {
            "intent": "RESOURCE_BOOKING",
            "selected_agent": "resource_agent",
            "action_type": "CLARIFICATION_NEEDED",
            "final_response": sanitize_plain_english(
                f"Which booking would you like to cancel?\n\n"
                f"Here are your recent booking requests:\n"
                f"{list_lines}\n\n"
                f"Please specify the booking ID (e.g. Cancel booking #{my_bookings['bookings'][0]['booking_id']})."
            ),
            "tool_calls": tool_calls,
            "sources": sources,
            "success": True,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Booking Status & History Inquiries
    # ──────────────────────────────────────────────────────────────────────────
    status_id_match = re.search(r"\b(?:status|details|info)\s+(?:of\s+)?(?:booking|request)?\s*#?(\d+)\b", msg_lower)
    if status_id_match:
        bid = int(status_id_match.group(1))
        tool_calls.append({"tool": "get_booking_details", "args": {"booking_id": bid}})

        detail = get_booking_details_data(db=db, booking_id=bid, user=user)
        if "error" in detail:
            return {
                "intent": "RESOURCE_QUERY",
                "selected_agent": "resource_agent",
                "action_type": "INFO",
                "final_response": sanitize_plain_english(f"{detail['error']}"),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": False,
            }

        approver_info = f"- Approved By: {detail['approver_name']}\n" if detail.get("approver_name") else ""
        requester_info = f"- Requested By: {detail['requester_name']}" if detail.get("requester_name") else ""
        if detail.get("requester_email"):
            requester_info += f" ({detail['requester_email']})"

        reply = (
            f"Booking Details: #{detail['booking_id']}\n\n"
            f"- Facility: {detail['resource_name']} ({detail.get('resource_type', 'N/A')})\n"
            f"- Location: {detail.get('location', 'Main Campus')}\n"
            f"- Capacity: {detail.get('capacity', 'Standard')} seats\n"
            f"- Date: {detail['date']}\n"
            f"- Time: {detail['start_time'][:5]} - {detail['end_time'][:5]}\n"
            f"- Status: {detail['status']}\n"
            f"- Purpose: {detail.get('purpose', 'N/A')}\n"
            f"{requester_info}\n"
            f"{approver_info}"
        )

        return {
            "intent": "RESOURCE_QUERY",
            "selected_agent": "resource_agent",
            "action_type": "BOOKING_DETAILS",
            "final_response": sanitize_plain_english(reply),
            "tool_calls": tool_calls,
            "sources": ["Resource Booking Register"],
            "success": True,
        }

    if any(k in msg_lower for k in ["my bookings", "my booking", "show my bookings", "list my bookings", "track my bookings"]):
        tool_calls.append({"tool": "get_user_bookings", "args": {"user_id": user.id}})
        b_data = get_user_bookings_data(db=db, user=user)

        if b_data["count"] == 0:
            return {
                "intent": "RESOURCE_QUERY",
                "selected_agent": "resource_agent",
                "action_type": "BOOKINGS_LIST",
                "final_response": "You do not have any submitted resource bookings on record.",
                "tool_calls": tool_calls,
                "sources": sources,
                "success": True,
            }

        table_rows = []
        for b in b_data["bookings"]:
            table_rows.append(
                f"- Booking #{b['booking_id']}: {b['resource_name']} on {b['date']} ({b['start_time'][:5]} - {b['end_time'][:5]}) - Status: {b['status']}"
            )

        reply = (
            f"Your Campus Resource Bookings ({b_data['count']} found):\n\n"
            + "\n".join(table_rows) + "\n\n"
            f"To view details or cancel, ask: Status of booking #<id> or Cancel booking #<id>."
        )

        return {
            "intent": "RESOURCE_QUERY",
            "selected_agent": "resource_agent",
            "action_type": "BOOKINGS_LIST",
            "final_response": sanitize_plain_english(reply),
            "tool_calls": tool_calls,
            "sources": ["Resource Booking Register"],
            "success": True,
        }

    req_date = parse_date(message)
    req_start, req_end = parse_time_interval(message)
    res_details = extract_resource_details(message)

    # Database-grounded resource matching takes precedence over regex heuristics
    active_resources = db.query(Resource).filter(Resource.status == "ACTIVE").all()
    for r in sorted(active_resources, key=lambda x: len(x.name or ""), reverse=True):
        if r.name and r.name.lower() in msg_lower:
            res_details["resource_name"] = r.name
            res_details["resource_id"] = r.id
            res_details["resource_type"] = r.resource_type
            break

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Resource Discovery / Inventory Queries (without explicit time interval)
    # ──────────────────────────────────────────────────────────────────────────
    is_discovery = any(k in msg_lower for k in [
        "find", "search", "show", "what", "which", "list", "available resources", "facilities", "rooms", "labs", "halls"
    ]) and not (req_date and req_start and req_end)

    if is_discovery and not any(k in msg_lower for k in ["book", "reserve"]):
        tool_calls.append({
            "tool": "discover_resources",
            "args": {
                "resource_type": res_details.get("resource_type"),
                "min_capacity": res_details.get("min_capacity"),
            },
        })

        search_kw = res_details.get("resource_name") or None
        disc = discover_resources_data(
            db=db,
            resource_type=res_details.get("resource_type"),
            min_capacity=res_details.get("min_capacity"),
            search_query=search_kw,
        )

        if disc["count"] == 0:
            return {
                "intent": "RESOURCE_DISCOVERY",
                "selected_agent": "resource_agent",
                "action_type": "DISCOVERY_RESULTS",
                "final_response": sanitize_plain_english(
                    "No Matching Resources Found\n\n"
                    "We could not locate any active facilities matching your requested filters. "
                    "Try broadening your search criteria: Find seminar halls or Show computer labs."
                ),
                "tool_calls": tool_calls,
                "sources": sources,
                "success": True,
            }

        res_lines = []
        for r in disc["resources"]:
            status_text = "Unavailable (Active Booking)" if r.get("is_locked") else "Available"
            res_lines.append(
                f"- {r['name']} (#{r['id']}) - Type: {r['resource_type']}, Location: {r['location'] or 'Main Block'}, Capacity: {r['capacity'] or 'Standard'} seats - Status: {status_text}"
            )

        reply = (
            f"Matching Campus Facilities ({disc['count']} found):\n\n"
            + "\n".join(res_lines) + "\n\n"
            f"To check real-time availability or book a facility, please provide your target date and time:\n"
            f"(e.g. Book {disc['resources'][0]['name']} tomorrow from 2:00 PM to 4:00 PM for Guest Lecture)"
        )

        return {
            "intent": "RESOURCE_DISCOVERY",
            "selected_agent": "resource_agent",
            "action_type": "DISCOVERY_RESULTS",
            "final_response": sanitize_plain_english(reply),
            "tool_calls": tool_calls,
            "sources": sources,
            "success": True,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 7. Targeted Clarification for Incomplete Interval / Booking Requests
    # ──────────────────────────────────────────────────────────────────────────
    target_res: Optional[Resource] = None
    if res_details.get("resource_id"):
        target_res = db.query(Resource).filter(Resource.id == res_details["resource_id"]).first()
    if not target_res and res_details.get("resource_name"):
        target_res = db.query(Resource).filter(Resource.name.ilike(f"%{res_details['resource_name']}%")).first()

    # If the named resource is already known and has an active booking lock, report immediately
    if target_res:
        active_lock = (
            db.query(ResourceBooking)
            .filter(
                ResourceBooking.resource_id == target_res.id,
                ResourceBooking.status.in_(["PENDING", "APPROVED"]),
            )
            .first()
        )
        if active_lock:
            eligible_alts = find_alternative_resources(
                db=db,
                resource_id=target_res.id,
                date=req_date or datetime.date.today(),
                start_time=req_start or datetime.time(9, 0),
                end_time=req_end or datetime.time(10, 0),
            )
            lock_reply = (
                f"Resource already booked. {target_res.name} has an active booking and is not available "
                f"for another booking. Please select another resource."
            )
            if eligible_alts:
                alt_lines = "\n".join(
                    f"- {a.name} ({a.resource_type}, Location: {a.location or 'Main Campus'}, Capacity: {a.capacity or 'Standard'} seats)"
                    for a in eligible_alts
                )
                lock_reply += f"\n\nAvailable alternative resources:\n{alt_lines}"
            return {
                "intent": "RESOURCE_BOOKING",
                "selected_agent": "resource_agent",
                "action_type": "RESOURCE_UNAVAILABLE",
                "final_response": sanitize_plain_english(lock_reply),
                "tool_calls": tool_calls,
                "sources": ["Resource Allocation Engine"],
                "success": False,
            }

    missing_elements: List[str] = []
    if not res_details.get("resource_name") and not res_details.get("resource_type") and not res_details.get("resource_id"):
        missing_elements.append("the specific facility or resource type (e.g., Seminar Hall A, CSE Lab 1)")
    if req_date is None:
        missing_elements.append("the booking date (e.g., 'tomorrow' or '2026-10-25')")
    if req_start is None or req_end is None:
        missing_elements.append("the time interval (e.g., '2:00 PM to 4:00 PM')")

    if missing_elements or req_date is None or req_start is None or req_end is None:
        prompt = "To check availability or prepare a booking proposal, please provide:\n" + "\n".join(f"- {m}" for m in missing_elements)
        return {
            "intent": "RESOURCE_BOOKING",
            "selected_agent": "resource_agent",
            "action_type": "CLARIFICATION_NEEDED",
            "final_response": sanitize_plain_english(f"Resource Details Needed\n\n{prompt}"),
            "tool_calls": tool_calls,
            "sources": sources,
            "success": True,
        }

    # At this point, req_date, req_start, and req_end are strictly narrowed to non-None instances
    valid_date: datetime.date = req_date
    valid_start: datetime.time = req_start
    valid_end: datetime.time = req_end

    if valid_end <= valid_start:
        return {
            "intent": "RESOURCE_BOOKING",
            "selected_agent": "resource_agent",
            "action_type": "CLARIFICATION_NEEDED",
            "final_response": (
                "Invalid Time Interval: The requested end time must be after the start time. "
                "Please specify a valid window (e.g. 10:00 AM to 12:00 PM or 2:00 PM to 4:00 PM)."
            ),
            "tool_calls": tool_calls,
            "sources": sources,
            "success": True,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 8. Resolve Target Resource
    # ──────────────────────────────────────────────────────────────────────────
    target_res: Optional[Resource] = None

    if res_details.get("resource_id"):
        target_res = db.query(Resource).filter(Resource.id == res_details["resource_id"]).first()

    if not target_res and res_details.get("resource_name"):
        r_name = res_details["resource_name"]
        # Case-insensitive substring match
        target_res = db.query(Resource).filter(Resource.name.ilike(f"%{r_name}%")).first()

    if not target_res and res_details.get("resource_type"):
        # Match first active resource of that type with capacity >= min_capacity
        q = db.query(Resource).filter(
            Resource.resource_type == res_details["resource_type"],
            Resource.status == "ACTIVE",
        )
        if res_details.get("min_capacity"):
            q = q.filter(Resource.capacity >= res_details["min_capacity"])
        target_res = q.order_by(Resource.capacity.asc()).first()

    if not target_res:
        return {
            "intent": "RESOURCE_BOOKING",
            "selected_agent": "resource_agent",
            "action_type": "RESOURCE_NOT_FOUND",
            "final_response": sanitize_plain_english(
                f"Resource Not Found: We could not identify an active campus resource matching '{message}'.\n\n"
                f"You can ask: Find seminar halls or List available labs to view registered facilities."
            ),
            "tool_calls": tool_calls,
            "sources": sources,
            "success": False,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 9. Grounded Availability Check & Conflict Detection
    # ──────────────────────────────────────────────────────────────────────────
    tool_calls.append({
        "tool": "check_resource_availability",
        "args": {
            "resource_id": target_res.id,
            "date": valid_date.isoformat(),
            "start_time": valid_start.isoformat(),
            "end_time": valid_end.isoformat(),
        },
    })

    avail_info = check_resource_availability_data(
        db=db,
        resource_id=target_res.id,
        date=valid_date,
        start_time=valid_start,
        end_time=valid_end,
    )

    # If UNAVAILABLE: Explain conflicts honestly and suggest alternatives
    if not avail_info.get("available"):
        conflicts = avail_info.get("conflicts", [])
        has_active_lock = any(c.get("conflict_type") == "ACTIVE_BOOKING_LOCK" for c in conflicts)

        alt_items = []
        for alt in avail_info.get("alternatives", []):
            alt_items.append(
                f"- {alt['name']} (#{alt['id']}) - Location: {alt.get('location', 'N/A')}, Capacity: {alt.get('capacity', 'N/A')} seats"
            )

        if has_active_lock:
            lock_conflict = next(c for c in conflicts if c.get("conflict_type") == "ACTIVE_BOOKING_LOCK")
            reply = lock_conflict["description"]
            if alt_items:
                reply += "\n\nAvailable alternatives:\n" + "\n".join(alt_items)

            return {
                "intent": "RESOURCE_AVAILABILITY",
                "selected_agent": "resource_agent",
                "action_type": "RESOURCE_UNAVAILABLE",
                "final_response": sanitize_plain_english(reply),
                "tool_calls": tool_calls,
                "sources": ["Resource Allocation Engine", "Published Timetable"],
                "success": True,
            }

        conflict_items = "\n".join(f"- {c['description']}" for c in conflicts)
        reply = (
            f"Facility Unavailable: Conflict Detected\n\n"
            f"{target_res.name} cannot be booked on {valid_date.isoformat()} from {valid_start.strftime('%H:%M')} to {valid_end.strftime('%H:%M')}:\n\n"
            f"{conflict_items}\n\n"
        )
        if alt_items:
            reply += "Available alternatives:\n" + "\n".join(alt_items)
        else:
            reply += "No matching alternative resources of the same type are free during this exact interval. Consider choosing another time window."

        return {
            "intent": "RESOURCE_AVAILABILITY",
            "selected_agent": "resource_agent",
            "action_type": "RESOURCE_UNAVAILABLE",
            "final_response": sanitize_plain_english(reply),
            "tool_calls": tool_calls,
            "sources": ["Resource Allocation Engine", "Published Timetable"],
            "success": True,
        }

    is_pure_check = (
        any(k in msg_lower for k in ["is it free", "is it available", "check availability", "check if", "can i use", "availability"])
        or bool(re.search(r"\bis\b.+\b(?:available|free)\b", msg_lower))
    ) and not any(k in msg_lower for k in ["book", "reserve", "schedule a booking"])

    if is_pure_check:
        reply = (
            f"Facility is available.\n\n"
            f"{target_res.name} ({target_res.resource_type}) is available on {valid_date.isoformat()} "
            f"from {valid_start.strftime('%H:%M')} to {valid_end.strftime('%H:%M')} with zero conflicts.\n\n"
            f"- Location: {target_res.location or 'Main Campus'}\n"
            f"- Capacity: {target_res.capacity or 'Standard'} seats\n\n"
            f"To book this facility, ask:\n"
            f"Book {target_res.name} on {valid_date.isoformat()} from {valid_start.strftime('%H:%M')} to {valid_end.strftime('%H:%M')} for [Your Purpose]."
        )
        return {
            "intent": "RESOURCE_AVAILABILITY",
            "selected_agent": "resource_agent",
            "action_type": "AVAILABILITY_CONFIRMED",
            "final_response": sanitize_plain_english(reply),
            "tool_calls": tool_calls,
            "sources": ["Resource Allocation Engine", "Published Timetable"],
            "success": True,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 11. Create Booking Proposal (Explicit Confirmation Step)
    # ──────────────────────────────────────────────────────────────────────────
    purpose = res_details.get("purpose") or "Academic Event / Session"

    proposal = resource_proposal_store.create_proposal(
        user_id=user.id,
        role=user.role,
        resource_id=target_res.id,
        resource_name=target_res.name or f"Resource #{target_res.id}",
        resource_type=target_res.resource_type or "EQUIPMENT",
        location=target_res.location,
        capacity=target_res.capacity,
        date=valid_date.isoformat(),
        start_time=valid_start.isoformat(),
        end_time=valid_end.isoformat(),
        purpose=purpose,
    )

    reply = (
        f"Resource Booking Proposal ({proposal.proposal_id})\n\n"
        f"Facility Details:\n"
        f"- Resource: {proposal.resource_name} ({proposal.resource_type})\n"
        f"- Location: {proposal.location or 'Main Campus'}\n"
        f"- Capacity: {proposal.capacity or 'Standard'} seats\n"
        f"- Date: {proposal.date}\n"
        f"- Time Interval: {proposal.start_time[:5]} - {proposal.end_time[:5]}\n"
        f"- Purpose: {proposal.purpose}\n\n"
        f"Availability Pre-Check: Passed (0 conflicts with approved bookings or published timetables).\n\n"
        f"User Confirmation Required:\n"
        f"Submitting this proposal will register a verified PENDING booking request under your account ({user.email}).\n\n"
        f"To finalize this booking, click Confirm & Submit Booking below or type:\n"
        f"confirm {proposal.proposal_id}"
    )

    return {
        "intent": "RESOURCE_PROPOSAL",
        "selected_agent": "resource_agent",
        "action_type": "PROPOSAL_CREATED",
        "final_response": sanitize_plain_english(reply),
        "proposal": proposal.model_dump(),
        "tool_calls": tool_calls,
        "sources": sources,
        "success": True,
    }
