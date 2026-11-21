"""Wishlist message formatting and the Steam Family game list URL."""

import asyncio
import json
import logging
import random

import aiohttp

from familybot.config import (
    FAMILY_STEAM_ID,  # Import FAMILY_USER_DICT here
    FAMILY_USER_DICT,
)
from familybot.lib.itad_service import get_lowest_price
from familybot.lib.token_manager import get_token  # <<< IMPORT get_token here

# Setup logging for this specific module
logger = logging.getLogger(__name__)


def get_family_game_list_url() -> str:
    """Generate the URL for the Steamworks GetSharedLibraryApps API using webapi_token."""
    token = get_token()  # Retrieve the webapi_token
    if not token:
        logger.error(
            "webapi_token is empty or not available. Cannot fetch family game list."
        )
        # Consider raising an error to be caught by the calling function
        msg = "webapi_token is missing or invalid."
        raise ValueError(msg)

    # Use 'access_token' parameter with the webapi_token for this specific endpoint
    url_family_list = (
        f"https://api.steampowered.com/IFamilyGroupsService/GetSharedLibraryApps/v1/"
        f"?access_token={token}"  # <<< Changed back to access_token={token}
        f"&family_groupid={FAMILY_STEAM_ID}"
        f"&include_own=true"  # Changed to true to include games you own in the shared library list
        f"&include_free=false"
        f"&language=french"
        f"&format=json"
    )
    logger.debug(f"Generated family game list URL: {url_family_list}")
    return url_family_list


_STEAM_APPDETAILS_URL = (
    "https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=fr"
)

# How many Steam Store and ITAD lookups to keep in flight at once. The loop these
# replace was fully sequential: one round trip per game, ~200 ms against the real store,
# so a 200-game wishlist spent more than a minute waiting on sockets.
_DETAILS_CONCURRENCY = 8
_ITAD_CONCURRENCY = 5

# Steam answers 429 when a burst is wider than it likes. These mirror the retry policy in
# SteamAPIManager.make_request_with_retry: exponential backoff with jitter, so a burst
# degrades into a slow response instead of a wall of "Unknown Game" lines.
_MAX_ATTEMPTS = 3
_BASE_BACKOFF = 1.0

# Jitter that desynchronises the retries of concurrent requests. SystemRandom keeps the
# security linters quiet without a suppression; the cost is a few microseconds.
_rng = random.SystemRandom()


async def _get_appdetails_json(session: aiohttp.ClientSession, app_id: str) -> dict:
    """GET appdetails for one app, retrying 429 with backoff and jitter.

    Non-429 failures raise, so the caller maps them to the same "Unknown Game" suffixes it
    always did.
    """
    url = _STEAM_APPDETAILS_URL.format(app_id=app_id)

    for attempt in range(_MAX_ATTEMPTS):
        retry_after: float | None = None
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status == 429 and attempt < _MAX_ATTEMPTS - 1:
                retry_after = _BASE_BACKOFF * (2**attempt) + _rng.uniform(0, 1)
                logger.warning(
                    f"Rate limited (429) fetching app details for {app_id}, retrying in "
                    f"{retry_after:.1f}s (attempt {attempt + 1}/{_MAX_ATTEMPTS})"
                )
            else:
                response.raise_for_status()
                return json.loads(await response.text())

        if retry_after is not None:
            await asyncio.sleep(retry_after)

    return {}


async def _fetch_app_details(
    session: aiohttp.ClientSession, app_id: str, limiter: asyncio.Semaphore
) -> tuple[dict | None, str | None]:
    """Fetch one app's store details.

    Returns ``(data, None)`` on success, or ``(None, reason)`` where ``reason`` is the
    parenthetical shown on the "Unknown Game" line.
    """
    payload: dict = {}
    async with limiter:
        try:
            payload = await _get_appdetails_json(session, app_id)

            if payload.get(app_id, {}).get("success"):
                return payload[app_id]["data"], None

            logger.warning(
                f"App details success false for AppID {app_id} in format_message."
                f" Response: {payload}"
            )
            return None, "Details Unavailable"
        except aiohttp.ClientError as e:
            logger.error(
                f"Request error fetching app details for {app_id} in format_message: {e}"
            )
            return None, "API Error"
        except json.JSONDecodeError as e:
            logger.error(
                f"JSON decode error for app details {app_id} in format_message: {e}."
            )
            return None, "Data Error"
        except KeyError as e:
            logger.error(
                f"Missing key in app details for {app_id} in format_message: {e}."
                f" Response: {payload}"
            )
            return None, "Format Error"
        except Exception as e:
            logger.critical(
                f"Unexpected error fetching app details for {app_id} in format_message: {e}",
                exc_info=True,
            )
            return None, "Unexpected Error"


async def _fetch_lowest_price(app_id: str, limiter: asyncio.Semaphore) -> tuple[str, str]:
    """Return the historical-low message line for one game, paired with its app id."""
    async with limiter:
        try:
            lowest_price = await asyncio.to_thread(get_lowest_price, int(app_id))
            return app_id, f"   The lowest price ever was {lowest_price}$ \n"
        except Exception as e:
            logger.warning(f"Could not get lowest price for {app_id}: {e}")
            return app_id, "   Lowest price info unavailable. \n"


