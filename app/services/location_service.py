"""
location_service.py — Geocode event location strings.

This is a thin wrapper around scrapers/utils/location.py,
provided as a service-layer entry point for use outside of scrapers
(e.g., backfill scripts, manual event submissions).
"""

from typing import Optional
from app.scrapers.utils.location import get_coordinates


def geocode_event(event) -> tuple[Optional[float], Optional[float]]:
    """
    Attempt to geocode an event's location fields.
    Returns (lat, lon) or (None, None). Does not modify the event.
    """
    return get_coordinates(
        location_name=event.location_name,
        location_address=event.location_address,
    )


def backfill_coordinates(db) -> int:
    """
    Geocode all active events that are missing lat/lon.
    Returns the number of events geocoded.
    """
    from app.models.event import Event

    events = (
        db.query(Event)
        .filter(
            Event.is_active == True,
            Event.latitude.is_(None),
            Event.location_name.isnot(None),
        )
        .all()
    )

    count = 0
    for event in events:
        lat, lon = geocode_event(event)
        if lat and lon:
            event.latitude = lat
            event.longitude = lon
            count += 1

    if count:
        db.commit()
    return count
