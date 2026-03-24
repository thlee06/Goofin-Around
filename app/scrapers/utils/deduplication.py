"""
Deduplication utilities for the scraping pipeline.

Two levels of deduplication:
1. Per-source: external_id = SHA-256 hash of (source_url + title)
   Prevents the same event from being inserted twice when a scraper re-runs.

2. Cross-department: events with matching title + start_datetime (within 1 hour)
   are flagged as potential duplicates. They are stored as separate rows but
   linked via a shared canonical_group field (future V1 feature).
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def compute_external_id(source_url: str, title: str) -> str:
    """SHA-256 hash of 'source_url|title'. Used as the unique key per event source."""
    raw = f"{source_url}|{title}"
    return hashlib.sha256(raw.encode()).hexdigest()


def upsert_event(db: Session, event_data: dict) -> bool:
    """
    Insert or update an event based on its external_id.

    Returns True if a new event was created, False if an existing one was updated.
    """
    from app.models.event import Event

    external_id = event_data.get("external_id")
    if not external_id:
        raise ValueError("event_data must contain 'external_id'")

    existing = db.query(Event).filter_by(external_id=external_id).first()

    if existing:
        # Update mutable fields; preserve created_at
        for key, value in event_data.items():
            if key not in ("id", "created_at", "external_id"):
                setattr(existing, key, value)
        existing.is_active = True
        db.commit()
        return False
    else:
        event = Event(**event_data)
        db.add(event)
        db.commit()
        return True


def find_cross_department_duplicates(
    db: Session,
    title: str,
    start_datetime: Optional[datetime],
    exclude_event_id: Optional[int] = None,
    window_hours: int = 1,
) -> list:
    """
    Find events with a matching title and start time (within window_hours)
    from a different department. Used for cross-department dedup reporting.
    """
    from app.models.event import Event

    if not start_datetime:
        return []

    window_start = start_datetime - timedelta(hours=window_hours)
    window_end = start_datetime + timedelta(hours=window_hours)

    query = (
        db.query(Event)
        .filter(
            Event.title.ilike(f"%{title}%"),
            Event.start_datetime >= window_start,
            Event.start_datetime <= window_end,
            Event.is_active == True,
        )
    )
    if exclude_event_id:
        query = query.filter(Event.id != exclude_event_id)

    return query.all()
