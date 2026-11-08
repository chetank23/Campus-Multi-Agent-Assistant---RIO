"""
scripts/standardize_time_slots.py
---------------------------------
Cleans up and standardizes the time_slots table in campus_ai_test:
1. Deletes legacy/dummy time slots (e.g. old 09:00-17:00 slots) that conflict with the
   official institution 9-period schedule (08:30-16:15).
2. Ensures exactly 54 canonical time slots exist (6 days: MON..SAT x 9 periods: P1..P7 + 2 breaks).
3. Standardizes day representation to canonical 3-letter uppercase codes:
   MON, TUE, WED, THU, FRI, SAT.
4. Re-points any existing TimetableEntry and FacultyAvailability records to the canonical slots.
"""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path
from typing import Dict, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text
from backend.database import SessionLocal
from backend.models.space_time import TimeSlot, FacultyAvailability
from backend.models.timetable import TimetableEntry

CANONICAL_PERIODS = [
    ("P1", datetime.time(8, 30), datetime.time(9, 25), "CLASS"),
    ("P2", datetime.time(9, 25), datetime.time(10, 20), "CLASS"),
    ("TEA BREAK", datetime.time(10, 20), datetime.time(10, 40), "BREAK"),
    ("P3", datetime.time(10, 40), datetime.time(11, 35), "CLASS"),
    ("P4", datetime.time(11, 35), datetime.time(12, 30), "CLASS"),
    ("LUNCH BREAK", datetime.time(12, 30), datetime.time(13, 30), "LUNCH"),
    ("P5", datetime.time(13, 30), datetime.time(14, 25), "CLASS"),
    ("P6", datetime.time(14, 25), datetime.time(15, 20), "CLASS"),
    ("P7", datetime.time(15, 20), datetime.time(16, 15), "CLASS"),
]

CANONICAL_DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT"]


def normalize_day_code(d: str | None) -> str:
    if not d:
        return "MON"
    u = d.strip().upper()
    if u.startswith("MON"):
        return "MON"
    if u.startswith("TUE"):
        return "TUE"
    if u.startswith("WED"):
        return "WED"
    if u.startswith("THU"):
        return "THU"
    if u.startswith("FRI"):
        return "FRI"
    if u.startswith("SAT"):
        return "SAT"
    return u[:3]


def standardize_time_slots():
    with SessionLocal() as db:
        print("[*] Standardizing time slots to 54 official university slots...")

        # Step 1: Ensure the 54 canonical slots exist
        canonical_map: Dict[Tuple[str, datetime.time, datetime.time], TimeSlot] = {}

        for day in CANONICAL_DAYS:
            for label, st, et, stype in CANONICAL_PERIODS:
                # Find matching slot by day (either full name or 3-letter) and exact start/end time
                slot = (
                    db.query(TimeSlot)
                    .filter(
                        (TimeSlot.day == day) | (TimeSlot.day.ilike(f"{day}%")),
                        TimeSlot.start_time == st,
                        TimeSlot.end_time == et,
                    )
                    .first()
                )

                if not slot:
                    slot = TimeSlot(
                        day=day,
                        start_time=st,
                        end_time=et,
                        slot_type=stype,
                    )
                    db.add(slot)
                    db.flush()
                else:
                    slot.day = day
                    slot.slot_type = stype
                    db.flush()

                canonical_map[(day, st, et)] = slot

        canonical_ids = set(s.id for s in canonical_map.values())
        print(f"[+] Ensured all 54 canonical slots exist. IDs: {min(canonical_ids)}..{max(canonical_ids)}")

        # Step 2: For any TimetableEntry or FacultyAvailability referencing non-canonical slots,
        # remap them to the canonical slot if possible, or remove obsolete references
        all_slots = db.query(TimeSlot).all()
        obsolete_slots = [s for s in all_slots if s.id not in canonical_ids]

        if obsolete_slots:
            obsolete_ids = [s.id for s in obsolete_slots]
            print(f"[*] Found {len(obsolete_slots)} obsolete slots to clean up (IDs: {obsolete_ids[:5]}...)")

            # Remap entries that have matching day and time
            for obs in obsolete_slots:
                day_code = normalize_day_code(obs.day)
                # Try finding canonical slot with closest start_time or same day
                matching_canon = next(
                    (s for (d, st, et), s in canonical_map.items() if d == day_code and st == obs.start_time),
                    None
                )
                if matching_canon:
                    db.query(TimetableEntry).filter(TimetableEntry.slot_id == obs.id).update(
                        {"slot_id": matching_canon.id}
                    )
                    db.query(FacultyAvailability).filter(FacultyAvailability.slot_id == obs.id).update(
                        {"slot_id": matching_canon.id}
                    )
                else:
                    # Remove obsolete references that can't be mapped
                    db.query(TimetableEntry).filter(TimetableEntry.slot_id == obs.id).delete()
                    db.query(FacultyAvailability).filter(FacultyAvailability.slot_id == obs.id).delete()

            # Now delete obsolete slots
            db.query(TimeSlot).filter(TimeSlot.id.in_(obsolete_ids)).delete(synchronize_session=False)
            db.commit()
            print(f"[+] Successfully deleted {len(obsolete_slots)} obsolete slots.")
        else:
            db.commit()
            print("[+] Zero obsolete slots found. All slots are canonical.")

        # Step 3: Ensure faculty availability exists for all 42 CLASS slots across all active faculty
        from backend.models.academic import Faculty
        faculties = db.query(Faculty).all()
        class_slots = [s for s in canonical_map.values() if s.slot_type == "CLASS"]
        added_fa = 0
        for f in faculties:
            for cs in class_slots:
                existing = (
                    db.query(FacultyAvailability)
                    .filter(FacultyAvailability.faculty_id == f.id, FacultyAvailability.slot_id == cs.id)
                    .first()
                )
                if not existing:
                    fa = FacultyAvailability(faculty_id=f.id, slot_id=cs.id, availability="AVAILABLE", preference=1)
                    db.add(fa)
                    added_fa += 1
        db.commit()
        if added_fa > 0:
            print(f"[+] Added {added_fa} missing FacultyAvailability records for canonical class slots.")

        remaining_slots = db.query(TimeSlot).count()
        print(f"[SUCCESS] Final TimeSlot count in database: {remaining_slots} (Expected: 54)")


if __name__ == "__main__":
    standardize_time_slots()
