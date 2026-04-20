from __future__ import annotations

"""
cs.py — Columbia Computer Science Department events scraper.

Source: https://www.cs.columbia.edu/calendar/

All event data is embedded directly in static HTML — no detail pages needed.
Each event is an <a class="event-item"> element containing month, day, title,
time, location, and a short abstract inline.

Actual structure (verified):

    <a class="event-item" data-news="2219" data-toggle="modal" href="#event2219">
      <div class="row">
        <div class="col-xs-3">
          <div class="date">
            <span class="month">Apr</span>
            <span class="day">21</span>
          </div>
        </div>
        <div class="col-md-9">
          <h4 class="event-title">Scalable Image AI via Self-Designing Storage</h4>
          <p class="time">Tuesday 12:00 pm</p>
          <p class="location">CSB 453</p>
          <p class="abstract small">Utku Sirin, Harvard University</p>
        </div>
      </div>
    </a>

The page only shows upcoming events (no pagination needed).
Year is inferred from the month: if the month has already passed this calendar
year, we assume next year.
"""

import logging
import re
from datetime import date, datetime

from app.scrapers.base import BaseScraper, ScrapeResult
from app.scrapers.utils.date_parser import normalize_safe
from app.scrapers.utils.location import get_coordinates

logger = logging.getLogger(__name__)

BASE = "https://www.cs.columbia.edu"

_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


class CSScraper(BaseScraper):
    department_slug = "cs"
    base_url = f"{BASE}/calendar/"
    use_playwright = False

    # All data is on the listing page — override run() to skip HTTP fetches per event
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
                    result.errors.append(str(exc))

            result.status = "success" if not result.errors else "partial"

        except Exception as exc:
            logger.exception("CS scraper failed")
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

    def _scrape_listing(self) -> list[dict]:
        html = self._fetch(self.base_url)
        if not html:
            return []

        soup = self._soup(html)
        items = soup.select("a.event-item")
        logger.info("cs: found %d events on calendar page", len(items))

        events = []
        for item in items:
            event = self._parse_item(item)
            if event:
                events.append(event)
        return events

    def _parse_item(self, item) -> dict | None:
        title_el = item.select_one(".event-title")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        if not title:
            return None

        # Date
        month_el = item.select_one(".date .month")
        day_el   = item.select_one(".date .day")
        start_dt = end_dt = None

        if month_el and day_el:
            month_str = month_el.get_text(strip=True).lower()[:3]
            day_str   = day_el.get_text(strip=True)
            month_num = _MONTH_ABBR.get(month_str)
            if month_num and day_str.isdigit():
                year = _infer_year(month_num, int(day_str))
                # Time element: "Tuesday 12:00 pm" — strip day-of-week prefix
                time_el = item.select_one(".time")
                time_str = time_el.get_text(strip=True) if time_el else ""
                time_clean = re.sub(r"^[A-Za-z]+\s+", "", time_str)  # strip "Tuesday "
                date_str = f"{month_str.capitalize()} {day_str}, {year}"
                start_dt, _ = normalize_safe(f"{date_str} {time_clean}".strip())

        # Location
        loc_el = item.select_one(".location")
        location_name = loc_el.get_text(strip=True) if loc_el else None
        lat, lon = get_coordinates(location_name) if location_name else (None, None)

        # Abstract / description (often speaker + institution)
        abstract_el = item.select_one(".abstract")
        description = abstract_el.get_text(strip=True) if abstract_el else None

        # Source URL — use event anchor with news ID if available
        news_id = item.get("data-news", "")
        source_url = f"{self.base_url}#event{news_id}" if news_id else self.base_url

        return {
            "title": title,
            "description": description or None,
            "short_description": description[:280] if description else None,
            "start_datetime": start_dt,
            "end_datetime": None,
            "all_day": False,
            "location_name": location_name,
            "latitude": lat,
            "longitude": lon,
            "source_url": source_url,
            "is_free": True,
            "tags": ["lecture", "seminar"],
        }

    # Required by BaseScraper ABC (never called since we override run())
    def get_event_urls(self) -> list[str]:
        return []

    def parse_event(self, html: str, url: str) -> dict:
        return {}


def _infer_year(month_num: int, day: int) -> int:
    today = date.today()
    candidate = date(today.year, month_num, day)
    if candidate < today:
        return today.year + 1
    return today.year
