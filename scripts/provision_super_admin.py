"""
scripts/provision_super_admin.py
--------------------------------
Privileged Administrative Provisioning CLI for RIO-MJP SUPER_ADMIN accounts.

Usage:
  python scripts/provision_super_admin.py --email superadmin@campus.edu --name "Dr. Eleanor Vance" --password "Test@1234"
"""

from __future__ import annotations

import argparse
import sys
import os

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal
from backend.models.identity import User
from backend.models.workflow import AuditLog
from backend.core.security import get_password_hash


def provision_super_admin(email: str, name: str, password: str) -> None:
    email_clean = email.strip().lower()
    name_clean = name.strip()

    if len(password) < 6:
        print("[ERROR] Password must be at least 6 characters long.", file=sys.stderr)
        sys.exit(1)

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email_clean).first()
        hashed = get_password_hash(password)

        old_role: str | None = None
        if user:
            old_role = user.role
            user.role = "SUPER_ADMIN"
            user.name = name_clean or user.name
            user.password_hash = hashed
            user.is_active = True
            print(f"[UPDATED] Existing user '{user.email}' upgraded to SUPER_ADMIN (previous role: {old_role}).")
            action = "UPGRADE_TO_SUPER_ADMIN"
            prev_summary = f"role={old_role}"
        else:
            user = User(
                email=email_clean,
                name=name_clean,
                password_hash=hashed,
                role="SUPER_ADMIN",
                is_active=True,
            )
            db.add(user)
            db.flush()
            print(f"[CREATED] New SUPER_ADMIN account '{user.email}' created successfully with User ID #{user.id}.")
            action = "PROVISION_SUPER_ADMIN"
            prev_summary = "None"

        # Record audit log
        audit = AuditLog(
            user_id=user.id,
            action=action,
            entity_type="users",
            entity_id=user.id,
            old_value={"role": old_role} if old_role else None,
            new_value={
                "email": user.email,
                "role": "SUPER_ADMIN",
                "name": user.name,
            },
        )
        db.add(audit)
        db.commit()
        print(f"[SUCCESS] Super Admin '{user.email}' provisioned and logged in audit history.")


def main():
    parser = argparse.ArgumentParser(description="Provision a RIO-MJP Super Admin user account.")
    parser.add_argument("--email", required=True, help="Institutional email for Super Admin")
    parser.add_argument("--name", default="Super Administrator", help="Display name")
    parser.add_argument("--password", required=True, help="Initial password")

    args = parser.parse_args()
    provision_super_admin(args.email, args.name, args.password)


if __name__ == "__main__":
    main()
