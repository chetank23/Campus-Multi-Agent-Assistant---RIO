"""
scripts/capture_modal_screenshots.py
------------------------------------
Captures pixel-accurate before/after screenshots of the two polished modal dialogs:
1. Faculty Modal: Report Absence & Request Substitution
2. Admin Modal: Review Substitution & Assign Faculty
"""

import os
import sys
import json
from playwright.sync_api import sync_playwright

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts_screenshots")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def capture_modals():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        # -------------------------------------------------------------
        # 1. FACULTY MODAL CAPTURE
        # -------------------------------------------------------------
        print("Setting up routes for Faculty modal...")
        
        # Mock auth endpoints for faculty
        page.route("**/api/auth/refresh", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"access_token": "mock-token", "token_type": "bearer"})
        ))
        page.route("**/api/auth/me", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "id": 10,
                "name": "Dr. Nimrita Koul",
                "email": "nimrita@campus.edu",
                "role": "FACULTY",
                "department_id": 1
            })
        ))

        # Mock faculty substitutions data
        mock_scheduled_classes = [
            {
                "timetable_entry_id": 101,
                "date": "2026-11-11",
                "day": "Wednesday",
                "start_time": "08:30",
                "end_time": "09:25",
                "course_code": "B22EH0704",
                "course_name": "Project – Phase 1",
                "room_number": "012",
                "section_name": "AIDS-A",
                "has_active_request": False
            }
        ]
        page.route("**/api/substitutions/my-classes*", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(mock_scheduled_classes)
        ))
        page.route("**/api/substitutions/my-requests*", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps([])
        ))
        page.route("**/api/substitutions/my-assignments*", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps([])
        ))

        print("Navigating to Faculty Substitutions page...")
        page.goto("http://localhost:5173/faculty/substitutions", wait_until="networkidle")
        page.wait_for_timeout(1000)

        # Click "Report Absence" button to open modal
        report_button = page.locator("button:has-text('Report Absence')").first
        if report_button.is_visible():
            report_button.click()
            page.wait_for_selector("[role='dialog']", timeout=5000)
            page.wait_for_timeout(500)
            
            # Take screenshot of the faculty modal
            modal_element = page.locator("[role='dialog'] > div")
            faculty_screenshot_path = os.path.join(OUTPUT_DIR, "faculty_modal_report_absence.png")
            modal_element.screenshot(path=faculty_screenshot_path)
            print(f"Captured Faculty Modal to: {faculty_screenshot_path}")
        else:
            print("Report Absence button not found on page.")

        # -------------------------------------------------------------
        # 2. ADMIN MODAL CAPTURE
        # -------------------------------------------------------------
        print("Setting up routes for Admin modal...")
        admin_page = context.new_page()

        admin_page.route("**/api/auth/refresh", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"access_token": "mock-token", "token_type": "bearer"})
        ))
        admin_page.route("**/api/auth/me", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "id": 1,
                "name": "Academic Administrator",
                "email": "admin@campus.edu",
                "role": "ADMIN",
                "department_id": 1
            })
        ))

        mock_pending_requests = [
            {
                "id": 55,
                "timetable_entry_id": 202,
                "substitution_date": "2026-11-10",
                "slot_day": "TUE",
                "start_time": "08:30",
                "end_time": "09:25",
                "original_faculty_id": 10,
                "original_faculty_name": "Dr. Nimrita Koul",
                "course_code": "B25CS0701",
                "course_name": "Principles of Federated Learning",
                "room_number": "807",
                "reason": "SICK",
                "status": "REQUESTED",
                "version": 1,
                "section_name": "AIDS-A"
            }
        ]
        admin_page.route("**/api/substitutions/pending*", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(mock_pending_requests)
        ))
        admin_page.route("**/api/substitutions/all*", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(mock_pending_requests)
        ))

        mock_candidates = {
            "request_id": 55,
            "evaluation_status": "NO_ELIGIBLE_CANDIDATE",
            "cannot_determine_reason": None,
            "candidates": [
                {
                    "faculty_id": 21,
                    "faculty_name": "Prof. Aarthy G",
                    "department_name": "AI & DS",
                    "designation": "Faculty Member",
                    "qualification_tier": "DIRECT_ASSIGNMENT",
                    "current_weekly_load": 0,
                    "max_weekly_load": 16,
                    "load_percentage": 0,
                    "is_eligible": False,
                    "ineligibility_reasons": ["Lacks verified qualification/assignment for course B25CS0701"],
                    "eligibility_breakdown": [
                        {"factor": "ACTIVE_STATUS", "status": "PASS", "detail": "Active faculty member"},
                        {"factor": "QUALIFICATION", "status": "FAIL", "detail": "Lacks verified qualification"},
                        {"factor": "TIMETABLE_CLASH", "status": "PASS", "detail": "No clash"},
                        {"factor": "AVAILABILITY", "status": "PASS", "detail": "Available"},
                        {"factor": "EXISTING_SUBSTITUTION", "status": "PASS", "detail": "No existing substitution"},
                        {"factor": "WORKLOAD_LIMIT", "status": "PASS", "detail": "Within workload limit"}
                    ]
                },
                {
                    "faculty_id": 22,
                    "faculty_name": "Prof. M. Jeevaa",
                    "department_name": "AI & DS",
                    "designation": "Faculty Member",
                    "qualification_tier": "DIRECT_ASSIGNMENT",
                    "current_weekly_load": 0,
                    "max_weekly_load": 16,
                    "load_percentage": 0,
                    "is_eligible": False,
                    "ineligibility_reasons": ["Lacks verified qualification/assignment for course B25CS0701"],
                    "eligibility_breakdown": [
                        {"factor": "ACTIVE_STATUS", "status": "PASS", "detail": "Active faculty member"},
                        {"factor": "QUALIFICATION", "status": "FAIL", "detail": "Lacks verified qualification"},
                        {"factor": "TIMETABLE_CLASH", "status": "PASS", "detail": "No clash"},
                        {"factor": "AVAILABILITY", "status": "PASS", "detail": "Available"},
                        {"factor": "EXISTING_SUBSTITUTION", "status": "PASS", "detail": "No existing substitution"},
                        {"factor": "WORKLOAD_LIMIT", "status": "PASS", "detail": "Within workload limit"}
                    ]
                },
                {
                    "faculty_id": 23,
                    "faculty_name": "Dr. Chatrapathy K",
                    "department_name": "AI & DS",
                    "designation": "Faculty Member",
                    "qualification_tier": "DIRECT_ASSIGNMENT",
                    "current_weekly_load": 0,
                    "max_weekly_load": 16,
                    "load_percentage": 0,
                    "is_eligible": False,
                    "ineligibility_reasons": ["Lacks verified qualification/assignment for course B25CS0701"],
                    "eligibility_breakdown": [
                        {"factor": "ACTIVE_STATUS", "status": "PASS", "detail": "Active faculty member"},
                        {"factor": "QUALIFICATION", "status": "FAIL", "detail": "Lacks verified qualification"},
                        {"factor": "TIMETABLE_CLASH", "status": "PASS", "detail": "No clash"}
                    ]
                }
            ]
        }
        admin_page.route("**/api/substitutions/requests/*/candidates*", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(mock_candidates)
        ))

        print("Navigating to Admin Substitutions page...")
        admin_page.goto("http://localhost:5173/admin/substitutions", wait_until="networkidle")
        admin_page.wait_for_timeout(1000)

        # Click "Review & Assign" on the row
        review_button = admin_page.locator("button:has-text('Review & Assign')").first
        if review_button.is_visible():
            review_button.click()
            admin_page.wait_for_selector("[role='dialog']", timeout=5000)
            admin_page.wait_for_timeout(800)

            # Take screenshot of the admin modal
            modal_element = admin_page.locator("[role='dialog'] > div")
            admin_screenshot_path = os.path.join(OUTPUT_DIR, "admin_modal_review_substitution.png")
            modal_element.screenshot(path=admin_screenshot_path)
            print(f"Captured Admin Modal to: {admin_screenshot_path}")
        else:
            print("Review & Assign button not found on page.")

        browser.close()

if __name__ == "__main__":
    capture_modals()
