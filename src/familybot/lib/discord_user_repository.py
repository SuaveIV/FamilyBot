# In src/familybot/lib/discord_user_repository.py

import logging
from datetime import datetime, timedelta, timezone

from familybot.lib.database import get_db_connection, get_write_connection

logger = logging.getLogger(__name__)


def get_cached_discord_user(discord_id: str):
    """Get cached Discord user info if not expired, returns None if not found or expired."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT username FROM discord_users_cache
            WHERE discord_id = ? AND expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
        """,
            (discord_id,),
        )
        row = cursor.fetchone()
        if row:
            return row["username"]
        return None
    except Exception as e:
        logger.error(f"Error getting cached Discord user for {discord_id}: {e}")
        return None


def cache_discord_user(discord_id: str, username: str, cache_hours: int = 1):
    """Cache Discord user info for specified hours."""
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=cache_hours)

            cursor.execute(
                """
                INSERT OR REPLACE INTO discord_users_cache
                (discord_id, username, cached_at, expires_at)
                VALUES (?, ?, ?, ?)
            """,
                (
                    discord_id,
                    username,
                    now.isoformat().replace("+00:00", "Z"),
                    expires_at.isoformat().replace("+00:00", "Z"),
                ),
            )
            conn.commit()
            logger.debug(f"Cached Discord user {discord_id}: {username}")
    except Exception as e:
        logger.error(f"Error caching Discord user {discord_id}: {e}")
