# In src/familybot/web/routes/routes_common_games.py
"""
Common Games API endpoint.
Returns games owned by multiple family members.
"""

import json
import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from familybot.web.dependencies import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


class PriceData(BaseModel):
    initial: Optional[int] = None
    final: Optional[int] = None
    discount_percent: Optional[int] = None
    is_free: Optional[bool] = None


class CommonGameItem(BaseModel):
    appid: int
    game_name: str
    owner_count: int
    owner_steam_ids: list[str]
    price_data: Optional[PriceData] = None
    is_multiplayer: Optional[bool] = None
    is_coop: Optional[bool] = None
    is_free: Optional[bool] = None
    has_game_details: bool


class CommonGamesResponse(BaseModel):
    items: list[CommonGameItem]
    total_items: int


@router.get("/api/common-games", response_model=CommonGamesResponse)
def get_common_games(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    min_owners: int = Query(2, ge=1, le=20),
    sort: str = Query("name", regex="^(name|owners)$"),
    conn=Depends(get_db),
):
    """
    Return a paginated list of games owned by multiple family members.

    - min_owners: Minimum number of members who own the game (default 2)
    - sort: Sort by 'name' (alphabetical) or 'owners' (most owners first)
    """
    cursor = conn.cursor()
    offset = (page - 1) * limit

    try:
        # Count games with at least min_owners owners
        count_q = """
            SELECT COUNT(*) FROM (
                SELECT appid
                FROM user_games_cache
                WHERE expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
                GROUP BY appid
                HAVING COUNT(DISTINCT steam_id) >= ?
            )
        """

        # Get games with owner count and details
        if sort == "owners":
            order_clause = "owner_count DESC, g.name"
        else:
            order_clause = "g.name"

        data_q = (
            """
            SELECT
                ugc.appid,
                COUNT(DISTINCT ugc.steam_id) as owner_count,
                GROUP_CONCAT(DISTINCT ugc.steam_id) as owner_steam_ids,
                g.name,
                g.price_data,
                g.is_multiplayer,
                g.is_coop,
                g.is_free
            FROM user_games_cache ugc
            LEFT JOIN game_details_cache g
                   ON ugc.appid = g.appid
                  AND (g.permanent = 1 OR g.expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
            WHERE ugc.expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
            GROUP BY ugc.appid
            HAVING COUNT(DISTINCT ugc.steam_id) >= ?
            ORDER BY """
            + order_clause
            + """
            LIMIT ? OFFSET ?
        """
        )

        cursor.execute(count_q, (min_owners,))
        total_items: int = cursor.fetchone()[0]

        cursor.execute(data_q, (min_owners, limit, offset))
        rows = cursor.fetchall()

    except sqlite3.OperationalError as exc:
        logger.warning("Common games query failed: %s", exc)
        return {"items": [], "total_items": 0}

    items = []
    for row in rows:
        price_data = None
        if row["price_data"]:
            try:
                price_data = json.loads(row["price_data"])
            except json.JSONDecodeError as exc:
                logger.debug(
                    "Failed to parse price_data for appid %s: %r — raw: %s",
                    row["appid"],
                    exc,
                    row["price_data"],
                )

        owner_steam_ids = []
        if row["owner_steam_ids"]:
            owner_steam_ids = row["owner_steam_ids"].split(",")

        has_game_details = row["name"] is not None

        items.append(
            {
                "appid": row["appid"],
                "game_name": row["name"] or "",
                "owner_count": row["owner_count"],
                "owner_steam_ids": owner_steam_ids,
                "price_data": price_data,
                "is_multiplayer": bool(row["is_multiplayer"])
                if row["is_multiplayer"] is not None
                else None,
                "is_coop": bool(row["is_coop"]) if row["is_coop"] is not None else None,
                "is_free": bool(row["is_free"]) if row["is_free"] is not None else None,
                "has_game_details": has_game_details,
            }
        )

    return {"items": items, "total_items": total_items}
