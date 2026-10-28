"""
backend/services/notification_service.py
----------------------------------------
Authoritative notification service for RIO-MJP.
Handles:
  1. Authoritative recipient resolution from database relationships.
  2. Transactional persistence and PostgreSQL storage.
  3. Idempotent event deduplication.
  4. Real-time in-memory event dispatch (SSE broker).
  5. Recipient privacy and authorization enforcement.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session

from backend.models.academic import Department, Faculty, Program, Section, Student
from backend.models.courses import Course, CourseAssignment
from backend.models.identity import User
from backend.models.resources import Resource, ResourceBooking
from backend.models.timetable import TimetableEntry, TimetableVersion
from backend.models.workflow import Notification, NotificationOutbox
from backend.utils.datetime_utils import utc_now


# ── In-Memory SSE Stream Broker ───────────────────────────────────────────────

class NotificationStreamBroker:
    """
    Manages active SSE client subscriber queues per user_id.
    Thread-safe and asyncio-compatible.
    """
    def __init__(self) -> None:
        self._subscribers: Dict[int, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, user_id: int) -> asyncio.Queue:
        async with self._lock:
            queue: asyncio.Queue = asyncio.Queue()
            if user_id not in self._subscribers:
                self._subscribers[user_id] = set()
            self._subscribers[user_id].add(queue)
            return queue

    async def unsubscribe(self, user_id: int, queue: asyncio.Queue) -> None:
        async with self._lock:
            if user_id in self._subscribers:
                self._subscribers[user_id].discard(queue)
                if not self._subscribers[user_id]:
                    del self._subscribers[user_id]

    def publish_notification(self, user_id: int, notification: Notification) -> None:
        """
        Dispatches a notification payload to all active listener queues for the given user.
        Non-blocking: skips if no event loop or no connected subscribers.
        """
        if user_id not in self._subscribers or not self._subscribers[user_id]:
            return

        payload = {
            "id": notification.id,
            "user_id": notification.user_id,
            "title": notification.title,
            "message": notification.message,
            "type": notification.type,
            "link": notification.link,
            "entity_type": notification.entity_type,
            "entity_id": notification.entity_id,
            "is_read": notification.is_read,
            "created_at": notification.created_at.isoformat() if notification.created_at else None,
        }

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # No running event loop in this thread

        for queue in list(self._subscribers.get(user_id, set())):
            try:
                queue.put_nowait(payload)
            except Exception:
                loop.call_soon_threadsafe(queue.put_nowait, payload)


# Global singleton broker instance
stream_broker = NotificationStreamBroker()


# ── Core Creation & Persistence ───────────────────────────────────────────────

def create_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    type: str,
    link: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    dedupe: bool = False,
) -> Optional[Notification]:
    """
    Persists a single notification to PostgreSQL with optional deduplication.
    """
    if dedupe and entity_type and entity_id:
        existing = (
            db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.entity_type == entity_type,
                Notification.entity_id == entity_id,
                Notification.type == type,
            )
            .first()
        )
        if existing:
            return existing

    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type,
        link=link,
        entity_type=entity_type,
        entity_id=entity_id,
        is_read=False,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    stream_broker.publish_notification(user_id, notif)
    return notif


def create_bulk_notifications(
    db: Session,
    notifications: List[Notification],
    channel: str = "SSE",
) -> List[Notification]:
    """
    Bulk persists notifications within a single database transaction,
    generating transactional NotificationOutbox records for durable delivery.
    """
    if not notifications:
        return []

    db.add_all(notifications)
    db.flush()

    outbox_entries: List[NotificationOutbox] = []
    for notif in notifications:
        if notif.user_id:
            outbox = NotificationOutbox(
                notification_id=notif.id,
                user_id=notif.user_id,
                channel=channel,
                status="PENDING",
                payload={
                    "id": notif.id,
                    "title": notif.title,
                    "message": notif.message,
                    "type": notif.type,
                    "link": notif.link,
                    "entity_type": notif.entity_type,
                    "entity_id": notif.entity_id,
                },
                created_at=utc_now(),
            )
            outbox_entries.append(outbox)

    if outbox_entries:
        db.add_all(outbox_entries)
    db.commit()

    for notif in notifications:
        db.refresh(notif)
        if notif.user_id:
            try:
                stream_broker.publish_notification(notif.user_id, notif)
            except Exception:
                pass

    for outbox in outbox_entries:
        try:
            db.refresh(outbox)
            outbox.status = "SENT"
            outbox.sent_at = utc_now()
            outbox.last_attempt_at = utc_now()
        except Exception as exc:
            outbox.status = "FAILED"
            outbox.last_error = str(exc)
            outbox.last_attempt_at = utc_now()
            outbox.retry_count += 1
    db.commit()

    return notifications


# ── Timetable Publication Lifecycle Event ─────────────────────────────────────

def notify_timetable_published(
    db: Session,
    version_id: int,
) -> Dict[str, Any]:
    """
    Authoritative event handler for Timetable Publication (Priority 1).
    1. Verifies timetable status is strictly PUBLISHED.
    2. Resolves affected faculty and enrolled students from database relations.
    3. Guarantees deduplication: retries do not re-broadcast.
    4. Guarantees safety: unassociated departments/sections receive nothing.
    """
    version = db.query(TimetableVersion).filter(TimetableVersion.id == version_id).first()
    if not version:
        return {"success": False, "error": f"TimetableVersion #{version_id} not found."}

    if version.status != "PUBLISHED":
        return {
            "success": False,
            "error": (
                f"Cannot dispatch publication notifications: TimetableVersion #{version_id} "
                f"status is '{version.status}', not 'PUBLISHED'."
            ),
        }

    # Deduplication check: Has this publication event already been delivered?
    existing = (
        db.query(Notification)
        .filter(
            Notification.entity_type == "TimetableVersion",
            Notification.entity_id == version_id,
            Notification.type == "TIMETABLE_PUBLISHED",
        )
        .first()
    )
    if existing:
        return {
            "success": True,
            "deduplicated": True,
            "message": f"Notifications for TimetableVersion #{version_id} publication have already been dispatched.",
            "faculty_notified": 0,
            "students_notified": 0,
            "admins_notified": 0,
            "total_notified": 0,
        }

    # Query active entries for this version
    entries = (
        db.query(TimetableEntry)
        .filter(
            TimetableEntry.version_id == version_id,
            TimetableEntry.status != "CANCELLED",
        )
        .all()
    )

    if not entries:
        return {
            "success": False,
            "error": f"Cannot resolve recipients: TimetableVersion #{version_id} contains no active entries.",
            "faculty_notified": 0,
            "students_notified": 0,
            "admins_notified": 0,
            "total_notified": 0,
        }

    faculty_pks = {e.faculty_id for e in entries if e.faculty_id is not None}
    section_pks = {e.section_id for e in entries if e.section_id is not None}

    if not faculty_pks and not section_pks:
        return {
            "success": False,
            "error": f"Cannot resolve recipients: TimetableVersion #{version_id} has no assigned faculty or sections.",
            "faculty_notified": 0,
            "students_notified": 0,
            "admins_notified": 0,
            "total_notified": 0,
        }

    # Resolve Faculty recipients
    faculty_user_ids: Set[int] = set()
    if faculty_pks:
        fac_rows = (
            db.query(Faculty.user_id)
            .filter(
                Faculty.id.in_(faculty_pks),
                Faculty.user_id.isnot(None),
            )
            .all()
        )
        faculty_user_ids = {uid for (uid,) in fac_rows if uid}

    # Resolve Student recipients (strictly enrolled in the published sections)
    student_user_ids: Set[int] = set()
    if section_pks:
        stud_rows = (
            db.query(Student.user_id)
            .filter(
                Student.section_id.in_(section_pks),
                Student.user_id.isnot(None),
            )
            .all()
        )
        student_user_ids = {uid for (uid,) in stud_rows if uid}

    ver_num = version.version_number or str(version.id)
    notifications_to_add: List[Notification] = []

    # Notify Faculty
    for f_uid in faculty_user_ids:
        notifications_to_add.append(
            Notification(
                user_id=f_uid,
                title=f"Timetable Published: Version v{ver_num}",
                message=f"An official timetable (v{ver_num}) has been published. Your teaching schedule is now live and active.",
                type="TIMETABLE_PUBLISHED",
                link="/faculty/timetable",
                entity_type="TimetableVersion",
                entity_id=version.id,
                is_read=False,
            )
        )

    # Notify Students
    for s_uid in student_user_ids:
        notifications_to_add.append(
            Notification(
                user_id=s_uid,
                title=f"Timetable Published: Version v{ver_num}",
                message=f"Your class timetable (v{ver_num}) has been officially published and is now active.",
                type="TIMETABLE_PUBLISHED",
                link="/student/timetable",
                entity_type="TimetableVersion",
                entity_id=version.id,
                is_read=False,
            )
        )

    # Notify Admins
    admin_rows = db.query(User.id).filter(User.role == "ADMIN", User.is_active == True).all()
    admin_uids = {uid for (uid,) in admin_rows if uid}
    for a_uid in admin_uids:
        notifications_to_add.append(
            Notification(
                user_id=a_uid,
                title=f"Timetable v{ver_num} Published",
                message=(
                    f"Timetable version v{ver_num} published successfully across {len(section_pks)} section(s) "
                    f"({len(faculty_user_ids)} faculty, {len(student_user_ids)} students notified)."
                ),
                type="TIMETABLE_PUBLISHED",
                link=f"/admin/timetable/versions/{version.id}",
                entity_type="TimetableVersion",
                entity_id=version.id,
                is_read=False,
            )
        )

    created = create_bulk_notifications(db, notifications_to_add)

    return {
        "success": True,
        "version_id": version.id,
        "faculty_notified": len(faculty_user_ids),
        "students_notified": len(student_user_ids),
        "admins_notified": len(admin_uids),
        "total_notified": len(created),
    }


def notify_timetable_rescheduled(
    db: Session,
    old_version_id: int,
    new_version_id: int,
    diff_items: List[Dict[str, Any]],
    reason: str,
) -> Dict[str, Any]:
    """
    Authoritative event handler for Timetable Rescheduling Publication.
    1. Resolves affected courses, sections, faculty, and student batches strictly from diff_items.
    2. Enforces targeted delivery: unaffected students and faculty receive ZERO notifications.
    3. Guarantees deduplication across retries.
    4. Transactionally creates Notification records and NotificationOutbox entries.
    5. Dispatches real-time SSE alerts via stream_broker.
    """
    # 1. Deduplication check
    existing = (
        db.query(Notification)
        .filter(
            Notification.entity_type == "TimetableVersion",
            Notification.entity_id == new_version_id,
            Notification.type == "TIMETABLE_RESCHEDULED",
        )
        .first()
    )
    if existing:
        return {
            "success": True,
            "deduplicated": True,
            "message": f"Notifications for rescheduled TimetableVersion #{new_version_id} have already been dispatched.",
            "faculty_notified": 0,
            "students_notified": 0,
            "admins_notified": 0,
            "total_notified": 0,
            "outbox_entries": 0,
        }

    new_version = db.query(TimetableVersion).filter(TimetableVersion.id == new_version_id).first()
    new_v_num = new_version.version_number if new_version else str(new_version_id)

    # 2. Extract affected assignment IDs
    affected_ca_ids = set()
    for d in diff_items:
        ca_id = d.get("course_assignment_id")
        if ca_id:
            affected_ca_ids.add(ca_id)

    if not affected_ca_ids and not diff_items:
        return {
            "success": True,
            "message": "No diff items provided; 0 recipients affected.",
            "faculty_notified": 0,
            "students_notified": 0,
            "admins_notified": 0,
            "total_notified": 0,
            "outbox_entries": 0,
        }

    # Fetch CourseAssignment details for affected assignments
    cas = db.query(CourseAssignment).filter(CourseAssignment.id.in_(affected_ca_ids)).all() if affected_ca_ids else []
    affected_faculty_pks = {ca.faculty_id for ca in cas if ca.faculty_id}
    affected_section_pks = {ca.section_id for ca in cas if ca.section_id}
    affected_batch_pks = {ca.batch_id for ca in cas if ca.batch_id}

    # Resolve Faculty recipients
    faculty_user_ids: Set[int] = set()
    if affected_faculty_pks:
        fac_rows = db.query(Faculty.user_id).filter(Faculty.id.in_(affected_faculty_pks), Faculty.user_id.isnot(None)).all()
        faculty_user_ids = {uid for (uid,) in fac_rows if uid}

    # Resolve Student recipients (strictly enrolled in affected sections or batches)
    student_user_ids: Set[int] = set()
    if affected_section_pks:
        sec_studs = db.query(Student.user_id).filter(Student.section_id.in_(affected_section_pks), Student.user_id.isnot(None)).all()
        student_user_ids.update(uid for (uid,) in sec_studs if uid)
    if affected_batch_pks:
        batch_studs = db.query(Student.user_id).filter(Student.batch_id.in_(affected_batch_pks), Student.user_id.isnot(None)).all()
        student_user_ids.update(uid for (uid,) in batch_studs if uid)

    # Map diff details for nice human-readable formatting
    diff_summary_lines = []
    for d in diff_items:
        c_code = d.get("course_code", "Course")
        old_loc = f"{d.get('old_slot_label', '')} ({d.get('old_room_number', '')})"
        new_loc = f"{d.get('new_slot_label', '')} ({d.get('new_room_number', '')})"
        diff_summary_lines.append(f"{c_code}: {old_loc} -> {new_loc}")
    diff_text = "; ".join(diff_summary_lines[:3])
    if len(diff_summary_lines) > 3:
        diff_text += f"; (+{len(diff_summary_lines) - 3} more)"

    notifications_to_add: List[Notification] = []

    # Targeted Faculty Notifications
    for f_uid in faculty_user_ids:
        notifications_to_add.append(
            Notification(
                user_id=f_uid,
                title=f"Schedule Rescheduled: Timetable {new_v_num}",
                message=(
                    f"Your teaching schedule has been adjusted due to: {reason}.\n"
                    f"Updates: {diff_text}\n"
                    f"Authoritative Timetable Revision: #{new_version_id} ({new_v_num})."
                ),
                type="TIMETABLE_RESCHEDULED",
                link="/faculty/timetable",
                entity_type="TimetableVersion",
                entity_id=new_version_id,
                is_read=False,
            )
        )

    # Targeted Student Notifications
    for s_uid in student_user_ids:
        notifications_to_add.append(
            Notification(
                user_id=s_uid,
                title=f"Class Rescheduled: Timetable {new_v_num}",
                message=(
                    f"One or more of your classes have been rescheduled due to: {reason}.\n"
                    f"Updates: {diff_text}\n"
                    f"Authoritative Timetable Revision: #{new_version_id} ({new_v_num})."
                ),
                type="TIMETABLE_RESCHEDULED",
                link="/student/timetable",
                entity_type="TimetableVersion",
                entity_id=new_version_id,
                is_read=False,
            )
        )

    # Targeted Admin Notifications
    admin_rows = db.query(User.id).filter(User.role == "ADMIN", User.is_active == True).all()
    admin_uids = {uid for (uid,) in admin_rows if uid}
    for a_uid in admin_uids:
        notifications_to_add.append(
            Notification(
                user_id=a_uid,
                title=f"Timetable Revision {new_v_num} Published",
                message=(
                    f"Timetable #{new_version_id} ({new_v_num}) published to replace #{old_version_id} after disruption: {reason}. "
                    f"{len(diff_items)} session(s) moved ({len(faculty_user_ids)} faculty, {len(student_user_ids)} students notified)."
                ),
                type="TIMETABLE_RESCHEDULED",
                link=f"/admin/timetable/versions/{new_version_id}",
                entity_type="TimetableVersion",
                entity_id=new_version_id,
                is_read=False,
            )
        )

    created = create_bulk_notifications(db, notifications_to_add)

    return {
        "success": True,
        "old_version_id": old_version_id,
        "new_version_id": new_version_id,
        "faculty_notified": len(faculty_user_ids),
        "students_notified": len(student_user_ids),
        "admins_notified": len(admin_uids),
        "total_notified": len(created),
        "outbox_entries": len(created),
    }


def process_notification_outbox(
    db: Session,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Processes pending or retryable notification outbox entries,
    dispatching them to the stream broker or marking them failed/dead-letter.
    """
    outbox_records = (
        db.query(NotificationOutbox)
        .filter(
            NotificationOutbox.status.in_(["PENDING", "FAILED"]),
            NotificationOutbox.retry_count < NotificationOutbox.max_retries,
        )
        .limit(limit)
        .all()
    )

    processed = 0
    delivered = 0
    failed = 0

    for item in outbox_records:
        processed += 1
        item.last_attempt_at = utc_now()
        item.retry_count += 1
        try:
            notif = db.query(Notification).filter(Notification.id == item.notification_id).first()
            if notif and notif.user_id:
                stream_broker.publish_notification(notif.user_id, notif)
            item.status = "SENT"
            item.sent_at = utc_now()
            delivered += 1
        except Exception as exc:
            failed += 1
            item.last_error = str(exc)
            if item.retry_count >= item.max_retries:
                item.status = "DEAD_LETTER"
            else:
                item.status = "FAILED"

    db.commit()
    return {
        "processed_count": processed,
        "delivered_count": delivered,
        "failed_count": failed,
    }


