"""
rebuild_search_index.py — Wipe and rebuild the Whoosh search index from the database.

Run if the index gets corrupted or after a bulk data import:
  python scripts/rebuild_search_index.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_db

if __name__ == "__main__":
    init_db()
    from app.services.search_service import INDEX_DIR, rebuild_index
    from whoosh.index import create_in
    from app.services.search_service import _get_schema

    print(f"Rebuilding search index at {INDEX_DIR} ...")
    INDEX_DIR.mkdir(exist_ok=True)
    create_in(str(INDEX_DIR), _get_schema())  # wipe existing index
    rebuild_index()
    print("Done.")
