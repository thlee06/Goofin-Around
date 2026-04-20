from __future__ import annotations

"""
dsi.py — Columbia Data Science Institute events scraper.

Source: https://datascience.columbia.edu/wp-json/tribe/events/v1/events

DSI runs WordPress with The Events Calendar (TEC) plugin, which exposes
a clean REST API. We use the API directly instead of scraping HTML.

API endpoint: /wp-json/tribe/events/v1/events
  ?per_page=N   — number of events per request (max 50)
  ?page=N        — pagination
  ?status=publish

Event object key fields:
  title, description, excerpt, url
  start_date, end_date          (local ET: "2026-04-20 12:00:00")
  all_day
  cost                          (empty string = free)
  image.url                     (featured image)
  categories[].name
  tags[].name
  venue.venue, venue.address, venue.city, venue.state, venue.zip

No Playwright or HTML parsing needed.
"""

import logging
from datetime import datetime, timezone

import requests

from app.scrapers.base import BaseScraper, ScrapeResult
from app.scrapers.utils.date_parser import normalize_safe
from app.scrapers.utils.location import get_coordinates

logger = logging.getLogger(__name__)

BASE        = "https://datascience.columbia.edu"
API_URL     = f"{BASE}/wp-json/tribe/events/v1/events"
PER_PAGE    = 50
MAX_PAGES   = 20


class DSIScraper(BaseScraper):
    department_slug = "dsi"
    base_url        = f"{BASE}/news-and-events/events/"
    use_playwright  = False

    # ------------------------------------------------------------------
    # Override run() to use REST API instead of HTML scraping
    # ------------------------------------------------------------------

    def run(self) -> ScrapeResult:
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

            events = self._fetch_all_events()
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
                    logger.warning("DSI upsert error: %s", exc)

            result.status = "success" if not result.errors else "partial"

        except Exception as exc:
            logger.exception("DSI scraper failed")
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
    # API fetch
    # ------------------------------------------------------------------

    def _fetch_all_events(self) -> list[dict]:
        all_events: list[dict] = []

        for page in range(1, MAX_PAGES + 1):
            try:
                resp = self._session.get(
                    API_URL,
                    params={"per_page": PER_PAGE, "page": page, "status": "publish"},
                    timeout=15,
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                logger.warning("DSI API error on page %d: %s", page, exc)
                break

            data = resp.json()
            raw_events = data.get("events", [])
            if not raw_events:
                break

            for raw in raw_events:
                parsed = self._parse_api_event(raw)
                if parsed:
                    all_events.append(parsed)

            # TEC API returns total_pages in the response
            total_pages = data.get("total_pages", 1)
            if page >= total_pages:
                break

        logger.info("dsi: fetched %d events from API", len(all_events))
        return all_events

    def _parse_api_event(self, raw: dict) -> dict | None:
        title = (raw.get("title") or "").strip()
        if not title:
            return None

        # Dates — API returns local ET strings: "2026-04-20 12:00:00"
        start_dt, _ = normalize_safe(raw.get("start_date", "") or "")
        end_dt, _   = normalize_safe(raw.get("end_date", "") or "")

        # Description — strip HTML tags
        import re
        raw_desc = raw.get("description") or raw.get("excerpt") or ""
        description = re.sub(r"<[^>]+>", " ", raw_desc).strip()
        description = re.sub(r"\s+", " ", description)

        # Cost — empty string means free; "$10" means paid
        cost_raw = (raw.get("cost") or "").strip()
        is_free = (cost_raw == "" or cost_raw.lower() in ("free", "0", "$0"))

        # Venue
        venue = raw.get("venue") or {}
        location_name = (venue.get("venue") or "").strip() or None
        if venue and not location_name:
            location_name = venue.get("address", "") or None

        location_address = None
        if venue:
            parts = [
                venue.get("address", ""),
                venue.get("city", ""),
                venue.get("state", ""),
                venue.get("zip", ""),
            ]
            addr = ", ".join(p for p in parts if p)
            location_address = addr or None

        lat, lon = get_coordinates(location_name, location_address)

        # Image
        image_data = raw.get("image") or {}
        image_url = image_data.get("url") if isinstance(image_data, dict) else None

        # Categories and tags
        cats = [c.get("name", "") for c in (raw.get("categories") or []) if c.get("name")]
        tags_raw = [t.get("name", "") for t in (raw.get("tags") or []) if t.get("name")]
        tags = [t.lower() for t in cats + tags_raw if t]

        return {
            "title": title,
            "description": description or None,
            "short_description": (description or "")[:280] or None,
            "start_datetime": start_dt,
            "end_datetime": end_dt,
            "all_day": bool(raw.get("all_day", False)),
            "location_name": location_name,
            "location_address": location_address,
            "latitude": lat,
            "longitude": lon,
            "source_url": raw.get("url") or self.base_url,
            "image_url": image_url,
            "is_free": is_free,
            "tags": tags,
        }

    # Required by ABC
    def get_event_urls(self) -> list[str]:
        return []

    def parse_event(self, html: str, url: str) -> dict:
        return {}
