"""
backend/utils/datetime_utils.py
-------------------------------
Timezone-aware UTC datetime helpers compliant with Python 3.11+ / 3.12+ / 3.13+.
Replaces deprecated `datetime.utcnow()`.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """
    Returns the current UTC time as a naive datetime object.

    This matches PostgreSQL TIMESTAMP WITHOUT TIME ZONE storage expectations
    and provides exact behavioral parity with the deprecated datetime.utcnow()
    without emitting Python deprecation warnings.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_now_aware() -> datetime:
    """
    Returns the current UTC time as a timezone-aware datetime object in UTC.
    """
    return datetime.now(timezone.utc)
