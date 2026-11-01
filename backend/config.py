"""
backend/config.py
-----------------
Reads configuration from .env and exposes SQLAlchemy engine + session factory.
Stage 1: database only. FastAPI / Celery settings are stubs for later stages.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Load .env from repo root (two levels up from backend/)
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

from sqlalchemy.engine import make_url

DATABASE_URL: str = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required and must be set")

try:
    _database_url = make_url(DATABASE_URL)
except Exception as exc:
    raise RuntimeError("DATABASE_URL must be a valid SQLAlchemy database URL.") from exc

if _database_url.get_backend_name() not in ("postgresql", "postgres"):
    raise RuntimeError("DATABASE_URL must target PostgreSQL.")

_SECRET_PLACEHOLDERS = {
    "",
    "your-32-byte-random-secret-key-here",
    "super-secret-key-for-dev-change-to-a-long-random-secret-at-least-32-bytes",
    "change-me",
    "changeme",
    "your-secret-key",
}
SECRET_KEY: str = os.environ.get("SECRET_KEY", "").strip()
if SECRET_KEY.lower() in _SECRET_PLACEHOLDERS or len(SECRET_KEY.encode("utf-8")) < 32:
    raise ValueError(
        "SECRET_KEY must be configured with a non-placeholder value of at least 32 bytes."
    )
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 20
REFRESH_TOKEN_EXPIRE_DAYS: int = 7

# SQLAlchemy 2.0 engine
# pool_pre_ping=True keeps the connection alive on Windows where idle
# connections can be dropped by the OS or the Postgres server.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
