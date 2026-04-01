"""
seed_departments.py — Populate the departments and categories tables.

Run once after the first migration:
  python scripts/seed_departments.py

Safe to re-run (uses upsert logic — skips rows that already exist).
"""

import sys
from pathlib import Path

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_db, SessionLocal
from app.models.department import Department
from app.models.category import Category

CATEGORIES = [
    {"name": "Lecture",  "slug": "lecture",  "color_hex": "#1D4ED8", "icon_name": "academic-cap"},
    {"name": "Workshop", "slug": "workshop", "color_hex": "#7C3AED", "icon_name": "wrench"},
    {"name": "Social",   "slug": "social",   "color_hex": "#059669", "icon_name": "users"},
    {"name": "Career",   "slug": "career",   "color_hex": "#D97706", "icon_name": "briefcase"},
    {"name": "Arts",     "slug": "arts",     "color_hex": "#DB2777", "icon_name": "musical-note"},
    {"name": "Other",    "slug": "other",    "color_hex": "#6B7280", "icon_name": "tag"},
]

# Add your department scrapers here.
# scraper_class must match the class name in app/scrapers/departments/<slug>.py
DEPARTMENTS = [
    {
        "name": "Economics",
        "slug": "economics",
        "school": "Columbia College / SIPA",
        "website_url": "https://econ.columbia.edu/events/",
        "scraper_class": "EconScraper",
        "scrape_interval_hours": 6,
    },
    {
        "name": "Psychology",
        "slug": "psychology",
        "school": "Columbia College / GSAS",
        "website_url": "https://psychology.columbia.edu/events",
        "scraper_class": "PsychologyScraper",
        "scrape_interval_hours": 6,
    },
    {
        "name": "Law School",
        "slug": "law",
        "school": "Columbia Law School",
        "website_url": "https://www.law.columbia.edu/events",
        "scraper_class": "LawScraper",
        "scrape_interval_hours": 6,
    },
    {
        "name": "SIPA",
        "slug": "sipa",
        "school": "School of International & Public Affairs",
        "website_url": "https://www.sipa.columbia.edu/communities-connections/events",
        "scraper_class": "SIPAScraper",
        "scrape_interval_hours": 6,
    },
    # Templates for future scrapers:
    # {
    #     "name": "Data Science Institute",
    #     "slug": "dsi",
    #     "school": "SEAS",
    #     "website_url": "https://datascience.columbia.edu/news-and-events/events/",
    #     "scraper_class": "DSIScraper",
    #     "scrape_interval_hours": 6,
    # },
]


def seed():
    init_db()
    db = SessionLocal()

    try:
        # Seed categories
        for cat_data in CATEGORIES:
            existing = db.query(Category).filter_by(slug=cat_data["slug"]).first()
            if not existing:
                db.add(Category(**cat_data))
                print(f"  [+] Category: {cat_data['name']}")
            else:
                print(f"  [=] Category already exists: {cat_data['name']}")

        # Seed departments
        for dept_data in DEPARTMENTS:
            existing = db.query(Department).filter_by(slug=dept_data["slug"]).first()
            if not existing:
                db.add(Department(**dept_data))
                print(f"  [+] Department: {dept_data['name']}")
            else:
                print(f"  [=] Department already exists: {dept_data['name']}")

        db.commit()
        print("\nSeeding complete.")

    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding database...")
    seed()
