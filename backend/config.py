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

# SQLAlchemy 2.0 engine
# pool_pre_ping=True keeps the connection alive on Windows where idle
# connections can be dropped by the OS or the Postgres server.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
