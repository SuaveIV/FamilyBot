"""Repository for caching Steam AppID to ITAD ID mappings."""

import logging
import sqlite3
from datetime import datetime, timezone

from familybot.lib.database import get_db_connection, get_write_connection

logger = logging.getLogger(__name__)

# Safe limit below SQLITE_MAX_VARIABLE_NUMBER (999)
MAX_CHUNK_SIZE = 900


def get_cached_itad_id(appid: str) -> str | None:
    """Get cached ITAD ID for a Steam AppID. Returns None if not found."""
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT itad_id FROM steam_itad_mapping WHERE appid = ?",
            (appid,),
        )
        row = cursor.fetchone()
        return row["itad_id"] if row else None
    except Exception as e:
        logger.error(f"Error getting cached ITAD ID for {appid}: {e}")
        return None
    finally:
        if cursor is not None:
            cursor.close()


def get_cached_itad_ids_bulk(appids: list[str]) -> dict[str, str]:
    """Get cached ITAD IDs for multiple Steam AppIDs in one query.

    Returns dict of appid -> itad_id for only the found entries.
    Chunked to respect SQLITE_MAX_VARIABLE_NUMBER (default 999).
    """
    if not appids:
        return {}

    result = {}
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Process appids in chunks to avoid exceeding SQLite variable limit
        for i in range(0, len(appids), MAX_CHUNK_SIZE):
            chunk = appids[i : i + MAX_CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk))
            cursor.execute(
                f"SELECT appid, itad_id FROM steam_itad_mapping WHERE appid IN ({placeholders})",
                chunk,
            )
            result.update({row["appid"]: row["itad_id"] for row in cursor.fetchall()})

        return result
    except Exception as e:
        logger.error(f"Error getting cached ITAD IDs in bulk: {e}")
        return {}
    finally:
        if cursor is not None:
            cursor.close()


def cache_itad_mapping(
    appid: str, itad_id: str, conn: sqlite3.Connection | None = None
):
    """Cache a single Steam AppID to ITAD ID mapping."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _do_insert(cursor: sqlite3.Cursor):
        cursor.execute(
            "INSERT OR REPLACE INTO steam_itad_mapping (appid, itad_id, mapped_at) VALUES (?, ?, ?)",
            (appid, itad_id, now),
        )

    if conn is not None:
        _do_insert(conn.cursor())
        # Caller owns the connection and transaction; do not commit here
    else:
        with get_write_connection() as write_conn:
            _do_insert(write_conn.cursor())
            write_conn.commit()

    logger.debug(f"Cached ITAD mapping: {appid} -> {itad_id}")


def bulk_cache_itad_mappings(
    mappings: dict[str, str], conn: sqlite3.Connection | None = None
) -> int:
    """Cache multiple Steam AppID to ITAD ID mappings at once.

    Returns number of mappings cached.
    """
    if not mappings:
        return 0

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _do_bulk_insert(cursor: sqlite3.Cursor):
        cursor.executemany(
            "INSERT OR REPLACE INTO steam_itad_mapping (appid, itad_id, mapped_at) VALUES (?, ?, ?)",
            [(appid, itad_id, now) for appid, itad_id in mappings.items()],
        )

    if conn is not None:
        _do_bulk_insert(conn.cursor())
        # Caller owns the connection and transaction; do not commit here
    else:
        with get_write_connection() as write_conn:
            _do_bulk_insert(write_conn.cursor())
            write_conn.commit()

    logger.debug(f"Cached {len(mappings)} ITAD mappings")
    return len(mappings)
