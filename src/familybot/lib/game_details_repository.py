# In src/familybot/lib/game_details_repository.py

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from familybot.config import GAME_DETAILS_CACHE_TTL
from familybot.lib.database import get_db_connection, get_write_connection

logger = logging.getLogger(__name__)

# --- Normalization Constants ---
_NORMALIZED_DEFAULTS = {
    "name": "Unknown",
    "type": "unknown",
    "is_free": False,
    "categories": [],
    "price_overview": None,
    "is_multiplayer": False,
    "is_coop": False,
    "is_family_shared": False,
}

_NORMALIZED_KEYS = frozenset(_NORMALIZED_DEFAULTS.keys())


def _analyze_game_categories(categories: list) -> tuple[bool, bool, bool]:
    """Analyze Steam categories to determine multiplayer, co-op, and family sharing status."""
    is_multiplayer = False
    is_coop = False
    is_family_shared = False

    for cat in categories:
        cat_id = cat.get("id")
        if cat_id == 1:  # Multi-player
            is_multiplayer = True
        elif cat_id == 36:  # Online Multi-Player
            is_multiplayer = True
        elif cat_id == 38:  # Online Co-op
            is_multiplayer = True
            is_coop = True
        elif cat_id == 62:  # Family Sharing
            is_family_shared = True

    return is_multiplayer, is_coop, is_family_shared


def get_cached_game_details(appid: str):
    """Get cached game details. Returns None if not found. Permanent cache never expires."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT name, type, is_free, categories, price_data, permanent,
                   is_multiplayer, is_coop, is_family_shared
            FROM game_details_cache
            WHERE appid = ? AND (permanent = 1 OR expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
        """,
            (appid,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "name": row["name"],
                "type": row["type"],
                "is_free": bool(row["is_free"]),
                "categories": json.loads(row["categories"])
                if row["categories"]
                else [],
                "price_overview": json.loads(row["price_data"])
                if row["price_data"]
                else None,
                "is_multiplayer": bool(row["is_multiplayer"])
                if row["is_multiplayer"] is not None
                else False,
                "is_coop": bool(row["is_coop"])
                if row["is_coop"] is not None
                else False,
                "is_family_shared": bool(row["is_family_shared"])
                if row["is_family_shared"] is not None
                else False,
            }
        return None
    except Exception as e:
        logger.error(f"Error getting cached game details for {appid}: {e}")
        return None


def _do_cache_game_details(
    cursor: sqlite3.Cursor,
    appid: str,
    game_data: dict,
    permanent: bool,
    cache_hours: int | None,
    price_source: str,
):
    """Internal: cache game details using an existing cursor."""
    now = datetime.now(timezone.utc)
    expires_at_str = None
    if not permanent and cache_hours:
        expires_at = now + timedelta(hours=cache_hours)
        expires_at_str = expires_at.isoformat().replace("+00:00", "Z")

    categories = game_data.get("categories", [])
    is_multiplayer, is_coop, is_family_shared = _analyze_game_categories(categories)

    cursor.execute(
        """
        INSERT OR REPLACE INTO game_details_cache
        (appid, name, type, is_free, categories, price_data, is_multiplayer, is_coop, is_family_shared, price_source, cached_at, expires_at, permanent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            appid,
            game_data.get("name"),
            game_data.get("type"),
            game_data.get("is_free", False),
            json.dumps(categories),
            json.dumps(game_data.get("price_overview"))
            if game_data.get("price_overview")
            else None,
            1 if is_multiplayer else 0,
            1 if is_coop else 0,
            1 if is_family_shared else 0,
            price_source,
            now.isoformat().replace("+00:00", "Z"),
            expires_at_str,
            1 if permanent else 0,
        ),
    )
    cache_type = "permanently" if permanent else f"for {cache_hours} hours"
    logger.debug(
        f"Cached game details for {appid} {cache_type} (MP:{is_multiplayer}, Coop:{is_coop}, FS:{is_family_shared})"
    )


def cache_game_details(
    appid: str,
    game_data: dict,
    permanent: bool = True,
    cache_hours: int | None = GAME_DETAILS_CACHE_TTL,
    price_source: str = "store_api",
    conn: sqlite3.Connection | None = None,
):
    """Cache game details permanently by default, or for specified hours if permanent=False.

    If conn is supplied, the caller owns the write lock. Otherwise, acquires it internally.
    """
    if conn is not None:
        cursor = conn.cursor()
        _do_cache_game_details(
            cursor, appid, game_data, permanent, cache_hours, price_source
        )
        conn.commit()
    else:
        with get_write_connection() as write_conn:
            cursor = write_conn.cursor()
            _do_cache_game_details(
                cursor, appid, game_data, permanent, cache_hours, price_source
            )
            write_conn.commit()


def force_update_game_cache(appid: str, game_data: dict):
    """Force update cached game details even if they already exist."""
    cache_game_details(appid, game_data, permanent=False)
    logger.info(f"Force updated cache for game {appid}")


def normalize_game_data(raw: dict) -> dict:
    """Normalize game data from any source into a consistent shape.

    Ensures all consumers get a predictable dict structure regardless of
    whether data came from the Steam Store API or from the cache.

    Returns a dict with these guaranteed keys:
        - name: str
        - type: str
        - is_free: bool
        - categories: list
        - price_overview: dict | None
        - is_multiplayer: bool
        - is_coop: bool
        - is_family_shared: bool
    """
    if raw is None:
        return dict(_NORMALIZED_DEFAULTS)

    # If already fully normalized (has all guaranteed keys), return as-is
    if _NORMALIZED_KEYS.issubset(raw):
        return raw

    # Merge raw into defaults so missing fields are filled
    categories = raw.get("categories", [])
    is_multiplayer, is_coop, is_family_shared = _analyze_game_categories(categories)

    return {
        "name": raw.get("name", "Unknown"),
        "type": raw.get("type", "unknown"),
        "is_free": bool(raw.get("is_free", False)),
        "categories": categories,
        "price_overview": raw.get("price_overview"),
        "is_multiplayer": is_multiplayer,
        "is_coop": is_coop,
        "is_family_shared": is_family_shared,
    }


def cache_game_details_with_source(
    app_id: str, game_data: dict, source: str, conn: sqlite3.Connection | None = None
):
    """Wrapper for cache_game_details to maintain compatibility."""
    cache_game_details(
        app_id, game_data, permanent=False, price_source=source, conn=conn
    )
