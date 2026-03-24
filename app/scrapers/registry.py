"""
registry.py — Auto-discovers all scraper classes in scrapers/departments/.

Adding a new department scraper requires only:
1. Create a file in app/scrapers/departments/<slug>.py
2. Define a class inheriting BaseScraper with department_slug set
3. Add/enable the department row in the database

No manual registration needed.
"""

import importlib
import inspect
import logging
from pathlib import Path

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

_registry: dict[str, type[BaseScraper]] = {}


def _discover():
    departments_dir = Path(__file__).parent / "departments"
    for path in departments_dir.glob("*.py"):
        if path.stem.startswith("_"):
            continue
        module_name = f"app.scrapers.departments.{path.stem}"
        try:
            module = importlib.import_module(module_name)
            for _, cls in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(cls, BaseScraper)
                    and cls is not BaseScraper
                    and cls.department_slug
                ):
                    _registry[cls.department_slug] = cls
                    logger.debug("Registered scraper: %s -> %s", cls.department_slug, cls.__name__)
        except Exception as exc:
            logger.warning("Failed to import scraper module %s: %s", module_name, exc)


def get_scraper(slug: str) -> BaseScraper | None:
    if not _registry:
        _discover()
    cls = _registry.get(slug)
    return cls() if cls else None


def get_all_scrapers() -> dict[str, BaseScraper]:
    if not _registry:
        _discover()
    return {slug: cls() for slug, cls in _registry.items()}
