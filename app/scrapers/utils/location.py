"""
Location utilities: map location name strings to lat/lon coordinates.

Strategy (in order):
1. Check location_overrides.json for known Columbia building names.
2. If GEOCODIO_API_KEY is set, call Geocodio for unknown addresses.
3. Return (None, None) for "Zoom", "TBA", room-only strings, and failures.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_OVERRIDES_PATH = Path(__file__).parent.parent.parent.parent / "data" / "location_overrides.json"
_overrides_cache: Optional[dict] = None

# Strings that will never geocode — return None immediately
_VIRTUAL_PATTERNS = re.compile(
    r"\b(zoom|virtual|online|webinar|tba|tbd|teams|webex)\b", re.IGNORECASE
)
# Room-only strings like "Room 301" or "Pupin 301" without a street address
_ROOM_ONLY = re.compile(r"^(room\s*\d+|[a-z\s]+\s+\d{3,4})$", re.IGNORECASE)


def get_coordinates(location_name: str, location_address: Optional[str] = None) -> tuple[Optional[float], Optional[float]]:
    """
    Returns (latitude, longitude) or (None, None).
    Geocodes at most once per unique address (callers should persist the result).
    """
    if not location_name and not location_address:
        return None, None

    query = location_address or location_name

    # Skip virtual / TBA locations immediately
    if _VIRTUAL_PATTERNS.search(query):
        return None, None

    # Skip bare room numbers
    if _ROOM_ONLY.match(query.strip()):
        return None, None

    # 1. Check manual overrides
    overrides = _load_overrides()
    key = location_name.strip().lower() if location_name else ""
    if key in overrides:
        entry = overrides[key]
        return entry["lat"], entry["lon"]

    # 2. Try Geocodio
    from app.config import get_settings
    settings = get_settings()
    if settings.GEOCODIO_API_KEY:
        return _geocodio(query, settings.GEOCODIO_API_KEY)

    return None, None


def _load_overrides() -> dict:
    global _overrides_cache
    if _overrides_cache is not None:
        return _overrides_cache
    if _OVERRIDES_PATH.exists():
        try:
            with open(_OVERRIDES_PATH) as f:
                _overrides_cache = json.load(f)
        except Exception as exc:
            logger.warning("Failed to load location_overrides.json: %s", exc)
            _overrides_cache = {}
    else:
        _overrides_cache = {}
    return _overrides_cache


def _geocodio(address: str, api_key: str) -> tuple[Optional[float], Optional[float]]:
    try:
        import requests
        resp = requests.get(
            "https://api.geocod.io/v1.7/geocode",
            params={"q": address, "api_key": api_key, "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if results:
            loc = results[0]["location"]
            return loc["lat"], loc["lng"]
    except Exception as exc:
        logger.warning("Geocodio failed for %r: %s", address, exc)
    return None, None