# ── Resource Booking Lifecycle Events ─────────────────────────────────────────

def notify_booking_submitted(
    db: Session,
    booking_id: int,
) -> None:
    """
    Triggered when a resource booking request is created (PENDING).
    1. Notifies the requester that their submission is under review.
    2. Notifies all campus administrators to review the pending request.
    """
    booking = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
    if not booking or not booking.requested_by:
        return

    # Deduplication
    existing = (
        db.query(Notification)
        .filter(
            Notification.entity_type == "ResourceBooking",
            Notification.entity_id == booking_id,
            Notification.type == "BOOKING_SUBMITTED",
        )
        .first()
    )
    if existing:
        return

    resource = db.query(Resource).filter(Resource.id == booking.resource_id).first()
    requester = db.query(User).filter(User.id == booking.requested_by).first()

    res_name = resource.name if resource else f"Resource #{booking.resource_id}"
    req_name = requester.name if requester else f"User #{booking.requested_by}"
    time_str = f"{booking.start_time.strftime('%H:%M')} - {booking.end_time.strftime('%H:%M')}" if booking.start_time and booking.end_time else ""

    notifications: List[Notification] = []

    # Requester notification
    notifications.append(
        Notification(
            user_id=booking.requested_by,
            title=f"Booking Request Submitted: {res_name}",
            message=f"Your booking request #{booking.id} for {res_name} on {booking.date} ({time_str}) is pending administrator review.",
            type="BOOKING_SUBMITTED",
            link="/resources",
            entity_type="ResourceBooking",
            entity_id=booking.id,
            is_read=False,
        )
    )

    # Admin review notification
    admins = db.query(User).filter(User.role == "ADMIN", User.is_active == True).all()
    for admin in admins:
        notifications.append(
            Notification(
                user_id=admin.id,
                title=f"New Booking Request #{booking.id}: {res_name}",
                message=f"{req_name} requested {res_name} on {booking.date} ({time_str}). Review pending.",
                type="BOOKING_PENDING_REVIEW",
                link="/admin/resources",
                entity_type="ResourceBooking",
                entity_id=booking.id,
                is_read=False,
            )
        )

    create_bulk_notifications(db, notifications)


