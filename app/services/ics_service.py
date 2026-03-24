"""
ics_service.py — Generate .ics calendar files from Event objects.
Uses the `icalendar` library.
"""

from datetime import timezone
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event as ICSEvent, vText, vDatetime

EASTERN = ZoneInfo("America/New_York")


def generate_ics_for_event(event) -> bytes:
    """Generate a .ics file for a single Event. Returns bytes."""
    cal = _make_calendar()
    cal.add_component(_make_vevent(event))
    return cal.to_ical()


def generate_ics_for_events(events: list) -> bytes:
    """Generate a single .ics file containing multiple events. Returns bytes."""
    cal = _make_calendar()
    for event in events:
        cal.add_component(_make_vevent(event))
    return cal.to_ical()


def _make_calendar() -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//Columbia Events Hub//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", "Columbia University Events")
    cal.add("x-wr-timezone", "America/New_York")
    return cal


def _make_vevent(event) -> ICSEvent:
    vevent = ICSEvent()
    vevent.add("uid", f"columbia-event-{event.id}@columbia-events-hub")
    vevent.add("summary", event.title)

    if event.description:
        vevent.add("description", event.description)

    if event.start_datetime:
        dt = _localize(event.start_datetime)
        vevent.add("dtstart", dt)

    if event.end_datetime:
        dt = _localize(event.end_datetime)
        vevent.add("dtend", dt)

    if event.location_name:
        vevent.add("location", event.location_name)

    if event.source_url:
        vevent.add("url", event.source_url)

    return vevent


def _localize(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=EASTERN)
    return dt
