"""Family library fetching and new game detection services."""

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp

from familybot.lib.api_utils import handle_api_response
from familybot.lib.family_library_repository import (
    cache_family_library,
    get_cached_family_library,
)
from familybot.lib.family_game_manager import get_saved_games, set_saved_games
from familybot.lib.family_utils import get_family_game_list_url
from familybot.lib.game_details_repository import (
    cache_game_details,
    get_cached_game_details,
)
from familybot.lib.logging_config import get_logger
from familybot.lib.steam_api_manager import SteamAPIManager
from familybot.lib.user_repository import load_family_members_from_db
from familybot.lib.itad_service import get_lowest_price

logger = get_logger("family_library_service")


async def fetch_family_library_from_api(session: aiohttp.ClientSession) -> list:
    """Fetch family library from Steam API.

    Args:
        session: The aiohttp session to use for the request

    Returns:
        List of games from the family library

    Raises:
        Exception: If API call fails or no games found
    """
    steam_api_manager = SteamAPIManager()
    await steam_api_manager.rate_limit_steam_api()

    url_family_list = get_family_game_list_url()
    async with session.get(
        url_family_list, timeout=aiohttp.ClientTimeout(total=15)
    ) as answer:
        games_json = await handle_api_response("GetFamilySharedApps", answer)

    if not games_json:
        raise Exception("Failed to get family shared apps from API")

    game_list = games_json.get("response", {}).get("apps", [])
    if not game_list:
        logger.warning("No apps found in family game list response.")
        raise Exception("No games found in the family library")

    return game_list


async def process_new_games(
    game_list: list,
    current_family_members: dict,
    session: aiohttp.ClientSession,
) -> dict[str, Any]:
    """Process game list and detect new games for notification.

    Args:
        game_list: List of games from family library
        current_family_members: Dict of {steam_id: friendly_name}
        session: The aiohttp session to use for API requests

    Returns:
        Dict with success status and message about new games found
    """
    steam_api_manager = SteamAPIManager()

    game_owner_list = {}
    game_array = []
    for game in game_list:
        if game.get("exclude_reason") != 3:
            appid = str(game.get("appid"))
            game_array.append(appid)
            if len(game.get("owner_steamids", [])) == 1:
                game_owner_list[appid] = str(game["owner_steamids"][0])

    saved_games_with_timestamps = get_saved_games()
    saved_appids = {item[0] for item in saved_games_with_timestamps}

    new_appids = set(game_array) - saved_appids

    all_games_for_db_update = []
    current_utc_iso = (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )

    for appid in game_array:
        if appid in new_appids:
            all_games_for_db_update.append((appid, current_utc_iso))
        else:
            found_timestamp = next(
                (ts for ap, ts in saved_games_with_timestamps if ap == appid), None
            )
            if found_timestamp:
                all_games_for_db_update.append((appid, found_timestamp))
            else:
                all_games_for_db_update.append((appid, current_utc_iso))

    new_games_to_notify_raw = [(appid, current_utc_iso) for appid in new_appids]
    new_games_to_notify_raw.sort(key=lambda x: x[1], reverse=True)

    if len(new_games_to_notify_raw) > 10:
        logger.warning(
            f"Detected {len(new_games_to_notify_raw)} new games. Processing only the latest 10 (by AppID) to avoid rate limits."
        )
        new_games_to_process = new_games_to_notify_raw[:10]
        message_prefix = f"Detected {len(new_games_to_notify_raw)} new games. Processing only the latest 10. More may be announced in subsequent checks.\n"
    else:
        new_games_to_process = new_games_to_notify_raw
        message_prefix = ""

    notification_messages = []
    if new_games_to_process:
        logger.info(
            f"Processing {len(new_games_to_process)} new games for notification."
        )
        for new_appid_tuple in new_games_to_process:
            new_appid = new_appid_tuple[0]

            # Try to get cached game details first
            cached_game = get_cached_game_details(new_appid)
            if cached_game:
                logger.info(
                    f"Using cached game details for new game AppID: {new_appid}"
                )
                game_data = cached_game
            else:
                # If not cached, fetch from API
                await steam_api_manager.rate_limit_steam_store_api()
                game_url = f"https://store.steampowered.com/api/appdetails?appids={new_appid}&cc=us&l=en"
                logger.info(
                    f"Fetching app details from API for new game AppID: {new_appid}"
                )
                async with session.get(
                    game_url, timeout=aiohttp.ClientTimeout(total=10)
                ) as app_info_response:
                    game_info_json = await handle_api_response(
                        "AppDetails (New Game)", app_info_response
                    )
                if not game_info_json:
                    continue

                game_data = game_info_json.get(str(new_appid), {}).get("data")
                if not game_data:
                    logger.warning(
                        f"No game data found for new game AppID {new_appid} in app details response."
                    )
                    continue

                # Cache the game details (use permanent=False so prices expire with GAME_DETAILS_CACHE_TTL)
                cache_game_details(new_appid, game_data, permanent=False)

            is_family_shared_game = any(
                cat.get("id") == 62 for cat in game_data.get("categories", [])
            )

            if (
                game_data.get("type") == "game"
                and not game_data.get("is_free")
                and is_family_shared_game
            ):
                owner_steam_id = game_owner_list.get(str(new_appid))
                owner_name = current_family_members.get(
                    owner_steam_id, f"Unknown Owner ({owner_steam_id})"
                )

                # Build the base message
                game_name = game_data.get("name", "Unknown Game")
                message = f"Thank you to {owner_name} for **{game_name}**\nhttps://store.steampowered.com/app/{new_appid}"

                # Add pricing information if available
                try:
                    current_price = game_data.get("price_overview", {}).get(
                        "final_formatted", "N/A"
                    )
                    lowest_price = await asyncio.to_thread(
                        get_lowest_price, int(new_appid)
                    )

                    if current_price != "N/A" or lowest_price != "N/A":
                        price_info = []
                        if current_price != "N/A":
                            price_info.append(f"Current: {current_price}")
                        if lowest_price != "N/A":
                            price_info.append(f"Lowest ever: ${lowest_price}")

                        if price_info:
                            message += f"\n💰 {'|'.join(price_info)}"
                except Exception as e:
                    logger.warning(
                        f"Could not get pricing info for new game {new_appid}: {e}"
                    )

                notification_messages.append(message)
            else:
                logger.debug(
                    f"Skipping new game {new_appid}: not a paid game, not family shared, or not type 'game'."
                )

        # Track which new AppIDs were processed (even if skipped for notification)
        processed_new_appids = {item[0] for item in new_games_to_process}

        # Sync the database state:
        # 1. Existing games keep their timestamps
        # 2. PROCESSED new games get current timestamp
        # 3. UNPROCESSED new games are NOT added (so they stay "new" for next time)
        final_db_update_list = []
        for appid in game_array:
            if appid in new_appids:
                if appid in processed_new_appids:
                    final_db_update_list.append((appid, current_utc_iso))
                # Else: Skip this AppID for now so it remains "new"
            else:
                # Find existing timestamp from saved games
                found_timestamp = next(
                    (ts for ap, ts in saved_games_with_timestamps if ap == appid), None
                )
                if found_timestamp:
                    final_db_update_list.append((appid, found_timestamp))
                else:
                    # Should not happen if logic is correct, but for safety:
                    final_db_update_list.append((appid, current_utc_iso))

        set_saved_games(final_db_update_list)
        if notification_messages:
            full_message = message_prefix + "\n\n".join(notification_messages)
            return {
                "success": True,
                "message": f"New games detected: {len(new_games_to_process)} games processed. Details:\n{full_message}",
            }
        else:
            return {
                "success": True,
                "message": "No new family shared games detected for notification.",
            }
    else:
        logger.info("No new games detected.")
        return {"success": True, "message": "No new games detected."}


