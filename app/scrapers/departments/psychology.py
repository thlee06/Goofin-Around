from __future__ import annotations

"""
psychology.py — Columbia Psychology Department events scraper.

The events page embeds all event data as a JavaScript array in a <script> tag:

    var events_data = [ { "title": "...", "path": "/events/...", ... }, ... ];

We parse that JSON directly — no need to visit individual detail pages for
basic event info. Detail pages are visited only if we can't find a description
in the JSON payload.

Source: https://psychology.columbia.edu/events
"""

import json
import logging
import re
from datetime import datetime, timezone

from app.scrapers.base import BaseScraper
from app.scrapers.utils.date_parser import normalize_safe
from app.scrapers.utils.location import get_coordinates

logger = logging.getLogger(__name__)

BASE = "https://psychology.columbia.edu"
_JS_VAR_RE = re.compile(
    r"var\s+events_data\s*=\s*(\[.*?\])\s*;",
    re.DOTALL,
)


class PsychologyScraper(BaseScraper):
    department_slug = "psychology"
    base_url = f"{BASE}/events"
    use_playwright = False

    def __init__(self):
        super().__init__()
        # Populated by get_event_urls(), consumed by parse_event()
        self._cache: dict[str, dict] = {}

    def get_event_urls(self) -> list[str]:
        html = self._fetch(self.base_url)
        if not html:
            return []

        raw_events = self._extract_json(html)
        if not raw_events:
            logger.warning("psychology: could not find events_data in page")
            return []

        urls = []
        for ev in raw_events:
            path = ev.get("path", "")
            if not path:
                continue
            url = BASE + path
            self._cache[url] = ev
            urls.append(url)

        logger.info("psychology: found %d events", len(urls))
        return urls

    def parse_event(self, html: str, url: str) -> dict:
        ev = self._cache.get(url)
        if ev:
            return self._from_json(ev, url)
        # Fallback: parse the detail page HTML (shouldn't normally be needed)
        return self._parse_html_fallback(html, url)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_json(self, html: str) -> list[dict]:
        """Find the events_data JS array and parse it as JSON."""
        m = _JS_VAR_RE.search(html)
        if not m:
            return []
        raw = m.group(1)
        # JS booleans → Python
        raw = raw.replace(": false", ": null").replace(": true", ": true")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("psychology: JSON parse error: %s", exc)
            return []

    def _from_json(self, ev: dict, url: str) -> dict:
        title = ev.get("title", "").strip()
        if not title:
            return {}

        # Timestamps are Unix epoch strings in UTC
        start_dt = self._ts(ev.get("from_timestamp"))
        end_dt = self._ts(ev.get("to_timestamp"))

        # Location: "Building, Address\tRoom" — split on tab
        raw_loc = ev.get("location", "") or ""
        if "\t" in raw_loc:
            loc_parts = raw_loc.split("\t")
            location_name = loc_parts[0].strip()
            # Append room to name for clarity
            room = loc_parts[1].strip()
            if room:
                location_name = f"{location_name}, Room {room}"
        else:
            location_name = raw_loc.strip()

        # Strip the full address from the name (keep only building/room)
        # e.g. "Schermerhorn Hall, 1198 Amsterdam Ave., New York, NY 10027" → "Schermerhorn Hall"
        location_address = None
        addr_match = re.search(r"(\d+\s+\w+\s+(?:Ave|St|Blvd|Rd|Dr)\..*)", location_name)
        if addr_match:
            location_address = addr_match.group(1).strip()
            # Use just building name + room for location_name
            building = location_name[: addr_match.start()].strip().rstrip(",")
            room_suffix = location_name[location_name.rfind("Room"):]
            location_name = f"{building}, {room_suffix}".strip(", ") if "Room" in location_name else building

        lat, lon = get_coordinates(location_name, location_address)

        # Description is HTML; strip tags for short version
        html_desc = ev.get("views_conditional_field", "") or ""
        description = re.sub(r"<[^>]+>", " ", html_desc).strip()
        description = re.sub(r"\s+", " ", description)

        # Registration link
        reglink = ev.get("reglink") or None
        can_register = ev.get("can_register", "0") == "1"
        registration_url = reglink if (reglink and can_register) else None

        # Tags from context
        tags = ["colloquium"] if "colloquium" in title.lower() else []

        return {
            "title": title,
            "description": description or None,
            "short_description": (description or "")[:280] or None,
            "start_datetime": start_dt,
            "end_datetime": end_dt,
            "all_day": False,
            "location_name": location_name or None,
            "location_address": location_address,
            "latitude": lat,
            "longitude": lon,
            "registration_url": registration_url,
            "is_free": True,  # Psychology colloquia are open to public
            "tags": tags,
        }

    @staticmethod
    def _ts(val) -> datetime | None:
        """Convert a Unix timestamp string to a timezone-aware datetime (ET)."""
        if not val:
            return None
        try:
            ts = int(val)
            if ts == 0:
                return None
            from zoneinfo import ZoneInfo
            return datetime.fromtimestamp(ts, tz=ZoneInfo("America/New_York"))
        except (ValueError, TypeError):
            return None

    def _parse_html_fallback(self, html: str, url: str) -> dict:
        """Parse an individual event page as fallback if JSON cache misses."""
        soup = self._soup(html)
        title_el = soup.find("h1")
        if not title_el:
            return {}
        title = title_el.get_text(strip=True)

        desc_el = soup.find("div", class_=re.compile(r"field.*body|body|content", re.I))
        description = desc_el.get_text(" ", strip=True) if desc_el else None

        return {
            "title": title,
            "description": description,
            "short_description": (description or "")[:280] or None,
            "tags": [],
        }
