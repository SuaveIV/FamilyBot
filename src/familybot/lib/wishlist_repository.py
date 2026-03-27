# In src/familybot/lib/wishlist_repository.py

import logging
from datetime import datetime, timedelta, timezone

from familybot.config import WISHLIST_CACHE_TTL
from familybot.lib.database import get_db_connection, get_write_connection

logger = logging.getLogger(__name__)


def get_cached_wishlist(steam_id: str):
    """Get cached wishlist data if not expired, returns None if not found or expired."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT appid FROM wishlist_cache
            WHERE steam_id = ? AND expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
        """,
            (steam_id,),
        )
        rows = cursor.fetchall()
        if rows:
            return [row["appid"] for row in rows]
        return None
    except Exception as e:
        logger.error(f"Error getting cached wishlist for {steam_id}: {e}")
        return None


def cache_wishlist(steam_id: str, appids: list, cache_hours: int = WISHLIST_CACHE_TTL):
    """Cache user's wishlist for specified hours (wishlists change moderately)."""
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=cache_hours)

            # Clear existing cache for this user
            cursor.execute("DELETE FROM wishlist_cache WHERE steam_id = ?", (steam_id,))

            # Insert new cache entries
            cache_entries = [
                (
                    steam_id,
                    str(appid),
                    now.isoformat().replace("+00:00", "Z"),
                    expires_at.isoformat().replace("+00:00", "Z"),
                )
                for appid in appids
            ]
            cursor.executemany(
                """
                INSERT INTO wishlist_cache (steam_id, appid, cached_at, expires_at)
                VALUES (?, ?, ?, ?)
            """,
                cache_entries,
            )
            conn.commit()
            logger.debug(f"Cached {len(appids)} wishlist items for user {steam_id}")
    except Exception as e:
        logger.error(f"Error caching wishlist for {steam_id}: {e}")


def purge_wishlist_cache():
    """Purge all entries from the wishlist_cache table."""
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM wishlist_cache")
            conn.commit()
            logger.info("Purged all entries from wishlist_cache.")
    except Exception as e:
        logger.error(f"Error purging wishlist_cache: {e}")
