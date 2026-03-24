"""
search_service.py — Whoosh full-text search index management.

Index schema: id, title (boosted), description, department, tags
Index lives at search_index/ (gitignored, on Railway persistent volume).

Startup check: if the index directory is empty/missing, rebuild from DB.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

INDEX_DIR = Path("search_index")


def _get_schema():
    from whoosh.fields import Schema, ID, TEXT, KEYWORD, STORED
    return Schema(
        id=ID(stored=True, unique=True),
        title=TEXT(stored=True),
        description=TEXT(stored=False),
        department=KEYWORD(stored=True),
        tags=KEYWORD(stored=True, commas=True),
    )


def ensure_index():
    """
    Called at app startup. Creates the index if it doesn't exist,
    or rebuilds it from the database if the directory exists but is empty/corrupted.
    """
    from whoosh.index import create_in, open_dir, exists_in
    INDEX_DIR.mkdir(exist_ok=True)

    if not exists_in(str(INDEX_DIR)):
        logger.info("Search index not found — creating and rebuilding from database")
        create_in(str(INDEX_DIR), _get_schema())
        rebuild_index()
    else:
        logger.info("Search index found at %s", INDEX_DIR)


def rebuild_index():
    """Rebuild the entire Whoosh index from the database. Safe to run at any time."""
    from whoosh.index import open_dir
    from app.database import SessionLocal
    from app.models.event import Event
    from app.models.department import Department

    db = SessionLocal()
    try:
        ix = open_dir(str(INDEX_DIR))
        writer = ix.writer()
        events = db.query(Event).filter_by(is_active=True).join(Department).all()
        for event in events:
            _add_to_writer(writer, event)
        writer.commit()
        logger.info("Search index rebuilt with %d events", len(events))
    finally:
        db.close()


def reindex_recent():
    """
    Add/update only recently scraped events. Called after each scrape run.
    Uses update_document() which handles both new and existing docs.
    """
    from whoosh.index import open_dir, exists_in
    from app.database import SessionLocal
    from app.models.event import Event
    from datetime import datetime, timedelta, timezone

    if not exists_in(str(INDEX_DIR)):
        return

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        events = db.query(Event).filter(Event.updated_at >= cutoff, Event.is_active == True).all()
        if not events:
            return
        ix = open_dir(str(INDEX_DIR))
        writer = ix.writer()
        for event in events:
            _add_to_writer(writer, event, update=True)
        writer.commit()
        logger.debug("Reindexed %d recently updated events", len(events))
    finally:
        db.close()


def search_events(db, query_str: str, limit: int = 50) -> list:
    """
    Full-text search. Returns Event ORM objects ordered by relevance.
    Falls back to empty list on any Whoosh error.
    """
    from whoosh.index import open_dir, exists_in
    from whoosh.qparser import MultifieldParser, OrGroup
    from app.models.event import Event

    if not query_str.strip() or not exists_in(str(INDEX_DIR)):
        return []

    try:
        ix = open_dir(str(INDEX_DIR))
        with ix.searcher() as searcher:
            parser = MultifieldParser(
                ["title", "description", "department", "tags"],
                schema=ix.schema,
                group=OrGroup,
            )
            q = parser.parse(query_str)
            results = searcher.search(q, limit=limit)
            ids = [int(r["id"]) for r in results]

        if not ids:
            return []

        # Fetch ORM objects, preserving relevance order
        events_by_id = {e.id: e for e in db.query(Event).filter(Event.id.in_(ids)).all()}
        return [events_by_id[i] for i in ids if i in events_by_id]

    except Exception as exc:
        logger.warning("Search error for %r: %s", query_str, exc)
        return []


def _add_to_writer(writer, event, update: bool = False):
    tags = ",".join(event.tags) if event.tags else ""
    dept_name = event.department.name if event.department else ""
    kwargs = dict(
        id=str(event.id),
        title=event.title or "",
        description=event.description or "",
        department=dept_name,
        tags=tags,
    )
    if update:
        writer.update_document(**kwargs)
    else:
        writer.add_document(**kwargs)
