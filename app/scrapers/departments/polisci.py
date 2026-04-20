from __future__ import annotations

"""
polisci.py — Columbia Political Science Department events scraper.

Source: https://polisci.columbia.edu/events

Uses the exact same JSON-embed pattern as psychology.columbia.edu:
a `var events_data = [...]` JavaScript array is embedded in a <script> tag
on the listing page.

Event object fields (same schema as Psychology):
  title, path, from_timestamp, to_timestamp, location, views_conditional_field,
  can_register, reglink, field_cu_event_contact_*, event_url
"""

import json
import logging
import re
from datetime import datetime

from app.scrapers.base import BaseScraper
from app.scrapers.utils.location import get_coordinates

logger = logging.getLogger(__name__)

BASE = "https://polisci.columbia.edu"
_JS_VAR_RE = re.compile(r"var\s+events_data\s*=\s*(\[.*?\])\s*;", re.DOTALL)


class PolSciScraper(BaseScraper):
    department_slug = "polisci"
    base_url = f"{BASE}/events"
    use_playwright = False

    def __init__(self):
        super().__init__()
        self._cache: dict[str, dict] = {}

    def get_event_urls(self) -> list[str]:
        html = self._fetch(self.base_url)
        if not html:
            return []

        raw_events = self._extract_json(html)
        if not raw_events:
            logger.warning("polisci: could not find events_data in page")
            return []

        urls = []
        for ev in raw_events:
            path = ev.get("path", "")
            if not path:
                continue
            url = BASE + path
            self._cache[url] = ev
            urls.append(url)

        logger.info("polisci: found %d events", len(urls))
        return urls

    def parse_event(self, html: str, url: str) -> dict:
        ev = self._cache.get(url)
        if ev:
            return self._from_json(ev, url)
        return self._parse_html_fallback(html, url)

    # ------------------------------------------------------------------
    # Helpers (identical logic to PsychologyScraper)
    # ------------------------------------------------------------------

    def _extract_json(self, html: str) -> list[dict]:
        m = _JS_VAR_RE.search(html)
        if not m:
            return []
        raw = m.group(1)
        raw = raw.replace(": false", ": null").replace(": true", ": true")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("polisci: JSON parse error: %s", exc)
            return []

    def _from_json(self, ev: dict, url: str) -> dict:
        title = ev.get("title", "").strip()
        if not title:
            return {}

        start_dt = self._ts(ev.get("from_timestamp"))
        end_dt   = self._ts(ev.get("to_timestamp"))

        raw_loc = ev.get("location", "") or ""
        if "\t" in raw_loc:
            parts = raw_loc.split("\t")
            building = parts[0].strip()
            room = parts[1].strip()
            location_name = f"{building}, Room {room}" if room else building
        else:
            location_name = raw_loc.strip()

        location_address = None
        addr_match = re.search(r"(\d+\s+\w+\s+(?:Ave|St|Blvd|Rd|Dr)\..*)", location_name)
        if addr_match:
            location_address = addr_match.group(1).strip()
            building = location_name[: addr_match.start()].strip().rstrip(",")
            room_suffix = location_name[location_name.rfind("Room"):] if "Room" in location_name else ""
            location_name = f"{building}, {room_suffix}".strip(", ") if room_suffix else building

        lat, lon = get_coordinates(location_name, location_address)

        html_desc = ev.get("views_conditional_field", "") or ""
        description = re.sub(r"<[^>]+>", " ", html_desc).strip()
        description = re.sub(r"\s+", " ", description)

        reglink = ev.get("reglink") or None
        can_register = ev.get("can_register", "0") == "1"
        registration_url = reglink if (reglink and can_register) else None

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
            "is_free": True,
            "tags": [],
        }

    @staticmethod
    def _ts(val) -> datetime | None:
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
        soup = self._soup(html)
        h1 = soup.find("h1")
        if not h1:
            return {}
        return {"title": h1.get_text(strip=True), "tags": []}
