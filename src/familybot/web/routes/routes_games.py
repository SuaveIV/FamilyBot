# In src/familybot/web/routes/games.py
"""
Game-related API endpoints:
  - Family library listing
  - Recently added games
  - Batch Steam game-info lookup (name + cover art)
"""

import asyncio
import logging

import aiohttp
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from familybot.lib.database import (
    cache_game_details,
    get_cached_family_library,
    get_cached_game_details,
)
from familybot.web.dependencies import get_db
from familybot.web.models import GameDetails

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Family library ────────────────────────────────────────────────────────────


@router.get("/api/family-library", response_model=list[GameDetails])
async def get_family_library(limit: int = 50):
    """Return cached family library games with their cached details."""
    limit = max(0, min(limit, 200))
    family_apps = get_cached_family_library()
    if not family_apps:
        return []

    games = []
    for app in family_apps[:limit]:
        appid = str(app["appid"])
        details = get_cached_game_details(appid)
        if details:
            games.append(
                GameDetails(
                    appid=appid,
                    name=details.get("name"),
                    type=details.get("type"),
                    is_free=details.get("is_free", False),
                    categories=details.get("categories", []),
                    price_data=details.get("price_data"),
                    is_multiplayer=details.get("is_multiplayer", False),
                    is_coop=details.get("is_coop", False),
                    is_family_shared=details.get("is_family_shared", False),
                )
            )
    return games


# ── Recent games ──────────────────────────────────────────────────────────────


@router.get("/api/recent-games", response_model=list[GameDetails])
async def get_recent_games(limit: int = 10, conn=Depends(get_db)):
    """Return the most recently detected family library additions."""
    import json

    # Clamp limit to prevent negative or huge values
    limit = max(1, min(limit, 100))

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT s.appid, s.detected_at,
                   g.name, g.type, g.is_free, g.categories,
                   g.price_data, g.is_multiplayer, g.is_coop, g.is_family_shared
            FROM saved_games s
            LEFT JOIN game_details_cache g ON s.appid = g.appid
            ORDER BY s.detected_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
    except Exception:
        return []

    games = []
    for row in rows:
        categories = []
        price_data = None
        if row["categories"]:
            try:
                categories = json.loads(row["categories"])
            except Exception:
                pass
        if row["price_data"]:
            try:
                price_data = json.loads(row["price_data"])
            except Exception:
                pass

        games.append(
            GameDetails(
                appid=row["appid"],
                name=row["name"],
                type=row["type"],
                is_free=bool(row["is_free"]) if row["is_free"] is not None else False,
                categories=categories,
                price_data=price_data,
                is_multiplayer=bool(row["is_multiplayer"])
                if row["is_multiplayer"] is not None
                else False,
                is_coop=bool(row["is_coop"]) if row["is_coop"] is not None else False,
                is_family_shared=bool(row["is_family_shared"])
                if row["is_family_shared"] is not None
                else False,
            )
        )
    return games


# ── Batch game-info (name + cover art) ───────────────────────────────────────


class GameInfoBatchRequest(BaseModel):
    appids: list[str]


class GameInfoItem(BaseModel):
    appid: str
    name: str | None = None
    header_image: str  # always populated — Steam CDN URL


@router.post("/api/game-info/batch", response_model=dict[str, GameInfoItem])
async def get_game_info_batch(body: GameInfoBatchRequest):
    """
    Return name + cover-art URL for up to 50 Steam App IDs.

    Hits game_details_cache first; fetches from the Steam Store API for
    anything missing, caches the results permanently, then returns the
    full set. The frontend uses this to progressively enrich wishlist cards.
    """
    appids = [str(a) for a in body.appids[:50]]
    results: dict[str, GameInfoItem] = {}
    to_fetch: list[str] = []

    # Cache pass
    for appid in appids:
        cached = get_cached_game_details(appid)
        if cached and cached.get("name"):
            results[appid] = GameInfoItem(
                appid=appid,
                name=cached["name"],
                header_image=_cdn_url(appid),
            )
        else:
            to_fetch.append(appid)

    if not to_fetch:
        return results

    # Steam Store API pass
    semaphore = asyncio.Semaphore(5)

    async def fetch_one(
        session: aiohttp.ClientSession, appid: str
    ) -> tuple[str, GameInfoItem]:
        async with semaphore:
            try:
                url = (
                    f"https://store.steampowered.com/api/appdetails"
                    f"?appids={appid}&cc=us&l=en&filters=basic,price_overview"
                )
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        raise ValueError(f"HTTP {resp.status}")
                    data = await resp.json(content_type=None)

                game_data = data.get(str(appid), {}).get("data")
                if game_data:
                    cache_game_details(appid, game_data, permanent=True)
                    return appid, GameInfoItem(
                        appid=appid,
                        name=game_data.get("name"),
                        header_image=game_data.get("header_image") or _cdn_url(appid),
                    )
            except Exception as exc:
                logger.debug("game-info/batch: failed for %s: %s", appid, exc)

        return appid, GameInfoItem(appid=appid, name=None, header_image=_cdn_url(appid))

    async with aiohttp.ClientSession() as session:
        fetched = await asyncio.gather(*[fetch_one(session, a) for a in to_fetch])

    for appid, info in fetched:
        results[appid] = info

    return results


def _cdn_url(appid: str) -> str:
    return f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"
