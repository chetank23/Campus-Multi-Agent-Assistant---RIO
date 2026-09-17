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

DATABASE_URL: str = os.environ["DATABASE_URL"]
_DEFAULT_DEV_SECRET = "super-secret-key-for-dev-change-to-a-long-random-secret-at-least-32-bytes"
SECRET_KEY: str = os.environ["SECRET_KEY"]
if not SECRET_KEY or SECRET_KEY == _DEFAULT_DEV_SECRET:
    raise ValueError("SECRET_KEY must be set in environment and cannot use default placeholder key")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 20
REFRESH_TOKEN_EXPIRE_DAYS: int = 7

# SQLAlchemy 2.0 engine
# pool_pre_ping=True keeps the connection alive on Windows where idle
# connections can be dropped by the OS or the Postgres server.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
