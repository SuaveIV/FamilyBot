"""Wishlist collection and duplicate detection services."""

from typing import Any

import aiohttp

from familybot.config import STEAMWORKS_API_KEY
from familybot.lib.api_utils import handle_api_response
from familybot.lib.constants import MAX_WISHLIST_GAMES_TO_PROCESS
from familybot.lib.family_game_manager import get_saved_games
from familybot.lib.family_utils import format_message
from familybot.lib.logging_config import get_logger, log_private_profile_detection
from familybot.lib.steam_api_manager import SteamAPIManager
from familybot.lib.user_repository import load_family_members_from_db
from familybot.lib.utils import add_to_wishlist
from familybot.lib.wishlist_repository import cache_wishlist, get_cached_wishlist

logger = get_logger("wishlist_service")


async def collect_wishlists(
    current_family_members: dict,
    force_fresh: bool,
    session: aiohttp.ClientSession,
    target_user_steam_ids: list[str] | None = None,
) -> list[list]:
    """Collect wishlists from family members and aggregate into a global list.

    Args:
        current_family_members: Dict of {steam_id: friendly_name}
        force_fresh: If True, bypass cache and fetch fresh data
        session: The aiohttp session to use for API requests
        target_user_steam_ids: Optional list of specific users to check

    Returns:
        Global wishlist as list of [appid, [user_steam_ids]]
    """
    steam_api_manager = SteamAPIManager()

    if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
        logger.error("STEAMWORKS_API_KEY is not configured for wishlist task.")
        return []

    global_wishlist: list[list] = []
    if target_user_steam_ids:
        all_unique_steam_ids_to_check = set(target_user_steam_ids)
    else:
        all_unique_steam_ids_to_check = set(current_family_members.keys())

    for user_steam_id in all_unique_steam_ids_to_check:
        user_name_for_log = current_family_members.get(
            user_steam_id, f"Unknown ({user_steam_id})"
        )

        if not force_fresh:
            # Try to get cached wishlist first
            cached_wishlist = get_cached_wishlist(user_steam_id)
            if cached_wishlist is not None:
                logger.info(
                    f"Using cached wishlist for {user_name_for_log} ({len(cached_wishlist)} items)"
                )
                for app_id in cached_wishlist:
                    add_to_wishlist(global_wishlist, app_id, user_steam_id)
                continue

        # If not cached or force_fresh is True, fetch from API
        wishlist_url = "https://api.steampowered.com/IWishlistService/GetWishlist/v1/"
        wishlist_params = {
            "key": STEAMWORKS_API_KEY,
            "steamid": user_steam_id,
        }
        logger.info(
            f"Fetching wishlist from API for {user_name_for_log} (Steam ID: {user_steam_id})"
        )

        wishlist_json = None
        try:
            await steam_api_manager.rate_limit_steam_api()  # Apply rate limit here
            async with session.get(
                wishlist_url,
                params=wishlist_params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as wishlist_response:
                text = await wishlist_response.text()
                if text == '{"success":2}':
                    log_private_profile_detection(
                        logger, user_name_for_log, user_steam_id, "wishlist"
                    )
                    continue

                wishlist_json = await handle_api_response(
                    f"GetWishlist ({user_name_for_log})", wishlist_response
                )
            if not wishlist_json:
                continue

            wishlist_items = wishlist_json.get("response", {}).get("items", [])

            if not wishlist_items:
                logger.info(f"No items found in {user_name_for_log}'s wishlist.")
                continue

            # Extract app IDs for caching
            user_wishlist_appids = []
            for game_item in wishlist_items:
                app_id = str(game_item.get("appid"))
                if not app_id:
                    logger.warning(
                        f"Skipping wishlist item due to missing appid: {game_item}"
                    )
                    continue

                user_wishlist_appids.append(app_id)
                add_to_wishlist(global_wishlist, app_id, user_steam_id)

            # Cache the wishlist
            cache_wishlist(user_steam_id, user_wishlist_appids)

        except Exception as e:
            logger.critical(
                f"An unexpected error occurred fetching/processing {user_name_for_log}'s wishlist: {e}",
                exc_info=True,
            )

    return global_wishlist


async def process_wishlist_duplicates(
    global_wishlist: list[list], session: aiohttp.ClientSession
) -> dict[str, Any]:
    """Process duplicate games in the global wishlist and fetch their details.

    Args:
        global_wishlist: List of [appid, [user_steam_ids]]
        session: The aiohttp session to use for API requests

    Returns:
        Dict with success status and formatted message about duplicates found
    """
    steam_api_manager = SteamAPIManager()

    # First, collect all duplicate games without fetching details
    potential_duplicate_games = []
    for item in global_wishlist:
        app_id = item[0]
        owner_steam_ids = item[1]
        if len(owner_steam_ids) > 1:
            potential_duplicate_games.append(item)

    # Sort and slice the potential duplicate games for processing
    sorted_duplicate_games = sorted(
        potential_duplicate_games, key=lambda x: x[0], reverse=True
    )

    if len(sorted_duplicate_games) > MAX_WISHLIST_GAMES_TO_PROCESS:
        logger.warning(
            f"Detected {len(sorted_duplicate_games)} common wishlist games. Processing only the latest {MAX_WISHLIST_GAMES_TO_PROCESS} to avoid rate limits."
        )
        games_to_process = sorted_duplicate_games[:MAX_WISHLIST_GAMES_TO_PROCESS]
        message_prefix = f"Detected {len(sorted_duplicate_games)} common wishlist games. Processing only the latest {MAX_WISHLIST_GAMES_TO_PROCESS}. More may be announced in subsequent checks.\n"
    else:
        games_to_process = sorted_duplicate_games
        message_prefix = ""

    # Now process the selected games and fetch their details
    duplicate_games_for_display = []
    saved_game_appids = {item[0] for item in get_saved_games()}

    for item in games_to_process:
        app_id = item[0]

        game_url = (
            f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
        )
        logger.info(f"Fetching app details for wishlist AppID: {app_id}")

        game_info_json = None
        try:
            await (
                steam_api_manager.rate_limit_steam_store_api()
            )  # Apply store API rate limit
            async with session.get(
                game_url, timeout=aiohttp.ClientTimeout(total=10)
            ) as game_info_response:
                game_info_json = await handle_api_response(
                    "AppDetails (Wishlist)", game_info_response
                )
            if not game_info_json:
                continue

            game_data = game_info_json.get(str(app_id), {}).get("data")
            if not game_data:
                logger.warning(
                    f"No game data found for wishlist AppID {app_id} in app details response."
                )
                continue

            # Use cached boolean fields for faster performance
            is_family_shared = game_data.get("is_family_shared", False)

            if (
                game_data.get("type") == "game"
                and not game_data.get("is_free")
                and is_family_shared
                and "recommendations" in game_data
                and app_id not in saved_game_appids
            ):
                duplicate_games_for_display.append(item)
            else:
                logger.debug(
                    f"Skipping wishlist game {app_id}: not a paid game, not family shared category, or no recommendations, or already owned."
                )

        except Exception as e:
            logger.critical(
                f"An unexpected error occurred processing duplicate wishlist game {app_id}: {e}",
                exc_info=True,
            )

    if duplicate_games_for_display:
        wishlist_message_content = await format_message(
            duplicate_games_for_display, short=False
        )
        full_message = message_prefix + wishlist_message_content
        return {
            "success": True,
            "message": f"Wishlist refreshed. Details:\n{full_message}",
        }
    else:
        return {
            "success": True,
            "message": "Wishlist refreshed. No common wishlist games found for display.",
        }


async def check_wishlist() -> dict[str, Any]:
    """Check wishlist using cached data (for scheduled tasks).

    Uses cached wishlist data (2-hour TTL) but always fetches fresh game details
    since prices change frequently.

    Returns:
        Dict with success status and message
    """
    logger.info("Running check_wishlist (cache-respecting for wishlists)...")
    try:
        async with aiohttp.ClientSession() as session:
            current_family_members = load_family_members_from_db()
            global_wishlist = await collect_wishlists(
                current_family_members, force_fresh=False, session=session
            )
            return await process_wishlist_duplicates(global_wishlist, session)
    except Exception as e:
        logger.critical(
            f"An unexpected error occurred in check_wishlist: {e}",
            exc_info=True,
        )
        return {
            "success": False,
            "message": f"Error checking wishlist: {str(e)}",
        }


async def force_wishlist() -> dict[str, Any]:
    """Force wishlist refresh bypassing cache (for admin commands).

    Always fetches fresh wishlist data and game details, and updates cache
    for next regular check.

    Returns:
        Dict with success status and message
    """
    logger.info("Running force_wishlist (bypassing cache)...")
    try:
        async with aiohttp.ClientSession() as session:
            current_family_members = load_family_members_from_db()
            global_wishlist = await collect_wishlists(
                current_family_members, force_fresh=True, session=session
            )
            return await process_wishlist_duplicates(global_wishlist, session)
    except Exception as e:
        logger.critical(
            f"An unexpected error occurred in force_wishlist: {e}",
            exc_info=True,
        )
        return {
            "success": False,
            "message": f"Error forcing wishlist refresh: {str(e)}",
        }