def notify_booking_approved(
    db: Session,
    booking_id: int,
) -> None:
    """
    Triggered when an administrator approves a booking request.
    Notifies the requester that their reservation is confirmed.
    """
    booking = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
    if not booking or not booking.requested_by:
        return

    existing = (
        db.query(Notification)
        .filter(
            Notification.user_id == booking.requested_by,
            Notification.entity_type == "ResourceBooking",
            Notification.entity_id == booking_id,
            Notification.type == "BOOKING_APPROVED",
        )
        .first()
    )
    if existing:
        return

    resource = db.query(Resource).filter(Resource.id == booking.resource_id).first()
    res_name = resource.name if resource else f"Resource #{booking.resource_id}"
    time_str = f"{booking.start_time.strftime('%H:%M')} - {booking.end_time.strftime('%H:%M')}" if booking.start_time and booking.end_time else ""

    create_notification(
        db=db,
        user_id=booking.requested_by,
        title=f"Booking Approved: {res_name}",
        message=f"Your booking request #{booking.id} for {res_name} on {booking.date} ({time_str}) has been approved.",
        type="BOOKING_APPROVED",
        link="/resources",
        entity_type="ResourceBooking",
        entity_id=booking.id,
        dedupe=True,
    )


def notify_booking_rejected(
    db: Session,
    booking_id: int,
    reason: Optional[str] = None,
) -> None:
    """
    Triggered when an administrator rejects a booking request.
    Notifies the requester with the administrative justification.
    """
    booking = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
    if not booking or not booking.requested_by:
        return

    existing = (
        db.query(Notification)
        .filter(
            Notification.user_id == booking.requested_by,
            Notification.entity_type == "ResourceBooking",
            Notification.entity_id == booking_id,
            Notification.type == "BOOKING_REJECTED",
        )
        .first()
    )
    if existing:
        return

    resource = db.query(Resource).filter(Resource.id == booking.resource_id).first()
    res_name = resource.name if resource else f"Resource #{booking.resource_id}"
    reason_text = f" Reason: {reason}" if reason else ""

    create_notification(
        db=db,
        user_id=booking.requested_by,
        title=f"Booking Rejected: {res_name}",
        message=f"Your booking request #{booking.id} for {res_name} on {booking.date} was rejected.{reason_text}",
        type="BOOKING_REJECTED",
        link="/resources",
        entity_type="ResourceBooking",
        entity_id=booking.id,
        dedupe=True,
    )


