"""
backend/database.py
-------------------
Database connection and session management.
Re-exports the central engine, SessionLocal, and DATABASE_URL from backend.config
to ensure a single, unified connection pool with pool_pre_ping=True enabled
across all API routes.
"""

from backend.config import DATABASE_URL, engine, SessionLocal


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
