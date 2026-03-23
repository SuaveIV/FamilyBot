# In src/familybot/web/routes/cache.py
"""
Cache inspection and purge endpoints.
"""

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from familybot.lib.database import cleanup_expired_cache, get_db_connection
from familybot.web.dependencies import get_db
from familybot.web.models import CacheStats, CommandResponse
from familybot.web.state import update_last_activity

logger = logging.getLogger(__name__)
router = APIRouter()

_CACHE_TABLES = {
    "game_details": "game_details_cache",
    "user_games": "user_games_cache",
    "wishlist": "wishlist_cache",
    "family_library": "family_library_cache",
    "itad_prices": "itad_price_cache",
    "discord_users": "discord_users_cache",
}

_PURGE_TABLE_MAP = {
    "games": "game_details_cache",
    "wishlist": "wishlist_cache",
    "family": "family_library_cache",
    "prices": "itad_price_cache",
}


@router.get("/api/cache/stats", response_model=CacheStats)
async def get_cache_stats(conn=Depends(get_db)):
    cursor = conn.cursor()
    stats = {}
    for key, table in _CACHE_TABLES.items():
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            stats[key] = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            stats[key] = 0
    return CacheStats(**stats)


@router.post("/api/cache/purge", response_model=CommandResponse)
async def purge_cache(cache_type: str = "all"):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if cache_type == "all":
            for table in _CACHE_TABLES.values():
                cursor.execute(f"DELETE FROM {table}")
            message = "All cache data purged successfully"

        elif cache_type == "expired":
            conn.close()
            cleanup_expired_cache()
            update_last_activity()
            return CommandResponse(
                success=True, message="Expired cache entries cleaned up"
            )

        elif cache_type in _PURGE_TABLE_MAP:
            cursor.execute(f"DELETE FROM {_PURGE_TABLE_MAP[cache_type]}")
            message = f"{cache_type.title()} cache purged successfully"

        else:
            conn.close()
            raise HTTPException(
                status_code=400, detail=f"Unknown cache_type: {cache_type!r}"
            )

        conn.commit()
        update_last_activity()
        return CommandResponse(success=True, message=message)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error purging cache (type=%s)", cache_type)
        return CommandResponse(success=False, message=f"Error purging cache: {exc}")
    finally:
        conn.close()