def _dedupe_app_ids(wishlist: list) -> list[str]:
    """Return every app id once, in wishlist order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for item in wishlist:
        app_id = str(item[0])
        if app_id not in seen:
            seen.add(app_id)
            ordered.append(app_id)
    return ordered


async def _prefetch_details(
    session: aiohttp.ClientSession, app_ids: list[str], cache: dict
) -> dict[str, str]:
    """Fetch store details into ``cache``; return app id -> failure reason."""
    if not app_ids:
        return {}

    limiter = asyncio.Semaphore(_DETAILS_CONCURRENCY)
    results = await asyncio.gather(
        *(_fetch_app_details(session, app_id, limiter) for app_id in app_ids)
    )

    failures: dict[str, str] = {}
    for app_id, (data, reason) in zip(app_ids, results, strict=True):
        if data is None:
            failures[app_id] = reason or "Unexpected Error"
        else:
            cache[app_id] = data
    return failures


async def _prefetch_lowest_prices(app_ids: list[str]) -> dict[str, str]:
    """Fetch historical lows; return app id -> rendered message line."""
    if not app_ids:
        return {}

    limiter = asyncio.Semaphore(_ITAD_CONCURRENCY)
    fetched = await asyncio.gather(
        *(_fetch_lowest_price(app_id, limiter) for app_id in app_ids)
    )
    return dict(fetched)


def _render_game_block(
    item: tuple, game_info_data: dict, lowest_price_line: str, short: bool
) -> list[str]:
    """Render one game's link, price, per-person split and historical low."""
    app_id = str(item[0])
    parts: list[str] = []

    game_name = game_info_data.get("name", f"Unknown Game ({app_id})")
    parts.append(f"[{game_name}](<https://store.steampowered.com/app/{app_id}>) \n")

    price_overview = game_info_data.get("price_overview")
    if price_overview and price_overview.get("discount_percent") != 0:
        final_formatted = price_overview.get("final_formatted", "N/A")
        discount_percent = price_overview.get("discount_percent", 0)
        parts.append(
            f"  **__The game is on sale at {final_formatted} (-{discount_percent}%)__** \n"
        )
    else:
        final_formatted = (
            price_overview.get("final_formatted", "N/A") if price_overview else "N/A"
        )
        parts.append(f"  The game is at {final_formatted} \n")

    if short:
        return parts

    final_price = price_overview.get("final") if price_overview else None
    if final_price is not None and item[1]:
        price_per_person = round(final_price / 100 / len(item[1]), 2)
        parts.append(f" which is {price_per_person}$ per person \n")

    parts.append(lowest_price_line)
    return parts


async def _apply_length_limits(
    message_parts: list[str], wishlist: list, cached_data: dict, short: bool
) -> str:
    """Join the parts and apply Discord's 1900-character limit rules."""
    final_message = "".join(message_parts)

    if len(final_message) > 1900 and not short:
        logger.warning(
            f"Formatted message too long ({len(final_message)} chars)."
            " Retrying with short format."
        )
        return await format_message(wishlist, short=True, cached_data=cached_data)
    if len(final_message) > 1900:
        logger.warning("Shortened message still too long. Sending generic message.")
        return "# 📝 Family Wishlist \n Can't create a message or it will be too long"
    if not final_message.strip().endswith("\n"):
        final_message += "\n"

    return final_message


async def format_message(
    wishlist: list, *, short: bool = False, cached_data: dict | None = None
) -> str:
    """Format a list of wishlist items into a Discord message."""
    message_parts = ["# 📝 Family Wishlist \n"]
    if not wishlist:
        return "# 📝 Family Wishlist \nNo common wishlist items found to display."

    new_cached_data = cached_data or {}

    app_ids = _dedupe_app_ids(wishlist)

    # Wave 1: store details, one request per uncached game, all in flight together
    # instead of one round trip per game inside the rendering loop.
    async with aiohttp.ClientSession() as session:
        detail_failures = await _prefetch_details(
            session,
            [app_id for app_id in app_ids if app_id not in new_cached_data],
            new_cached_data,
        )

    # Wave 2: historical lows, two blocking HTTP calls per cache miss. The short pass
    # never renders prices, so it never asks for them.
    lowest_price_lines = (
        {}
        if short
        else await _prefetch_lowest_prices(
            [app_id for app_id in app_ids if app_id in new_cached_data]
        )
    )

    for item in wishlist:
        app_id = str(item[0])
        users_wanting = ", ".join(
            FAMILY_USER_DICT.get(user_steam_id, f"Unknown User({user_steam_id})")
            for user_steam_id in item[1]
        )
        message_parts.append(f"- {users_wanting} want ")

        if app_id in detail_failures:
            message_parts.append(
                f"**Unknown Game ({app_id})** ({detail_failures[app_id]}) \n"
            )
            continue

        message_parts.extend(
            _render_game_block(
                item,
                new_cached_data[app_id],
                lowest_price_lines.get(app_id, ""),
                short,
            )
        )

    return await _apply_length_limits(message_parts, wishlist, new_cached_data, short)
