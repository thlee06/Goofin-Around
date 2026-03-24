import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class ScrapeResult:
    department_slug: str
    events_found: int = 0
    events_new: int = 0
    events_updated: int = 0
    errors: list[str] = field(default_factory=list)
    status: str = "success"  # "success" | "partial" | "failed"


class BaseScraper(ABC):
    """
    Abstract base class for all department scrapers.

    Subclasses must define:
      - department_slug: str
      - base_url: str
      - get_event_urls() -> list[str]
      - parse_event(html, url) -> dict

    Optionally override:
      - use_playwright = True  (for JS-rendered sites)
    """

    department_slug: str = ""
    base_url: str = ""
    use_playwright: bool = False

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": settings.SCRAPER_USER_AGENT})

    # ------------------------------------------------------------------
    # Public entry point called by the scheduler
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

            event_urls = self._safe_get_event_urls()
            result.events_found = len(event_urls)

            for url in event_urls:
                try:
                    html = self._fetch(url)
                    if not html:
                        continue
                    event_data = self.parse_event(html, url)
                    if not event_data:
                        continue
                    event_data["department_id"] = dept.id
                    event_data["scrape_run_id"] = scrape_run.id
                    event_data.setdefault("source_url", url)
                    event_data["external_id"] = compute_external_id(
                        event_data.get("source_url", url),
                        event_data.get("title", ""),
                    )
                    is_new = upsert_event(db, event_data)
                    if is_new:
                        result.events_new += 1
                    else:
                        result.events_updated += 1
                except Exception as exc:
                    msg = f"Error parsing {url}: {exc}"
                    logger.warning(msg)
                    result.errors.append(msg)

            result.status = "success" if not result.errors else "partial"

        except Exception as exc:
            logger.exception("Scraper failed for %s", self.department_slug)
            result.status = "failed"
            result.errors.append(str(exc))

        finally:
            if scrape_run:
                scrape_run.completed_at = datetime.now(timezone.utc)
                scrape_run.status = result.status
                scrape_run.events_found = result.events_found
                scrape_run.events_new = result.events_new
                scrape_run.events_updated = result.events_updated
                scrape_run.error_message = "\n".join(result.errors) or None
                if scrape_run.started_at:
                    delta = datetime.now(timezone.utc) - scrape_run.started_at.replace(tzinfo=timezone.utc)
                    scrape_run.duration_seconds = delta.total_seconds()

                from app.models import Department as Dept
                dept = db.query(Dept).filter_by(slug=self.department_slug).first()
                if dept:
                    dept.last_scraped_at = datetime.now(timezone.utc)

                db.commit()

            db.close()

        # Re-index new/updated events in Whoosh
        try:
            from app.services.search_service import reindex_recent
            reindex_recent()
        except Exception:
            pass

        return result

    # ------------------------------------------------------------------
    # Methods subclasses must implement
    # ------------------------------------------------------------------

    @abstractmethod
    def get_event_urls(self) -> list[str]:
        """Return list of URLs to individual event pages."""

    @abstractmethod
    def parse_event(self, html: str, url: str) -> dict:
        """
        Parse a single event page's HTML and return a dict with fields
        matching the Event model. Required keys: title.
        """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_get_event_urls(self) -> list[str]:
        try:
            return self.get_event_urls()
        except Exception as exc:
            logger.exception("get_event_urls() failed for %s: %s", self.department_slug, exc)
            return []

    def _fetch(self, url: str) -> str | None:
        time.sleep(settings.SCRAPER_REQUEST_DELAY_SECONDS)
        if self.use_playwright:
            return self._fetch_with_playwright(url)
        try:
            resp = self._session.get(url, timeout=15)
            if resp.status_code == 404:
                logger.debug("404 for %s — skipping", url)
                return None
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            logger.warning("HTTP error fetching %s: %s", url, exc)
            return None

    def _fetch_with_playwright(self, url: str) -> str | None:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=30000)
                html = page.content()
                browser.close()
                return html
        except Exception as exc:
            logger.warning("Playwright error for %s: %s", url, exc)
            return None

    def _soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    @staticmethod
    def _make_external_id(source_url: str, title: str) -> str:
        return hashlib.sha256(f"{source_url}|{title}".encode()).hexdigest()
