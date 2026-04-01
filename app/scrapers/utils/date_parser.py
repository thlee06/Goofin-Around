from __future__ import annotations

"""
date_parser.py — Normalize messy date strings from university department websites.

This is the highest-risk utility in the project. University websites use an
enormous variety of date formats. We wrap dateutil's parser with Columbia-specific
fallbacks and provide clear failure paths.

All returned datetimes are timezone-aware (America/New_York default).
Caller receives None if parsing completely fails.
"""

import logging
import re
from datetime import datetime, date
from typing import Optional
from zoneinfo import ZoneInfo

from dateutil import parser as dateutil_parser
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")

# Non-ET timezone strings seen on Columbia sites that need to be flagged
NON_ET_PATTERNS = re.compile(
    r"\b(PST|PDT|PT|CST|CDT|CT|MST|MDT|MT|GMT|UTC|BST|CET)\b", re.IGNORECASE
)

# Patterns we clean before passing to dateutil
CLEANUP_PATTERNS = [
    (r"\|", " "),                   # "Mar 23 | 4pm" -> "Mar 23  4pm"
    (r"(\d)(am|pm)", r"\1 \2"),     # "4pm" -> "4 pm"
    (r"(\d)\s*–\s*(\d)", r"\1-\2"), # en-dash -> hyphen in time ranges
    (r"\s+", " "),                  # collapse whitespace
]

# Known completely unparseable strings → return None silently
UNPARSEABLE = frozenset(["tba", "tbd", "to be announced", "to be determined", ""])


def normalize(raw: str, default_tz: ZoneInfo = EASTERN) -> Optional[datetime]:
    """
    Parse a raw date string into a timezone-aware datetime.

    Returns None if parsing fails. Never raises.
    """
    if not raw:
        return None

    raw = raw.strip()

    if raw.lower() in UNPARSEABLE:
        return None

    # Detect non-ET timezone before cleaning (for the flag)
    non_et = bool(NON_ET_PATTERNS.search(raw))

    cleaned = _clean(raw)

    # Try dateutil first
    dt = _try_dateutil(cleaned)

    if dt is None:
        # Try stripping the time part if it looks like a date-only string
        dt = _try_date_only(cleaned)

    if dt is None:
        logger.warning("date_parser: could not parse %r", raw)
        return None

    # Localize if naive
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_tz)

    return dt, non_et  # type: ignore[return-value]


def normalize_safe(raw: str, default_tz: ZoneInfo = EASTERN) -> tuple[Optional[datetime], bool]:
    """
    Returns (datetime | None, timezone_flag: bool).

    timezone_flag is True if a non-ET timezone was detected in the raw string.
    """
    if not raw:
        return None, False

    raw = raw.strip()
    if raw.lower() in UNPARSEABLE:
        return None, False

    non_et = bool(NON_ET_PATTERNS.search(raw))
    cleaned = _clean(raw)

    dt = _try_dateutil(cleaned) or _try_date_only(cleaned)

    if dt is None:
        logger.warning("date_parser: could not parse %r", raw)
        return None, non_et

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_tz)

    return dt, non_et


def expand_recurring(raw: str, reference_year: Optional[int] = None) -> list[datetime]:
    """
    Attempt to expand simple recurring patterns into a list of datetimes.

    Handles:
      - "Every Tuesday at 4pm through May 15, 2026"
      - "Weekly on Mondays, 2:00 PM, March 1 – April 30"

    Returns an empty list if the pattern is not recognized (caller should
    store as a single event with the raw string in the description).
    """
    raw = raw.strip()
    year = reference_year or datetime.now().year

    # Pattern: "Every <weekday> at <time> through <end date>"
    m = re.search(
        r"every\s+(\w+day)\s+at\s+([\d:apm\s]+)\s+through\s+(.+)",
        raw, re.IGNORECASE
    )
    if m:
        weekday_str, time_str, end_str = m.group(1), m.group(2), m.group(3)
        end_dt, _ = normalize_safe(end_str)
        if end_dt:
            return _weekly_between(weekday_str, time_str, datetime.now(EASTERN), end_dt)

    return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clean(raw: str) -> str:
    result = raw
    for pattern, repl in CLEANUP_PATTERNS:
        result = re.sub(pattern, repl, result)
    return result.strip()


def _try_dateutil(s: str) -> Optional[datetime]:
    try:
        return dateutil_parser.parse(s, fuzzy=True)
    except (ValueError, OverflowError):
        return None


def _try_date_only(s: str) -> Optional[datetime]:
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            d = datetime.strptime(s.split()[0] if " " in s else s, fmt)
            return d.replace(hour=0, minute=0, second=0)
        except ValueError:
            continue
    return None


_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _weekly_between(weekday_str: str, time_str: str, start: datetime, end: datetime) -> list[datetime]:
    target_wd = _WEEKDAYS.get(weekday_str.lower())
    if target_wd is None:
        return []

    time_dt, _ = normalize_safe(f"2000-01-01 {time_str}")
    if not time_dt:
        return []

    results = []
    current = start
    # Advance to the first occurrence of target weekday
    days_ahead = (target_wd - current.weekday()) % 7
    current = current + relativedelta(days=days_ahead)

    while current <= end:
        dt = current.replace(hour=time_dt.hour, minute=time_dt.minute, second=0, microsecond=0)
        results.append(dt)
        current += relativedelta(weeks=1)

    return results
