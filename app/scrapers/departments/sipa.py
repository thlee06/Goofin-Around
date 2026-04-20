from __future__ import annotations

"""
sipa.py — Columbia SIPA events scraper.

Listing page: https://www.sipa.columbia.edu/communities-connections/events

Actual card structure (verified via live DOM inspection):

    <section class="cc--component-container cc--events-card">
      <div class="c--component c--events-card">
        <div class="date-block">
          <div class="month">APRIL</div>
          <div class="day">18</div>
          <div class="day-of-week">SAT</div>
        </div>
        <div class="text-container">
          <div class="f--field f--cta-title">
            <h3><a href="https://...external or internal...">Title</a></h3>
          </div>
          <div class="event-details">
            <div class="time">8:30 a.m. - 6:30 p.m.</div>
            <div class="location">Butler 523</div>
          </div>
        </div>
        <div class="image-container">
          <img src="..." />
        </div>
      </div>
    </section>

IMPORTANT: SIPA event links frequently go to external sites (Eventbrite, Zoom, etc.).
We therefore extract ALL data from the listing page and store the link as source_url.
We override run() to avoid making HTTP requests to external event platforms.
"""

import logging
import re
from datetime import datetime, date

from app.scrapers.base import BaseScraper, ScrapeResult
from app.scrapers.utils.date_parser import normalize_safe
from app.scrapers.utils.location import get_coordinates

logger = logging.getLogger(__name__)

BASE = "https://www.sipa.columbia.edu"
EVENTS_PATH = "/communities-connections/events"

# SIPA shows month + day but no year. We infer the year: if the month has
# already passed this calendar year, assume next year.
_MONTH_MAP = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
    "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
    "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}