async def check_new_game() -> dict[str, Any]:
    """Check for new games using cached family library (for scheduled tasks).

    Uses cached family library if available to minimize API calls.
    Called by the hourly automated task.

    Returns:
        Dict with success status and message
    """
    logger.info("Running check_new_game (cache-respecting)...")

    try:
        async with aiohttp.ClientSession() as session:
            # Try to get cached family library first
            cached_family_library = get_cached_family_library()
            if cached_family_library is not None:
                logger.info(
                    f"Using cached family library for new game check ({len(cached_family_library)} games)"
                )
                game_list = cached_family_library
            else:
                # If not cached, fetch from API
                logger.info(
                    "No cached family library found (or cache expired), fetching from API..."
                )
                game_list = await fetch_family_library_from_api(session)

                # Cache for next time
                cache_family_library(game_list)
                logger.info(
                    f"Updated family library cache with {len(game_list)} games."
                )

            current_family_members = load_family_members_from_db()
            return await process_new_games(game_list, current_family_members, session)

    except Exception as e:
        logger.critical(
            f"An unexpected error occurred in check_new_game: {e}", exc_info=True
        )
        return {
            "success": False,
            "message": f"Error checking for new games: {str(e)}",
        }


async def force_new_game() -> dict[str, Any]:
    """Force check for new games bypassing cache (for admin commands).

    Always fetches fresh data from the Steam API and updates the cache.

    Returns:
        Dict with success status and message
    """
    logger.info("Running force_new_game (bypassing cache)...")

    try:
        async with aiohttp.ClientSession() as session:
            # Always fetch fresh data from API (no cache check)
            logger.info("Force refresh: Fetching fresh family library from API...")
            game_list = await fetch_family_library_from_api(session)

            # Update cache with fresh data for next regular check
            cache_family_library(game_list)
            logger.info(f"Updated family library cache with {len(game_list)} games")

            current_family_members = load_family_members_from_db()
            return await process_new_games(game_list, current_family_members, session)

    except Exception as e:
        logger.critical(
            f"An unexpected error occurred in force_new_game: {e}", exc_info=True
        )
        return {
            "success": False,
            "message": f"Error forcing new game notification: {str(e)}",
        }
