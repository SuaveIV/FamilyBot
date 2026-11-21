# In src/familybot/lib/family_utils.py

import asyncio
import json
import logging

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
    """Generates the URL for the Steamworks GetSharedLibraryApps API using webapi_token."""
    token = get_token()  # Retrieve the webapi_token
    if not token:
        logger.error(
            "webapi_token is empty or not available. Cannot fetch family game list."
        )
        # Consider raising an error to be caught by the calling function
        raise ValueError("webapi_token is missing or invalid.")

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


async def _fetch_app_details(
    session: aiohttp.ClientSession, app_id: str, limiter: asyncio.Semaphore
) -> tuple[dict | None, str | None]:
    """Fetch one app's store details.

    Returns ``(data, None)`` on success, or ``(None, reason)`` where ``reason`` is the
    parenthetical shown on the "Unknown Game" line.
    """
    game_info_json: dict | None = None
    async with limiter:
        try:
            url = _STEAM_APPDETAILS_URL.format(app_id=app_id)
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as game_info_response:
                game_info_response.raise_for_status()
                game_info_json = json.loads(await game_info_response.text())

            if game_info_json.get(app_id, {}).get("success"):
                return game_info_json[app_id]["data"], None

            logger.warning(
                f"App details success false for AppID {app_id} in format_message."
                f" Response: {game_info_json}"
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
                f" Response: {game_info_json}"
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


async def format_message(
    wishlist: list, *, short: bool = False, cached_data: dict | None = None
) -> str:
    """Formats a list of wishlist items into a Discord message."""
    message_parts = ["# 📝 Family Wishlist \n"]
    if not wishlist:
        return "# 📝 Family Wishlist \nNo common wishlist items found to display."

    new_cached_data = cached_data or {}

    # --- Wave 1: store details. One request per uncached game, all in flight together,
    # instead of one round trip per game inside the rendering loop.
    seen: set[str] = set()
    missing: list[str] = []
    for item in wishlist:
        app_id = str(item[0])
        if app_id not in new_cached_data and app_id not in seen:
            seen.add(app_id)
            missing.append(app_id)

    detail_failures: dict[str, str] = {}
    async with aiohttp.ClientSession() as session:
        if missing:
            limiter = asyncio.Semaphore(_DETAILS_CONCURRENCY)
            details = await asyncio.gather(
                *(_fetch_app_details(session, app_id, limiter) for app_id in missing)
            )
            for app_id, (data, reason) in zip(missing, details, strict=True):
                if data is None:
                    detail_failures[app_id] = reason or "Unexpected Error"
                else:
                    new_cached_data[app_id] = data

    # --- Wave 2: historical lows. Two blocking HTTP calls per cache miss, so this was the
    # second serial cost. The short pass never renders prices, so it never asks for them.
    lowest_price_lines: dict[str, str] = {}
    if not short:
        priced: list[str] = []
        for item in wishlist:
            app_id = str(item[0])
            if app_id in new_cached_data and app_id not in priced:
                priced.append(app_id)
        if priced:
            itad_limiter = asyncio.Semaphore(_ITAD_CONCURRENCY)
            for app_id, line in await asyncio.gather(
                *(_fetch_lowest_price(app_id, itad_limiter) for app_id in priced)
            ):
                lowest_price_lines[app_id] = line

    # --- Render in wishlist order, exactly as the sequential version did.
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

        game_info_data = new_cached_data[app_id]

        game_name = game_info_data.get("name", f"Unknown Game ({app_id})")
        message_parts.append(
            f"[{game_name}](<https://store.steampowered.com/app/{app_id}>) \n"
        )

        price_overview = game_info_data.get("price_overview")
        if price_overview and price_overview.get("discount_percent") != 0:
            final_formatted = price_overview.get("final_formatted", "N/A")
            discount_percent = price_overview.get("discount_percent", 0)
            message_parts.append(
                f"  **__The game is on sale at {final_formatted} (-{discount_percent}%)__** \n"
            )
        else:
            final_formatted = (
                price_overview.get("final_formatted", "N/A")
                if price_overview
                else "N/A"
            )
            message_parts.append(f"  The game is at {final_formatted} \n")

        if short:
            continue

        final_price = price_overview.get("final") if price_overview else None
        if final_price is not None and item[1]:
            price_per_person = round(final_price / 100 / len(item[1]), 2)
            message_parts.append(f" which is {price_per_person}$ per person \n")

        message_parts.append(lowest_price_lines.get(app_id, ""))

    final_message = "".join(message_parts)

    if len(final_message) > 1900 and not short:
        logger.warning(
            f"Formatted message too long ({len(final_message)} chars). Retrying with short format."
        )
        return await format_message(wishlist, short=True, cached_data=new_cached_data)
    if len(final_message) > 1900 and short:
        logger.warning("Shortened message still too long. Sending generic message.")
        return "# 📝 Family Wishlist \n Can't create a message or it will be too long"
    if not final_message.strip().endswith("\n"):
        final_message += "\n"

    return final_message
