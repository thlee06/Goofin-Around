"""
example.py — Template for writing a new department scraper.

Copy this file, rename it to match the department slug (e.g., cs.py),
and implement get_event_urls() and parse_event().

Then add a row to the departments table via scripts/seed_departments.py.
"""

from app.scrapers.base import BaseScraper
from app.scrapers.utils.date_parser import normalize_safe
from app.scrapers.utils.location import get_coordinates


class ExampleDepartmentScraper(BaseScraper):
    department_slug = "example"
    base_url = "https://example.columbia.edu/events"
    use_playwright = False  # Set True if the site loads events via JavaScript

    def get_event_urls(self) -> list[str]:
        """
        Fetch the events index page and return a list of URLs
        to individual event detail pages.
        """
        html = self._fetch(self.base_url)
        if not html:
            return []
        soup = self._soup(html)

        urls = []
        for link in soup.select("a.event-link"):  # UPDATE this CSS selector
            href = link.get("href", "")
            if href:
                if not href.startswith("http"):
                    href = self.base_url.rstrip("/") + "/" + href.lstrip("/")
                urls.append(href)
        return urls

    def parse_event(self, html: str, url: str) -> dict:
        """
        Parse a single event detail page and return a dict of event fields.
        Only 'title' is required; all other fields are optional.
        """
        soup = self._soup(html)

        title = soup.select_one("h1.event-title")  # UPDATE selector
        if not title:
            return {}

        raw_date = soup.select_one(".event-date")  # UPDATE selector
        start_dt, tz_flag = normalize_safe(raw_date.get_text() if raw_date else "")

        location_el = soup.select_one(".event-location")  # UPDATE selector
        location_name = location_el.get_text(strip=True) if location_el else None
        lat, lon = get_coordinates(location_name) if location_name else (None, None)

        description_el = soup.select_one(".event-description")  # UPDATE selector
        description = description_el.get_text(strip=True) if description_el else None

        return {
            "title": title.get_text(strip=True),
            "description": description,
            "short_description": (description or "")[:280] or None,
            "start_datetime": start_dt,
            "timezone_flag": "non-ET" if tz_flag else None,
            "location_name": location_name,
            "latitude": lat,
            "longitude": lon,
        }