def notify_booking_cancelled(
    db: Session,
    booking_id: int,
    cancelled_by_user_id: int,
    reason: Optional[str] = None,
) -> None:
    """
    Triggered when a booking is cancelled.
    - If cancelled by the requester: confirms to requester and alerts admins.
    - If cancelled by an admin: notifies the requester of administrative cancellation.
    """
    booking = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
    if not booking or not booking.requested_by:
        return

    resource = db.query(Resource).filter(Resource.id == booking.resource_id).first()
    res_name = resource.name if resource else f"Resource #{booking.resource_id}"
    canceller = db.query(User).filter(User.id == cancelled_by_user_id).first()
    canceller_name = canceller.name if canceller else f"User #{cancelled_by_user_id}"
    reason_text = f" Reason: {reason}" if reason else ""

    notifications: List[Notification] = []

    if cancelled_by_user_id == booking.requested_by:
        # Requester cancelled their own booking
        notifications.append(
            Notification(
                user_id=booking.requested_by,
                title=f"Booking Cancelled: {res_name}",
                message=f"Your booking #{booking.id} for {res_name} on {booking.date} has been cancelled.",
                type="BOOKING_CANCELLED",
                link="/resources",
                entity_type="ResourceBooking",
                entity_id=booking.id,
                is_read=False,
            )
        )
        # Notify admins
        admins = db.query(User).filter(User.role == "ADMIN", User.is_active == True).all()
        for admin in admins:
            notifications.append(
                Notification(
                    user_id=admin.id,
                    title=f"Booking Cancelled #{booking.id}: {res_name}",
                    message=f"Booking #{booking.id} for {res_name} on {booking.date} was cancelled by {canceller_name}.{reason_text}",
                    type="BOOKING_CANCELLED",
                    link="/admin/resources",
                    entity_type="ResourceBooking",
                    entity_id=booking.id,
                    is_read=False,
                )
            )
    else:
        # Admin cancelled user's booking
        notifications.append(
            Notification(
                user_id=booking.requested_by,
                title=f"Booking Cancelled: {res_name}",
                message=f"Your booking #{booking.id} for {res_name} on {booking.date} was cancelled by administration.{reason_text}",
                type="BOOKING_CANCELLED",
                link="/resources",
                entity_type="ResourceBooking",
                entity_id=booking.id,
                is_read=False,
            )
        )

    create_bulk_notifications(db, notifications)


