"""
scheduler.py — APScheduler setup.

Runs one scraping job per enabled department, on the interval defined
in department.scrape_interval_hours.

IMPORTANT: This scheduler runs in-process alongside the FastAPI web server.
The app must always be deployed with a single uvicorn worker (--workers 1).
Running multiple workers will cause each worker to run its own scheduler,
resulting in duplicate scrape runs.
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone="America/New_York")


def _run_department_scraper(slug: str):
    from app.scrapers.registry import get_scraper
    scraper = get_scraper(slug)
    if not scraper:
        logger.warning("No scraper found for department slug: %s", slug)
        return
    logger.info("Starting scheduled scrape for: %s", slug)
    result = scraper.run()
    logger.info(
        "Scrape complete for %s: %d new, %d updated, status=%s",
        slug, result.events_new, result.events_updated, result.status
    )


def _load_jobs():
    from app.database import SessionLocal
    from app.models import Department

    db = SessionLocal()
    try:
        departments = db.query(Department).filter_by(is_enabled=True).all()
        for dept in departments:
            _scheduler.add_job(
                _run_department_scraper,
                trigger=IntervalTrigger(hours=dept.scrape_interval_hours),
                args=[dept.slug],
                id=f"scrape_{dept.slug}",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=600,
            )
            logger.info(
                "Scheduled scraper for %s every %d hours",
                dept.slug, dept.scrape_interval_hours
            )
    finally:
        db.close()


def start_scheduler():
    _load_jobs()
    _scheduler.start()
    logger.info("APScheduler started with %d jobs", len(_scheduler.get_jobs()))


def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
