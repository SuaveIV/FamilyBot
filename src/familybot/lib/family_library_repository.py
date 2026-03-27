# In src/familybot/lib/family_library_repository.py

import logging
import json
from datetime import datetime, timedelta, timezone

from familybot.config import FAMILY_LIBRARY_CACHE_TTL
from familybot.lib.database import get_db_connection, get_write_connection

logger = logging.getLogger(__name__)


def get_cached_family_library():
    """Get cached family library data if not expired, returns None if not found or expired."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT appid, owner_steamids, exclude_reason FROM family_library_cache
            WHERE expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
        """,
            (),
        )
        rows = cursor.fetchall()
        if rows:
            family_apps = []
            for row in rows:
                family_apps.append(
                    {
                        "appid": int(row["appid"]),
                        "owner_steamids": json.loads(row["owner_steamids"])
                        if row["owner_steamids"]
                        else [],
                        "exclude_reason": row["exclude_reason"],
                    }
                )
            return family_apps
        return None
    except Exception as e:
        logger.error(f"Error getting cached family library: {e}")
        return None


def cache_family_library(
    family_apps: list, cache_hours: int = FAMILY_LIBRARY_CACHE_TTL
):
    """Cache family library data for specified hours (updates infrequently)."""
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=cache_hours)

            # Clear existing cache
            cursor.execute("DELETE FROM family_library_cache")

            # Insert new cache entries
            cache_entries = []
            for app in family_apps:
                cache_entries.append(
                    (
                        str(app.get("appid")),
                        json.dumps(app.get("owner_steamids", [])),
                        app.get("exclude_reason"),
                        now.isoformat().replace("+00:00", "Z"),
                        expires_at.isoformat().replace("+00:00", "Z"),
                    )
                )

            cursor.executemany(
                """
                INSERT INTO family_library_cache (appid, owner_steamids, exclude_reason, cached_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                cache_entries,
            )
            conn.commit()
            logger.debug(
                f"Cached {len(family_apps)} family library apps for {cache_hours} hours"
            )
    except Exception as e:
        logger.error(f"Error caching family library: {e}")


def purge_family_library_cache():
    """Purge all entries from the family_library_cache table."""
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM family_library_cache")
            conn.commit()
            logger.info("Purged all entries from family_library_cache.")
    except Exception as e:
        logger.error(f"Error purging family_library_cache: {e}")
