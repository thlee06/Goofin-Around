from __future__ import annotations

"""
law.py — Columbia Law School events scraper.

Listing page: https://www.law.columbia.edu/events?page=N
Structure: Drupal-rendered static HTML — events are in the page source.

Each event item in the listing looks like:
    <div>
      <span>Apr</span><span>2</span><span>2026</span>
      <h2><a href="/events/[slug]">Title</a></h2>
      <p>Thu, 12:10 p.m. - 1:10 p.m.</p>
      <p>Location name and address</p>
      <ul>topic links</ul>
    </div>

We collect URLs from the listing (with date/time/location already available),
then visit each detail page only to get the full description.
"""

import logging
import re
from datetime import datetime

from app.scrapers.base import BaseScraper
from app.scrapers.utils.date_parser import normalize_safe
from app.scrapers.utils.location import get_coordinates

logger = logging.getLogger(__name__)

BASE = "https://www.law.columbia.edu"
MAX_PAGES = 10  # Safety ceiling — site currently has ~7 pages


class LawScraper(BaseScraper):
    department_slug = "law"
    base_url = f"{BASE}/events"
    use_playwright = False

    def __init__(self):
        super().__init__()
        # url → partial event data extracted from the listing page
        self._listing_cache: dict[str, dict] = {}

    def get_event_urls(self) -> list[str]:
        urls = []
        for page_num in range(MAX_PAGES):
            page_url = f"{self.base_url}?page={page_num}"
            html = self._fetch(page_url)
            if not html:
                break

            soup = self._soup(html)
            links = soup.select('h2 a[href^="/events/"]')
            if not links:
                break  # No more events

            for link in links:
                href = link["href"]
                full_url = BASE + href
                if full_url in self._listing_cache:
                    continue

                # Walk up to find the parent container for date/time/location
                container = link.parent.parent  # a → h2 → container div
                listing_data = self._parse_listing_item(container, link)
                self._listing_cache[full_url] = listing_data
                urls.append(full_url)

            # If we got fewer than ~10 links, probably on the last page
            if len(links) < 5:
                break

        logger.info("law: found %d event URLs across %d pages", len(urls), page_num + 1)
        return urls

    def parse_event(self, html: str, url: str) -> dict:
        soup = self._soup(html)

        # Title from h1 (fallback to listing cache)
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else None

        # Description — look for the main content block
        description = self._extract_description(soup)

        base = self._listing_cache.get(url, {})

        if not title:
            title = base.get("title", "")
        if not title:
            return {}

        # Use listing-extracted date/time if detail page parsing fails
        start_dt = base.get("start_datetime")
        end_dt = base.get("end_datetime")
        location_name = base.get("location_name")
        lat = base.get("latitude")
        lon = base.get("longitude")
        tags = base.get("tags", [])

        return {
            "title": title,
            "description": description or None,
            "short_description": (description or "")[:280] or None,
            "start_datetime": start_dt,
            "end_datetime": end_dt,
            "all_day": base.get("all_day", False),
            "location_name": location_name,
            "latitude": lat,
            "longitude": lon,
            "is_free": True,
            "tags": tags,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_listing_item(self, container, link) -> dict:
        """
        Extract date, time, and location from a listing-page event container.

        The container looks like:
            <div>
              <span>Apr</span><span>2</span><span>2026</span>
              <h2><a href="...">Title</a></h2>
              <p>Thu, 12:10 p.m. - 1:10 p.m.</p>
              <p>Location string</p>
              <ul>topic links</ul>
            </div>
        """
        result: dict = {"title": link.get_text(strip=True)}

        # Date: three <span> siblings (month, day, year) before the h2
        spans = container.find_all("span", recursive=False)
        date_str = ""
        if len(spans) >= 3:
            date_str = f"{spans[0].get_text(strip=True)} {spans[1].get_text(strip=True)}, {spans[2].get_text(strip=True)}"

        # Paragraphs: first is time, second is location
        paras = container.find_all("p", recursive=False)
        time_str = paras[0].get_text(strip=True) if paras else ""
        loc_str = paras[1].get_text(strip=True) if len(paras) > 1 else ""

        # All-day check
        result["all_day"] = "all day" in time_str.lower()

        # Parse start datetime
        if date_str:
            # Combine date + time: "Apr 2, 2026 12:10 p.m."
            time_part = re.sub(r"^[A-Za-z]+,\s*", "", time_str)  # strip "Thu, "
            # Extract start time (before " - ")
            start_time = time_part.split(" - ")[0].strip() if " - " in time_part else time_part
            end_time_str = time_part.split(" - ")[1].strip() if " - " in time_part else ""

            start_dt, _ = normalize_safe(f"{date_str} {start_time}")
            result["start_datetime"] = start_dt

            if end_time_str:
                end_dt, _ = normalize_safe(f"{date_str} {end_time_str}")
                result["end_datetime"] = end_dt

        # Location — strip Columbia address suffix if present
        if loc_str:
            # Remove known address fragments for display name
            loc_name = re.sub(
                r",?\s*\d+\s+\w+[\w\s\.]+(?:Ave|St|Blvd|Rd|Dr)\..*",
                "",
                loc_str,
            ).strip().strip(",").strip()
            result["location_name"] = loc_name or loc_str
            lat, lon = get_coordinates(loc_name or loc_str, loc_str)
            result["latitude"] = lat
            result["longitude"] = lon

        # Tags from topic links
        ul = container.find("ul")
        if ul:
            result["tags"] = [a.get_text(strip=True).lower() for a in ul.find_all("a")]

        return result

    def _extract_description(self, soup) -> str | None:
        """
        Pull the event description from a Law School detail page.
        The page has an "About This Event" section — we grab everything after it.
        """
        # Try common Drupal body field selectors
        for selector in [
            ".field--name-body",
            ".field-name-body",
            ".field--type-text-with-summary",
            "article .field",
        ]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(" ", strip=True)
                if len(text) > 50:
                    return text

        # Fallback: find the "About This Event" heading and grab sibling text
        about_header = soup.find(string=re.compile(r"about this event", re.I))
        if about_header:
            parent = about_header.parent
            # Grab all subsequent text sibling nodes
            texts = []
            for sibling in parent.next_siblings:
                t = getattr(sibling, "get_text", lambda **kw: str(sibling))(strip=True)
                if t:
                    texts.append(t)
            if texts:
                return " ".join(texts)[:2000]

        # Last resort: grab the largest <p> block in main content
        main = soup.find("main") or soup.find("article") or soup.body
        if main:
            paragraphs = main.find_all("p")
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 100:
                    return text

        return None