class SIPAScraper(BaseScraper):
    department_slug = "sipa"
    base_url = BASE + EVENTS_PATH
    use_playwright = False

    # ------------------------------------------------------------------
    # Override run() — all data lives on the listing page, not detail pages
    # ------------------------------------------------------------------

    def run(self) -> ScrapeResult:
        from datetime import timezone
        from app.database import SessionLocal
        from app.models import Department, ScrapeRun
        from app.scrapers.utils.deduplication import compute_external_id, upsert_event

        result = ScrapeResult(department_slug=self.department_slug)
        db = SessionLocal()
        scrape_run = None

        try:
            dept = db.query(Department).filter_by(slug=self.department_slug).first()
            if not dept:
                logger.error("Department not found: %s", self.department_slug)
                result.status = "failed"
                return result

            scrape_run = ScrapeRun(
                department_id=dept.id,
                started_at=datetime.now(timezone.utc),
                status="running",
            )
            db.add(scrape_run)
            db.commit()
            db.refresh(scrape_run)

            events = self._scrape_listing()
            result.events_found = len(events)

            for event_data in events:
                try:
                    event_data["department_id"] = dept.id
                    event_data["scrape_run_id"] = scrape_run.id
                    event_data["external_id"] = compute_external_id(
                        event_data.get("source_url", ""),
                        event_data.get("title", ""),
                    )
                    is_new = upsert_event(db, event_data)
                    if is_new:
                        result.events_new += 1
                    else:
                        result.events_updated += 1
                except Exception as exc:
                    msg = f"Error upserting '{event_data.get('title','')}': {exc}"
                    logger.warning(msg)
                    result.errors.append(msg)

            result.status = "success" if not result.errors else "partial"

        except Exception as exc:
            logger.exception("SIPA scraper failed")
            result.status = "failed"
            result.errors.append(str(exc))

        finally:
            if scrape_run:
                from datetime import timezone as tz
                scrape_run.completed_at = datetime.now(tz.utc)
                scrape_run.status = result.status
                scrape_run.events_found = result.events_found
                scrape_run.events_new = result.events_new
                scrape_run.events_updated = result.events_updated
                scrape_run.error_message = "\n".join(result.errors) or None
                if scrape_run.started_at:
                    delta = datetime.now(tz.utc) - scrape_run.started_at.replace(tzinfo=tz.utc)
                    scrape_run.duration_seconds = delta.total_seconds()

                dept_obj = db.query(Department).filter_by(slug=self.department_slug).first()
                if dept_obj:
                    dept_obj.last_scraped_at = datetime.now(tz.utc)
                db.commit()
            db.close()

        try:
            from app.services.search_service import reindex_recent
            reindex_recent()
        except Exception:
            pass

        return result

    # ------------------------------------------------------------------
    # Listing page parser — extracts all events in one pass
    # ------------------------------------------------------------------

    def _scrape_listing(self) -> list[dict]:
        html = self._fetch(self.base_url)
        if not html:
            return []

        soup = self._soup(html)
        cards = soup.select("section.cc--component-container.cc--events-card")
        logger.info("sipa: found %d event cards on listing page", len(cards))

        events = []
        for card in cards:
            event = self._parse_card(card)
            if event:
                events.append(event)
        return events

    def _parse_card(self, card) -> dict | None:
        # Title + source URL
        link = card.select_one("h3 a")
        if not link:
            return None
        title = link.get_text(strip=True)
        if not title:
            return None
        source_url = link.get("href", "") or self.base_url
        if source_url.startswith("/"):
            source_url = BASE + source_url

        # Date — month name (uppercase) + day number; infer year
        month_el = card.select_one(".date-block .month")
        day_el   = card.select_one(".date-block .day")
        start_dt = end_dt = None
        if month_el and day_el:
            month_str = month_el.get_text(strip=True).upper()
            day_str   = day_el.get_text(strip=True)
            month_num = _MONTH_MAP.get(month_str)
            if month_num and day_str.isdigit():
                year = _infer_year(month_num, int(day_str))
                date_str = f"{month_str.capitalize()} {day_str}, {year}"

                # Time
                time_el = card.select_one(".event-details .time")
                time_str = time_el.get_text(strip=True) if time_el else ""

                if " - " in time_str:
                    start_raw, end_raw = time_str.split(" - ", 1)
                    start_dt, _ = normalize_safe(f"{date_str} {start_raw.strip()}")
                    end_dt, _   = normalize_safe(f"{date_str} {end_raw.strip()}")
                else:
                    start_dt, _ = normalize_safe(f"{date_str} {time_str}".strip())

        # Location
        loc_el = card.select_one(".event-details .location")
        location_name = loc_el.get_text(strip=True) if loc_el else None
        location_name = _expand_sipa_room(location_name)
        lat, lon = get_coordinates(location_name) if location_name else (None, None)

        # Image
        img = card.select_one(".image-container img")
        image_url = img.get("src") if img else None
        if image_url and image_url.startswith("/"):
            image_url = BASE + image_url

        # Registration: if link points to Zoom/Eventbrite/external, it's also the reg URL
        is_external = source_url.startswith("http") and BASE not in source_url
        registration_url = source_url if is_external else None

        return {
            "title": title,
            "description": None,
            "short_description": None,
            "start_datetime": start_dt,
            "end_datetime": end_dt,
            "all_day": False,
            "location_name": location_name,
            "latitude": lat,
            "longitude": lon,
            "source_url": source_url,
            "image_url": image_url,
            "registration_url": registration_url,
            "is_free": None,
            "tags": [],
        }

    # BaseScraper requires these even though we override run()
    def get_event_urls(self) -> list[str]:
        return []

    def parse_event(self, html: str, url: str) -> dict:
        return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_year(month_num: int, day: int) -> int:
    """Return the most likely year for a future or current-month event."""
    today = date.today()
    candidate = date(today.year, month_num, day)
    if candidate < today:
        return today.year + 1
    return today.year


_SIPA_ROOMS = {
    r"\bIAB\b": "International Affairs Building",
    r"\bJG\b":  "Jerome Greene Hall",
    r"\bSIPA\b": "SIPA Building",
}


def _expand_sipa_room(raw: str | None) -> str | None:
    if not raw:
        return None
    result = raw
    for pattern, full_name in _SIPA_ROOMS.items():
        result = re.sub(pattern, full_name, result)
    return result
