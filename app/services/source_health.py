from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SourceHealth


def _get_or_create(db: Session, source_key: str) -> SourceHealth:
    row = db.scalar(select(SourceHealth).where(SourceHealth.source_key == source_key))
    if row is None:
        row = SourceHealth(source_key=source_key)
        db.add(row)
        db.flush()
    return row


def mark_attempt(db: Session, source_key: str) -> SourceHealth:
    row = _get_or_create(db, source_key)
    row.last_attempt_at = datetime.now(timezone.utc)
    return row


def mark_success(db: Session, source_key: str, summary: str | None = None) -> None:
    row = _get_or_create(db, source_key)
    now = datetime.now(timezone.utc)
    row.state = "healthy"
    row.last_attempt_at = now
    row.last_success_at = now
    row.last_error = None
    row.consecutive_failures = 0
    row.last_value_summary = summary


def mark_failure(db: Session, source_key: str, error: Exception | str) -> None:
    row = _get_or_create(db, source_key)
    row.state = "degraded"
    row.last_attempt_at = datetime.now(timezone.utc)
    row.last_error = str(error)[:2000]
    row.consecutive_failures = (row.consecutive_failures or 0) + 1
