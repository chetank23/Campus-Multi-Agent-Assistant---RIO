import os
import sys

# Ensure backend can be imported
sys.path.insert(0, os.getcwd())

from backend.database import SessionLocal
from backend.models.identity import User
from backend.models.workflow import AuditLog, Notification
from backend.services.settings_service import execute_data_clear, get_data_management_summary, preview_data_clear
from backend.routes.analytics import get_analytics_overview, get_department_progress
from backend.routes.timetable import get_versions
from fastapi import Response

def run_tests():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.role == "ADMIN").first()
        assert admin is not None, "Admin user not found in database!"
        print(f"Testing as Admin user: {admin.email} (ID #{admin.id})")

        # 1. Clean legacy stale audit logs from before this fix
        from sqlalchemy import text
        db.execute(text("DELETE FROM test_schema.audit_logs WHERE entity_type IN ('Timetable', 'TimetableVersion', 'TimetableEntry')"))
        db.commit()

        # 2. Test get_data_management_summary
        summary = get_data_management_summary(db)
        print("\n--- DATA MANAGEMENT SUMMARY ---")
        print(f"Total generated records: {summary.total_generated_records}")
        for c in summary.categories:
            print(f"  Category: {c.category_id}: {c.total_records} records across {len(c.tables)} tables")

        # 3. Test preview_data_clear
        preview = preview_data_clear(db, ["timetable", "resources", "faculty_ops", "other_ops", "notifications"], clear_all=True)
        print("\n--- PREVIEW DATA CLEAR ---")
        print(f"Total to delete: {preview.total_records_to_delete}")
        print(f"Safe to execute: {preview.safe_to_execute}")
        print(f"Master records protected: {preview.master_records_protected}")

        # 4. Test execute_data_clear
        print("\n--- EXECUTING DATA CLEAR ---")
        exec_res = execute_data_clear(db, ["timetable", "resources", "faculty_ops", "other_ops", "notifications"], clear_all=True, user=admin)
        print(f"Clear Result: success={exec_res.success}, total_deleted={exec_res.total_records_deleted}, audit_id={exec_res.audit_log_id}")

        # 5. Verify Notifications Broadcast
        notifs = db.query(Notification).filter(Notification.type == "ANNOUNCEMENT").all()
        print(f"\n--- BROADCAST NOTIFICATIONS ---")
        print(f"Total broadcast notifications in DB: {len(notifs)}")
        assert len(notifs) >= 70, f"Expected notifications for all active campus users, got {len(notifs)}"
        sample_notif = notifs[0]
        print(f"Sample Notification: Title='{sample_notif.title}'")
        print(f"Message='{sample_notif.message}'")

        # 6. Verify Analytics Overview
        resp = Response()
        overview = get_analytics_overview(resp, admin, db)
        print("\n--- ANALYTICS OVERVIEW ---")
        print(f"Cache-Control: {resp.headers.get('Cache-Control')}")
        print(f"People: Users={overview['people']['total_users']}, Students={overview['people']['total_students']}, Faculty={overview['people']['total_faculty']}")
        print(f"Infrastructure: Rooms={overview['infrastructure']['total_rooms']}, Labs={overview['infrastructure']['labs']}")
        print(f"Timetable versions: {overview['timetables']['total_versions']}, status={overview['timetables']['status_breakdown']}")
        assert overview["timetables"]["total_versions"] == 0, "Expected 0 timetable versions after clear!"
        assert overview["people"]["total_users"] == 72, "Master user accounts must be preserved!"
        assert overview["infrastructure"]["total_rooms"] == 225, "Master rooms must be preserved!"

        # 7. Verify Department Progress
        resp2 = Response()
        dept_prog = get_department_progress(resp2, admin, db)
        print("\n--- DEPARTMENT PROGRESS ---")
        print(f"Cache-Control: {resp2.headers.get('Cache-Control')}")
        for dp in dept_prog:
            print(f"  {dp['department_name']} ({dp['department_code']}): {dp['published_sections']}/{dp['total_sections']} published ({dp['completion_percentage']}%)")
            assert dp["published_sections"] == 0, f"Expected 0 published sections, got {dp['published_sections']}"
            assert dp["completion_percentage"] == 0, f"Expected 0% completion, got {dp['completion_percentage']}%"

        # 8. Verify Timetable Versions Endpoint
        resp3 = Response()
        versions = get_versions(None, resp3, db, admin)
        print("\n--- TIMETABLE VERSIONS ---")
        print(f"Total versions returned: {len(versions)}")
        assert len(versions) == 0, f"Expected 0 versions after clear, got {len(versions)}"

        # 9. Verify Recent Audit Logs
        audit_logs = db.query(AuditLog).order_by(AuditLog.id.desc()).all()
        print("\n--- AUDIT LOGS ---")
        print(f"Total audit logs: {len(audit_logs)}")
        for al in audit_logs:
            print(f"  Log #{al.id}: {al.action} (entity={al.entity_type} #{al.entity_id}) at {al.timestamp}")
        assert audit_logs[0].action == "CLEAR_GENERATED_OPERATIONAL_DATA", "Latest audit log must be CLEAR_GENERATED_OPERATIONAL_DATA!"
        assert not any(al.entity_type in ('Timetable', 'TimetableVersion', 'TimetableEntry') for al in audit_logs), "No stale timetable audit logs should remain!"

        print("\n ALL VERIFICATION CHECKS PASSED SUCCESSFULLY!")

    finally:
        db.close()

if __name__ == "__main__":
    run_tests()

