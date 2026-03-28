# In src/familybot/lib/itad_price_repository.py

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from familybot.config import ITAD_CACHE_TTL
from familybot.lib.database import get_db_connection, get_write_connection

logger = logging.getLogger(__name__)


def get_cached_itad_price(appid: str):
    """Get cached ITAD price data. Returns None if not found. Permanent cache never expires."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT lowest_price, lowest_price_formatted, shop_name, permanent,
                   current_price, current_price_formatted, discount_percent,
                   original_price, is_family_shared, steam_game_name, lookup_method
            FROM itad_price_cache
            WHERE appid = ? AND (permanent = 1 OR expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
        """,
            (appid,),
        )
        row = cursor.fetchone()
        if row:
            # Null-handling policy:
            # - Numeric fields (discount_percent): default to 0
            # - Boolean fields (permanent, is_family_shared): default to False
            # - Optional string fields (current_price, original_price, steam_game_name, lookup_method): preserve None
            return {
                "lowest_price": row["lowest_price"],
                "lowest_price_formatted": row["lowest_price_formatted"],
                "shop_name": row["shop_name"],
                "permanent": bool(row["permanent"])
                if row["permanent"] is not None
                else False,
                "current_price": row["current_price"],
                "current_price_formatted": row["current_price_formatted"],
                "discount_percent": row["discount_percent"]
                if row["discount_percent"] is not None
                else 0,
                "original_price": row["original_price"],
                "is_family_shared": bool(row["is_family_shared"])
                if row["is_family_shared"] is not None
                else False,
                "steam_game_name": row["steam_game_name"],
                "lookup_method": row["lookup_method"],
            }
        return None
    except Exception as e:
        logger.error(f"Error getting cached ITAD price for {appid}: {e}")
        return None


def _do_cache_itad_price(
    cursor: sqlite3.Cursor,
    appid: str,
    price_data: dict,
    permanent: bool,
    cache_hours: int,
    lookup_method: str,
    steam_game_name: str | None,
):
    """Internal: cache ITAD price using an existing cursor."""
    now = datetime.now(timezone.utc)
    if permanent:
        expires_at_str = None
        permanent_val = 1
    else:
        expires_at = now + timedelta(hours=cache_hours)
        expires_at_str = expires_at.isoformat().replace("+00:00", "Z")
        permanent_val = 0

    # Map steam_current_price fields to current_price if present
    # This allows populate_prices.py to inject Steam fallback prices
    current_price = price_data.get("steam_current_price") or price_data.get("current_price")
    current_price_formatted = price_data.get("steam_current_price_formatted") or price_data.get("current_price_formatted")

    cursor.execute(
        """
        INSERT OR REPLACE INTO itad_price_cache
        (appid, lowest_price, lowest_price_formatted, shop_name, lookup_method, steam_game_name,
         current_price, current_price_formatted, discount_percent, original_price, is_family_shared,
         cached_at, expires_at, permanent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            appid,
            price_data.get("lowest_price"),
            price_data.get("lowest_price_formatted"),
            price_data.get("shop_name"),
            lookup_method,
            steam_game_name,
            current_price,
            current_price_formatted,
            price_data.get("discount_percent") or 0,
            price_data.get("original_price"),
            price_data.get("is_family_shared"),
            now.isoformat().replace("+00:00", "Z"),
            expires_at_str,
            permanent_val,
        ),
    )
    cache_type = "permanently" if permanent else f"for {cache_hours} hours"
    logger.debug(f"Cached ITAD price for {appid} {cache_type}")


def cache_itad_price(
    appid: str,
    price_data: dict,
    permanent: bool = False,
    cache_hours: int = ITAD_CACHE_TTL,
    lookup_method: str = "appid",
    steam_game_name: str | None = None,
    conn: sqlite3.Connection | None = None,
):
    """Cache ITAD price data. If permanent=True, cache never expires (expires_at=NULL, permanent=1).

    If conn is supplied, the caller owns the write lock. Otherwise, acquires it internally.
    """
    if conn is not None:
        cursor = conn.cursor()
        _do_cache_itad_price(
            cursor,
            appid,
            price_data,
            permanent,
            cache_hours,
            lookup_method,
            steam_game_name,
        )
        conn.commit()
    else:
        with get_write_connection() as write_conn:
            cursor = write_conn.cursor()
            _do_cache_itad_price(
                cursor,
                appid,
                price_data,
                permanent,
                cache_hours,
                lookup_method,
                steam_game_name,
            )
            write_conn.commit()


def cache_itad_price_enhanced(
    appid: str,
    price_data: dict,
    lookup_method: str = "appid",
    steam_game_name: str | None = None,
    permanent: bool = True,
    cache_hours: int = 6,
    conn: sqlite3.Connection | None = None,
):
    """Wrapper for cache_itad_price to maintain compatibility."""
    cache_itad_price(
        appid,
        price_data,
        permanent=permanent,
        cache_hours=cache_hours,
        lookup_method=lookup_method,
        steam_game_name=steam_game_name,
        conn=conn,
    )