# ── Faculty-to-Students Class Updates ─────────────────────────────────────────

def notify_faculty_class_update(
    db: Session,
    faculty_user_id: int,
    course_id: int,
    section_id: int,
    update_type: str,
    title: str,
    message: str,
) -> Tuple[bool, str, int]:
    """
    Allows a faculty member to notify students in a section they teach.
    Enforces authorization: faculty must be assigned to course_id and section_id
    via CourseAssignment or be the Section's class teacher.
    """
    faculty = db.query(Faculty).filter(Faculty.user_id == faculty_user_id).first()
    if not faculty:
        return False, "Authenticated user is not registered as faculty.", 0

    section = db.query(Section).filter(Section.id == section_id).first()
    if not section:
        return False, f"Section #{section_id} not found.", 0

    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        return False, f"Course #{course_id} not found.", 0

    # Authorization verification: CourseAssignment check
    assignment = (
        db.query(CourseAssignment)
        .filter(
            CourseAssignment.course_id == course_id,
            CourseAssignment.faculty_id == faculty.id,
            CourseAssignment.section_id == section_id,
        )
        .first()
    )
    is_class_teacher = section.class_teacher_id == faculty.id

    if not assignment and not is_class_teacher:
        return (
            False,
            f"Unauthorized: You are not assigned to course '{course.course_code}' in section '{section.section_name}'.",
            0,
        )

    # Authoritatively resolve enrolled students
    students = (
        db.query(Student)
        .filter(
            Student.section_id == section_id,
            Student.user_id.isnot(None),
        )
        .all()
    )

    if not students:
        return True, "Update recorded, but section contains no enrolled students.", 0

    notifications: List[Notification] = []
    notif_type = f"CLASS_{update_type.upper()}"

    for stud in students:
        if stud.user_id:
            notifications.append(
                Notification(
                    user_id=stud.user_id,
                    title=f"[{course.course_code}] {title}",
                    message=message,
                    type=notif_type,
                    link="/student/timetable",
                    entity_type="Course",
                    entity_id=course.id,
                    is_read=False,
                )
            )

    created = create_bulk_notifications(db, notifications)
    return True, f"Notification successfully delivered to {len(created)} student(s).", len(created)


