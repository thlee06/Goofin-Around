from __future__ import annotations

"""
econ.py — Columbia Economics Department events scraper.

Uses The Events Calendar (TEC) WordPress plugin.

Listing page: https://econ.columbia.edu/events/
Each event card uses class `.ecs-event` with a link in `.summary h3 a`.
The `.ecs-excerpt` often contains "Location | Day, Date, Time" inline.

Detail page selectors (TEC standard):
  - Title:       h1.tribe-events-single-event-title
  - Date/time:   .tribe-events-start-datetime or abbr[title] inside .tribe-events-event-meta
  - Location:    .tribe-venue
  - Description: .tribe-events-single-event-description
"""

import logging
import re

from app.scrapers.base import BaseScraper
from app.scrapers.utils.date_parser import normalize_safe
from app.scrapers.utils.location import get_coordinates

logger = logging.getLogger(__name__)

BASE = "https://econ.columbia.edu"


class EconScraper(BaseScraper):
    department_slug = "economics"
    base_url = f"{BASE}/events/"
    use_playwright = False

    def get_event_urls(self) -> list[str]:
        # TEC supports ?tribe-bar-date=YYYY-MM-DD for date navigation.
        # Collect from the default listing + next 2 months for coverage.
        from datetime import date, timedelta
        urls: list[str] = []
        seen: set[str] = set()

        # Listing pages to check: default + next-page pagination
        listing_urls = [self.base_url]

        # TEC pagination uses /page/N/ or ?tribe_paged=N
        for page in range(1, 6):
            listing_urls.append(f"{self.base_url}page/{page}/")

        for listing_url in listing_urls:
            html = self._fetch(listing_url)
            if not html:
                continue
            soup = self._soup(html)

            # Find all event links from .ecs-event cards
            links = soup.select(".ecs-event .summary a, .ecs-event .tribe-event-url")
            if not links:
                # Also try the standard TEC listing selectors
                links = soup.select(
                    ".tribe-events-list-event-title a, "
                    ".tribe-event-url, "
                    "h2.tribe-events-list-event-title a"
                )

            new_on_page = 0
            for link in links:
                href = link.get("href", "")
                if not href or href == "#":
                    continue
                if not href.startswith("http"):
                    href = BASE + href
                if href not in seen:
                    seen.add(href)
                    urls.append(href)
                    new_on_page += 1

            if new_on_page == 0:
                break  # No new events on this page — stop paginating

        logger.info("economics: found %d event URLs", len(urls))
        return urls

    def parse_event(self, html: str, url: str) -> dict:
        soup = self._soup(html)

        # Title
        title_el = (
            soup.select_one("h1.tribe-events-single-event-title")
            or soup.select_one(".tribe-events-single-event-title")
            or soup.find("h1")
        )
        if not title_el:
            return {}
        title = title_el.get_text(strip=True)

        # Date/time — TEC stores ISO datetime in abbr[title] or .tribe-events-abbr
        start_dt = end_dt = None
        start_el = soup.select_one("abbr.tribe-events-abbr.tribe-events-start-datetime")
        if start_el:
            start_dt, _ = normalize_safe(start_el.get("title", "") or start_el.get_text())

        end_el = soup.select_one("abbr.tribe-events-abbr.tribe-events-end-datetime")
        if end_el:
            end_dt, _ = normalize_safe(end_el.get("title", "") or end_el.get_text())

        if not start_dt:
            # Fallback: extract "Date: <value>" and "Time: <value>" from meta block
            meta_block = soup.select_one(".tribe-events-event-meta, .tribe-events-meta-group")
            if meta_block:
                meta_text = meta_block.get_text(" ", strip=True)
                date_m = re.search(r"Date:\s*([\w]+,?\s+[\w]+\s+\d+,?\s+\d{4})", meta_text)
                time_m = re.search(r"Time:\s*([\d:]+\s*[apm]+\s*-\s*[\d:]+\s*[apm]+)", meta_text)
                if date_m:
                    date_str = date_m.group(1)
                    time_str = time_m.group(1).split("-")[0].strip() if time_m else ""
                    start_dt, _ = normalize_safe(f"{date_str} {time_str}".strip())
                    if time_m and " - " in time_m.group(1):
                        end_time_str = time_m.group(1).split("-")[1].strip()
                        end_dt, _ = normalize_safe(f"{date_str} {end_time_str}")

        # Location
        venue_el = soup.select_one(".tribe-venue")
        address_el = soup.select_one(".tribe-address")
        location_name = venue_el.get_text(strip=True) if venue_el else None
        location_address = address_el.get_text(" ", strip=True) if address_el else None
        lat, lon = get_coordinates(location_name, location_address)

        # Description
        desc_el = soup.select_one(
            ".tribe-events-single-event-description, "
            ".tribe-events-content"
        )
        description = desc_el.get_text(" ", strip=True) if desc_el else None

        # Registration / external link
        registration_url = None
        for reg_selector in [
            'a[href*="register"]',
            'a[href*="eventbrite"]',
            'a[href*="zoom"]',
        ]:
            reg_el = soup.select_one(reg_selector)
            if reg_el:
                registration_url = reg_el.get("href")
                break

        # Tags from TEC category links
        tags = [
            a.get_text(strip=True).lower()
            for a in soup.select(".tribe-cat-item a, .tribe-events-cat-item a")
        ]

        return {
            "title": title,
            "description": description or None,
            "short_description": (description or "")[:280] or None,
            "start_datetime": start_dt,
            "end_datetime": end_dt,
            "all_day": False,
            "location_name": location_name,
            "location_address": location_address,
            "latitude": lat,
            "longitude": lon,
            "registration_url": registration_url,
            "tags": tags,
        }
