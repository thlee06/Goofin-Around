from __future__ import annotations

"""
sipa.py — Columbia SIPA (School of International & Public Affairs) events scraper.

Listing page: https://www.sipa.columbia.edu/communities-connections/events
Structure: Drupal — content appears to be server-rendered (not pure AJAX).

Each event in the listing looks like:
    <h3><a href="/communities-connections/events/[slug]">Title</a></h3>
    <div>Date/time text</div>
    <div>Location code (e.g., "IAB 1101")</div>

The site paginates via ?page=N (0-indexed).

Detail page: Has h1 title, date/time, location, and description paragraphs.
"""

import logging
import re

from app.scrapers.base import BaseScraper
from app.scrapers.utils.date_parser import normalize_safe
from app.scrapers.utils.location import get_coordinates

logger = logging.getLogger(__name__)

BASE = "https://www.sipa.columbia.edu"
EVENTS_PATH = "/communities-connections/events"
MAX_PAGES = 10


class SIPAScraper(BaseScraper):
    department_slug = "sipa"
    base_url = f"{BASE}{EVENTS_PATH}"
    use_playwright = False

    def __init__(self):
        super().__init__()
        self._listing_cache: dict[str, dict] = {}

    def get_event_urls(self) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        for page_num in range(MAX_PAGES):
            page_url = f"{self.base_url}?page={page_num}" if page_num > 0 else self.base_url
            html = self._fetch(page_url)
            if not html:
                break

            soup = self._soup(html)

            # SIPA event links: relative paths starting with /communities-connections/events/
            links = soup.select(f'a[href^="{EVENTS_PATH}/"]')
            # Filter out links that are not individual event pages
            links = [
                l for l in links
                if l["href"] != EVENTS_PATH
                and not l["href"].endswith(EVENTS_PATH)
                and "?" not in l["href"]
            ]

            if not links:
                break

            new_on_page = 0
            for link in links:
                href = link["href"]
                full_url = BASE + href
                if full_url in seen:
                    continue
                seen.add(full_url)
                urls.append(full_url)

                # Extract listing-level data: date/time/location from siblings
                listing_data = self._parse_listing_context(link)
                self._listing_cache[full_url] = listing_data

                new_on_page += 1

            if new_on_page == 0:
                break

        logger.info("sipa: found %d event URLs", len(urls))
        return urls

    def parse_event(self, html: str, url: str) -> dict:
        soup = self._soup(html)

        # Title
        h1 = soup.find("h1")
        if not h1:
            return {}
        title = h1.get_text(strip=True)

        # Date/time — look for structured date elements on the detail page
        start_dt = end_dt = None
        date_text = self._find_date_text(soup)
        if date_text:
            # Typical format: "April 1, 2026 12:00 p.m. to 1:00 p.m."
            # Split on " to " for start/end
            if " to " in date_text:
                parts = date_text.split(" to ", 1)
                start_dt, _ = normalize_safe(parts[0].strip())
                if start_dt and parts[1].strip():
                    # End time only — use same date
                    end_dt, _ = normalize_safe(
                        f"{start_dt.strftime('%B %d, %Y')} {parts[1].strip()}"
                    )
            else:
                start_dt, _ = normalize_safe(date_text)

        # Fallback to listing cache
        cached = self._listing_cache.get(url, {})
        if not start_dt:
            start_dt = cached.get("start_datetime")
            end_dt = cached.get("end_datetime")

        # Location
        location_name = self._find_location(soup) or cached.get("location_name")
        # SIPA room codes like "IAB 1101" → expand to full building name
        location_name = _expand_sipa_room(location_name)
        lat, lon = get_coordinates(location_name) if location_name else (None, None)

        # Description
        description = self._find_description(soup)

        # Registration link
        registration_url = None
        for sel in ['a[href*="register"]', 'a[href*="eventbrite"]', 'a[href*="zoom"]']:
            reg = soup.select_one(sel)
            if reg:
                registration_url = reg.get("href")
                break

        return {
            "title": title,
            "description": description or None,
            "short_description": (description or "")[:280] or None,
            "start_datetime": start_dt,
            "end_datetime": end_dt,
            "all_day": False,
            "location_name": location_name,
            "latitude": lat,
            "longitude": lon,
            "registration_url": registration_url,
            "tags": cached.get("tags", []),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_listing_context(self, link) -> dict:
        """Walk up from the link to find date/time and location siblings."""
        result: dict = {"title": link.get_text(strip=True)}

        # Walk up to find the event container (typically a div or article)
        container = link.parent
        for _ in range(4):
            if container is None:
                break
            text = container.get_text(" ", strip=True)
            # Look for something that contains date-like text
            if re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", text):
                break
            container = getattr(container, "parent", None)

        if not container:
            return result

        # Extract all text nodes, filter for date/time/location patterns
        for child in container.children:
            text = getattr(child, "get_text", lambda **k: str(child))(strip=True)
            if not text or text == result.get("title"):
                continue
            # Date pattern
            if re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b", text):
                dt, _ = normalize_safe(text)
                result.setdefault("start_datetime", dt)
            # Time range pattern
            elif re.search(r"\d+:\d+|\d+\s*[ap]\.m\.", text):
                pass  # already handled above
            # Location: IAB/SIPA room codes
            elif re.search(r"\b(IAB|SIPA|Dodge|Fayerweather|Pulitzer|Low|Butler)\b", text, re.I):
                result["location_name"] = _expand_sipa_room(text)

        return result

    def _find_date_text(self, soup) -> str | None:
        """Find the date/time text on a SIPA event detail page."""
        # Look for elements containing month names near a time expression
        for el in soup.find_all(["p", "div", "span", "time"]):
            text = el.get_text(strip=True)
            if re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b", text):
                if re.search(r"\d+:\d+|\d+\s*[ap]\.m\.", text):
                    return text
        return None

    def _find_location(self, soup) -> str | None:
        """Find location text on a SIPA detail page."""
        for el in soup.find_all(["p", "div", "span"]):
            text = el.get_text(strip=True)
            if re.search(r"\b(IAB|SIPA|Dodge|Pulitzer|Butler|Fayerweather|Warren Hall)\b", text, re.I):
                if len(text) < 200:  # Avoid grabbing full descriptions
                    return text
        return None

    def _find_description(self, soup) -> str | None:
        """Extract the main event description from a SIPA detail page."""
        # Try known Drupal body field selectors
        for sel in [".field--name-body", ".field-name-body", "article .field--type-text-with-summary"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(" ", strip=True)
                if len(text) > 50:
                    return text

        # Fallback: grab the longest paragraph in main content
        main = soup.find("main") or soup.find("article") or soup.body
        if main:
            paras = [p.get_text(strip=True) for p in main.find_all("p")]
            paras = [p for p in paras if len(p) > 80]
            if paras:
                return " ".join(paras[:4])  # First few substantial paragraphs

        return None


# ---------------------------------------------------------------------------
# SIPA room code expansion
# ---------------------------------------------------------------------------
_SIPA_ROOMS = {
    "IAB": "International Affairs Building",
    "SIPA": "SIPA Building (420 W 118th St)",
    "Dodge": "Dodge Hall",
    "Pulitzer": "Pulitzer Hall",
    "Warren Hall": "William and June Warren Hall",
    "JG": "Jerome Greene Hall",
}


def _expand_sipa_room(raw: str | None) -> str | None:
    if not raw:
        return None
    for code, full_name in _SIPA_ROOMS.items():
        if re.search(rf"\b{re.escape(code)}\b", raw, re.I):
            # Replace just the code, keep room number
            return re.sub(rf"\b{re.escape(code)}\b", full_name, raw, count=1, flags=re.I)
    return raw
