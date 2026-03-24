"""
run_scraper.py — Manually trigger a scraper for one or all departments.

Usage:
  python scripts/run_scraper.py --dept cs
  python scripts/run_scraper.py --dept cs --dept economics
  python scripts/run_scraper.py --all
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_db


def run(slugs: list[str]):
    from app.scrapers.registry import get_scraper, get_all_scrapers

    if not slugs:
        print("No department slugs specified. Use --dept <slug> or --all.")
        return

    for slug in slugs:
        scraper = get_scraper(slug)
        if not scraper:
            print(f"[!] No scraper found for: {slug}")
            continue

        print(f"\n--- Scraping: {slug} ---")
        result = scraper.run()
        print(f"  Status   : {result.status}")
        print(f"  Found    : {result.events_found}")
        print(f"  New      : {result.events_new}")
        print(f"  Updated  : {result.events_updated}")
        if result.errors:
            print(f"  Errors ({len(result.errors)}):")
            for err in result.errors[:5]:
                print(f"    - {err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run department scrapers manually.")
    parser.add_argument("--dept", action="append", dest="slugs", metavar="SLUG",
                        help="Department slug to scrape (can specify multiple)")
    parser.add_argument("--all", action="store_true", help="Scrape all enabled departments")
    args = parser.parse_args()

    init_db()

    if args.all:
        from app.database import SessionLocal
        from app.models import Department
        db = SessionLocal()
        slugs = [d.slug for d in db.query(Department).filter_by(is_enabled=True).all()]
        db.close()
    else:
        slugs = args.slugs or []

    run(slugs)
