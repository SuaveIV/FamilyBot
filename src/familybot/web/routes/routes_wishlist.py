# In src/familybot/web/routes/wishlist.py
"""
Wishlist API endpoint.
Returns paginated wishlist entries with optional per-member filtering.
"""

import json
import logging
import sqlite3

from fastapi import APIRouter, Depends
from fastapi import Query

from familybot.web.dependencies import get_db
from familybot.web.models import WishlistItem

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/wishlist")
async def get_wishlist_summary(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    family_member_id: str | None = None,
    conn=Depends(get_db),
):
    """
    Return a paginated list of wishlist entries.

    When family_member_id is omitted, all members' wishlists are returned
    (including duplicates where the same game appears on multiple wishlists —
    the frontend groups these by appid and displays all interested names).
    """
    cursor = conn.cursor()
    offset = (page - 1) * limit

    try:
        if family_member_id:
            # Count unique appids for the specific member
            count_q = "SELECT COUNT(DISTINCT w.appid) FROM wishlist_cache w WHERE w.steam_id = ?"
            # Get unique appids for the specific member, then join to get details
            data_q = f"""
                SELECT w.appid, w.steam_id, g.name, g.price_data
                FROM (
                    SELECT DISTINCT w2.appid, w2.steam_id
                    FROM wishlist_cache w2
                    WHERE w2.steam_id = ?
                ) w
                LEFT JOIN game_details_cache g
                       ON w.appid = g.appid
                      AND (g.permanent = 1 OR g.expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
                ORDER BY g.name, w.steam_id
                LIMIT {limit} OFFSET {offset}
            """
            params: list = [family_member_id]
        else:
            # Count unique appids across all members
            count_q = "SELECT COUNT(DISTINCT w.appid) FROM wishlist_cache w"
            # Get unique appids across all members, then join to get details
            data_q = f"""
                SELECT w.appid, w.steam_id, g.name, g.price_data
                FROM (
                    SELECT DISTINCT w2.appid, w2.steam_id
                    FROM wishlist_cache w2
                ) w
                LEFT JOIN game_details_cache g
                       ON w.appid = g.appid
                      AND (g.permanent = 1 OR g.expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
                ORDER BY g.name, w.steam_id
                LIMIT {limit} OFFSET {offset}
            """
            params = []

        cursor.execute(count_q, params)
        total_items: int = cursor.fetchone()[0]

        cursor.execute(data_q, params)
        rows = cursor.fetchall()

    except sqlite3.OperationalError as exc:
        logger.warning("Wishlist query failed: %s", exc)
        return {"items": [], "total_items": 0}

    items = []
    for row in rows:
        price_data = None
        if row["price_data"]:
            try:
                price_data = json.loads(row["price_data"])
            except Exception:
                pass
        items.append(
            WishlistItem(
                appid=row["appid"],
                steam_id=row["steam_id"],
                game_name=row["name"],
                price_data=price_data,
            )
        )

    return {"items": items, "total_items": total_items}