# ── Administrative Targeted Broadcast ─────────────────────────────────────────

def broadcast_announcement(
    db: Session,
    admin_user_id: int,
    title: str,
    message: str,
    target_role: Optional[str] = "ALL",
    department_id: Optional[int] = None,
    program_id: Optional[int] = None,
    section_id: Optional[int] = None,
) -> Tuple[bool, str, int]:
    """
    Authoritative Administrative broadcast.
    Resolves recipients strictly from database relationships:
      - section_id: enrolled students in section (+ class teacher)
      - program_id: students in program
      - department_id: faculty & students in department
      - None (campus-wide): all active campus users
    """
    target_user_ids: Set[int] = set()

    if section_id:
        # Target section
        if target_role in ("ALL", "STUDENT"):
            studs = db.query(Student.user_id).filter(Student.section_id == section_id, Student.user_id.isnot(None)).all()
            target_user_ids.update(uid for (uid,) in studs if uid)
        if target_role in ("ALL", "FACULTY"):
            sec = db.query(Section).filter(Section.id == section_id).first()
            if sec and sec.class_teacher_id:
                ct = db.query(Faculty.user_id).filter(Faculty.id == sec.class_teacher_id, Faculty.user_id.isnot(None)).first()
                if ct and ct[0]:
                    target_user_ids.add(ct[0])
    elif program_id:
        # Target program
        if target_role in ("ALL", "STUDENT"):
            studs = db.query(Student.user_id).filter(Student.program_id == program_id, Student.user_id.isnot(None)).all()
            target_user_ids.update(uid for (uid,) in studs if uid)
        if target_role in ("ALL", "FACULTY"):
            prog = db.query(Program).filter(Program.id == program_id).first()
            if prog and prog.department_id:
                facs = db.query(Faculty.user_id).filter(Faculty.department_id == prog.department_id, Faculty.user_id.isnot(None)).all()
                target_user_ids.update(uid for (uid,) in facs if uid)
    elif department_id:
        # Target department
        if target_role in ("ALL", "FACULTY"):
            facs = db.query(Faculty.user_id).filter(Faculty.department_id == department_id, Faculty.user_id.isnot(None)).all()
            target_user_ids.update(uid for (uid,) in facs if uid)
        if target_role in ("ALL", "STUDENT"):
            studs = db.query(Student.user_id).filter(Student.department_id == department_id, Student.user_id.isnot(None)).all()
            target_user_ids.update(uid for (uid,) in studs if uid)
    else:
        # Campus-wide
        query = db.query(User.id).filter(User.is_active == True)
        if target_role and target_role != "ALL":
            query = query.filter(User.role == target_role)
        all_users = query.all()
        target_user_ids.update(uid for (uid,) in all_users if uid)

    if not target_user_ids:
        return True, "No active recipients matched the requested targeting criteria.", 0

    notifications: List[Notification] = []
    for uid in target_user_ids:
        notifications.append(
            Notification(
                user_id=uid,
                title=title,
                message=message,
                type="ANNOUNCEMENT",
                link="/admin/notifications",
                is_read=False,
            )
        )

    created = create_bulk_notifications(db, notifications)
    return True, f"Broadcast successfully delivered to {len(created)} recipient(s).", len(created)
