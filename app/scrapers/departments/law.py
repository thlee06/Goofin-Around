from __future__ import annotations

"""
law.py — Columbia Law School events scraper.

Listing page: https://www.law.columbia.edu/events?page=N
Structure: Drupal static HTML.

Actual card structure (verified via live DOM inspection):

    <article class="event--item">
      <div class="grid-x grid-padding-x">
        <div class="cell--event-date">
          <div class="date-block">
            <div class="date-block__month">Apr</div>
            <div class="date-block__number">20</div>
            <div class="date-block__year">2026</div>
          </div>
        </div>
        <div class="cell--event-text">
          <h2 class="event__title">
            <a href="/events/[slug]"><span>Title</span></a>
          </h2>
          <div class="event__details--practical">
            <span class="event__time"><i ...></i><span>Mon, 9:10 a.m. - 10:00 a.m.</span></span>
            <span class="event__location"><i ...></i><span>Online\tZoom</span></span>
          </div>
          <div class="event__details--categorical">
            <ul>topic links</ul>
          </div>
        </div>
      </div>
    </article>

We collect all data from the listing (date, time, location, topics, title, URL),
then visit each detail page only to retrieve the description.
"""

import logging
import re

from app.scrapers.base import BaseScraper
from app.scrapers.utils.date_parser import normalize_safe
from app.scrapers.utils.location import get_coordinates

logger = logging.getLogger(__name__)

BASE = "https://www.law.columbia.edu"
MAX_PAGES = 10


class LawScraper(BaseScraper):
    department_slug = "law"
    base_url = f"{BASE}/events"
    use_playwright = False

    def __init__(self):
        super().__init__()
        self._listing_cache: dict[str, dict] = {}

    def get_event_urls(self) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        for page_num in range(MAX_PAGES):
            page_url = f"{self.base_url}?page={page_num}" if page_num else self.base_url
            html = self._fetch(page_url)
            if not html:
                break

            soup = self._soup(html)
            cards = soup.select("article.event--item")
            if not cards:
                break

            for card in cards:
                link = card.select_one("h2.event__title a, h2 a[href^='/events/']")
                if not link:
                    continue
                href = link.get("href", "")
                if not href or not href.startswith("/events/"):
                    continue
                full_url = BASE + href
                if full_url in seen:
                    continue
                seen.add(full_url)
                urls.append(full_url)
                self._listing_cache[full_url] = self._parse_card(card, link)

            if len(cards) < 5:
                break  # Last page

        logger.info("law: found %d events across %d pages", len(urls), page_num + 1)
        return urls

    def parse_event(self, html: str, url: str) -> dict:
        soup = self._soup(html)
        base = self._listing_cache.get(url, {})

        # Title: prefer h1 on detail page, fall back to listing cache
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else base.get("title", "")
        if not title:
            return {}

        description = self._extract_description(soup)

        return {
            "title": title,
            "description": description or None,
            "short_description": (description or "")[:280] or None,
            "start_datetime": base.get("start_datetime"),
            "end_datetime": base.get("end_datetime"),
            "all_day": base.get("all_day", False),
            "location_name": base.get("location_name"),
            "latitude": base.get("latitude"),
            "longitude": base.get("longitude"),
            "is_free": True,
            "tags": base.get("tags", []),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_card(self, card, link) -> dict:
        """Extract all available metadata from a listing-page article card."""
        result: dict = {"title": link.get_text(strip=True)}

        # Date
        month = card.select_one(".date-block__month")
        day   = card.select_one(".date-block__number")
        year  = card.select_one(".date-block__year")
        date_str = ""
        if month and day and year:
            date_str = f"{month.get_text(strip=True)} {day.get_text(strip=True)}, {year.get_text(strip=True)}"

        # Time — .event__time contains an <i> icon then a <span> with the text
        time_str = ""
        time_el = card.select_one(".event__time")
        if time_el:
            spans = time_el.find_all("span")
            time_str = spans[-1].get_text(strip=True) if spans else time_el.get_text(strip=True)

        result["all_day"] = "all day" in time_str.lower()

        if date_str:
            # Strip day-of-week prefix e.g. "Mon, " from time string
            clean_time = re.sub(r"^[A-Za-z]{2,3},\s*", "", time_str)
            start_time = clean_time.split(" - ")[0].strip()
            end_time   = clean_time.split(" - ")[1].strip() if " - " in clean_time else ""

            start_dt, _ = normalize_safe(f"{date_str} {start_time}")
            result["start_datetime"] = start_dt
            if end_time:
                end_dt, _ = normalize_safe(f"{date_str} {end_time}")
                result["end_datetime"] = end_dt

        # Location — .event__location has icon + span with text (may contain a tab)
        loc_el = card.select_one(".event__location")
        if loc_el:
            spans = loc_el.find_all("span")
            raw_loc = spans[-1].get_text(strip=True) if spans else loc_el.get_text(strip=True)
            # "Online\tZoom" → "Online – Zoom"; strip address suffix for display
            loc_display = raw_loc.replace("\t", " – ")
            loc_clean = re.sub(r",?\s*\d+\s+\w[\w\s\.]+(?:Ave|St|Blvd|Rd|Dr)\..*", "", loc_display).strip(", ")
            result["location_name"] = loc_clean or loc_display
            lat, lon = get_coordinates(loc_clean or loc_display, raw_loc)
            result["latitude"] = lat
            result["longitude"] = lon

        # Topics/tags
        topics = card.select(".event__topics li a")
        result["tags"] = [a.get_text(strip=True).lower() for a in topics]

        return result

    def _extract_description(self, soup) -> str | None:
        # Drupal body field selectors
        for sel in [".field--name-body", ".field-name-body", ".event__body", ".event-description"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(" ", strip=True)
                if len(text) > 50:
                    return text

        # "About This Event" section fallback
        about = soup.find(string=re.compile(r"about this event", re.I))
        if about:
            texts = []
            for sib in about.parent.next_siblings:
                t = getattr(sib, "get_text", lambda **k: str(sib))(strip=True)
                if t:
                    texts.append(t)
            if texts:
                return " ".join(texts)[:2000]

        # Grab first substantial paragraph from main content
        main = soup.find("main") or soup.find("article") or soup.body
        if main:
            for p in main.find_all("p"):
                text = p.get_text(strip=True)
                if len(text) > 100:
                    return text
        return None
