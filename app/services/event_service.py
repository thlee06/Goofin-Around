from __future__ import annotations

"""
event_service.py — Query and filter events from the database.
"""

import calendar
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.department import Department
from app.models.category import Category

# Keyword → category slug mapping for auto-assignment
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "lecture": ["lecture", "seminar", "colloquium", "talk", "speaker", "keynote", "panel"],
    "workshop": ["workshop", "training", "bootcamp", "tutorial", "lab session"],
    "social": ["reception", "happy hour", "mixer", "gathering", "celebration", "party", "lunch"],
    "career": ["career", "recruiting", "internship", "job fair", "networking", "alumni"],
    "arts": ["concert", "exhibition", "performance", "art show", "gallery", "film", "screening"],
}


def get_events(
    db: Session,
    q: Optional[str] = None,
    department: Optional[str] = None,
    category: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    is_free: Optional[bool] = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Event], int]:
    query = (
        db.query(Event)
        .join(Department)
        .filter(Event.is_active == True)
    )

    if department:
        query = query.filter(Department.slug == department)

    if category:
        query = query.join(Category).filter(Category.slug == category)

    if start_date:
        query = query.filter(Event.start_datetime >= datetime.combine(start_date, datetime.min.time()))

    if end_date:
        query = query.filter(Event.start_datetime <= datetime.combine(end_date, datetime.max.time()))

    if is_free is not None:
        query = query.filter(Event.is_free == is_free)

    if q:
        query = query.filter(
            Event.title.ilike(f"%{q}%") | Event.description.ilike(f"%{q}%")
        )

    total = query.count()
    events = (
        query.order_by(Event.start_datetime.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return events, total


def get_event_by_id(db: Session, event_id: int) -> Optional[Event]:
    return db.query(Event).filter(Event.id == event_id, Event.is_active == True).first()


def get_events_for_month(db: Session, year: int, month: int) -> dict[int, list[Event]]:
    """
    Returns a dict mapping day-of-month (int) → list of events for that day.
    """
    _, last_day = calendar.monthrange(year, month)
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    events = (
        db.query(Event)
        .filter(
            Event.is_active == True,
            Event.start_datetime >= start,
            Event.start_datetime <= end,
        )
        .order_by(Event.start_datetime.asc())
        .all()
    )

    by_day: dict[int, list[Event]] = {d: [] for d in range(1, last_day + 1)}
    for event in events:
        if event.start_datetime:
            day = event.start_datetime.day
            by_day[day].append(event)
    return by_day


def get_mappable_events(db: Session) -> list[Event]:
    """Return active events that have lat/lon coordinates for the map view."""
    return (
        db.query(Event)
        .filter(
            Event.is_active == True,
            Event.latitude.isnot(None),
            Event.longitude.isnot(None),
        )
        .order_by(Event.start_datetime.asc())
        .limit(500)
        .all()
    )


def assign_category(db: Session, event: Event) -> None:
    """
    Auto-assign a category to an event based on keyword matching in the title.
    Called during scraping. Modifies event in-place; caller must commit.
    """
    if event.category_id:
        return  # Already assigned

    title_lower = (event.title or "").lower()
    desc_lower = (event.description or "").lower()
    combined = f"{title_lower} {desc_lower}"

    for slug, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            cat = db.query(Category).filter_by(slug=slug).first()
            if cat:
                event.category_id = cat.id
                return

    # Fallback: "Other"
    other = db.query(Category).filter_by(slug="other").first()
    if other:
        event.category_id = other.id
