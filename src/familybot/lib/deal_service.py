"""Deal finding and notification services."""

import asyncio
from typing import Any

import aiohttp

from familybot.lib.logging_config import get_logger
from familybot.lib.steam_api_manager import SteamAPIManager
from familybot.lib.steam_helpers import process_game_deal
from familybot.lib.user_repository import load_family_members_from_db
from familybot.lib.utils import prefetch_itad_prices
from familybot.lib.wishlist_service import collect_wishlists

logger = get_logger("deal_service")


async def force_deals(
    target_friendly_name: str | None = None,
) -> dict[str, Any]:
    """Check for deals on wishlist games and return results.

    If target_friendly_name is provided, checks only that user's wishlist.
    If no target_friendly_name is provided, checks all family wishlists.

    Args:
        target_friendly_name: Optional friendly name of a specific user to check

    Returns:
        Dict with success status and message about deals found
    """
    logger.info("Running force_deals...")

    try:
        async with aiohttp.ClientSession() as session:
            current_family_members = load_family_members_from_db()

            target_user_steam_ids = []
            if target_friendly_name:
                # Find the SteamID for the given friendly name
                found_steam_id = None
                for steam_id, friendly_name in current_family_members.items():
                    if friendly_name.lower() == target_friendly_name.lower():
                        found_steam_id = steam_id
                        break

                if found_steam_id:
                    target_user_steam_ids.append(found_steam_id)
                    logger.info(
                        f"Force deals: Checking deals for {target_friendly_name}'s wishlist"
                    )
                else:
                    available_names = ", ".join(current_family_members.values())
                    return {
                        "success": False,
                        "message": f"Friendly name '{target_friendly_name}' not found. Available names: {available_names}",
                    }
            else:
                target_user_steam_ids = list(current_family_members.keys())
                logger.info("Force deals: Checking deals for all family wishlists")

            # Collect wishlist games from the target user(s)
            global_wishlist = await collect_wishlists(
                current_family_members,
                force_fresh=False,
                session=session,
                target_user_steam_ids=target_user_steam_ids,
            )

            if not global_wishlist:
                return {
                    "success": False,
                    "message": "No wishlist games found to check for deals. This could be due to private profiles or empty wishlists.",
                }

            deals_found = []
            games_checked = 0
            max_games_to_check = 100  # Higher limit for force command
            total_games = min(len(global_wishlist), max_games_to_check)

            logger.info(f"Force deals: Checking {total_games} games for deals")

            steam_api_manager = SteamAPIManager()

            # Prefetch ITAD prices in batch to prevent N+1 API calls
            app_ids_to_check = [
                item[0] for item in global_wishlist[:max_games_to_check]
            ]
            await asyncio.to_thread(prefetch_itad_prices, app_ids_to_check)

            for item in global_wishlist[:max_games_to_check]:
                app_id = item[0]
                interested_users = item[1]
                games_checked += 1

                try:
                    deal_info = await process_game_deal(
                        app_id,
                        steam_api_manager,
                        session=session,
                    )

                    if deal_info:
                        user_names = [
                            current_family_members.get(uid, "Unknown")
                            for uid in interested_users
                        ]
                        deal_info["interested_users"] = user_names
                        deals_found.append(deal_info)

                except Exception as e:
                    logger.warning(
                        f"Force deals: Error checking deals for game {app_id}: {e}"
                    )
                    continue

            # Format results
            if deals_found:
                target_info = (
                    f" for {target_friendly_name}" if target_friendly_name else ""
                )
                message_parts = [
                    f"🎯 **Current Deals Alert{target_info}** (found {len(deals_found)} deals from {games_checked} games checked):\n\n"
                ]

                for deal in deals_found:  # Show all deals found
                    message_parts.append(f"**{deal['name']}**\n")
                    message_parts.append(f"{deal['deal_reason']}\n")
                    message_parts.append(f"💰 {deal['current_price']}")
                    if deal["discount_percent"] > 0:
                        message_parts.append(f" ~~{deal['original_price']}~~")
                    if deal["lowest_price"] != "N/A":
                        message_parts.append(f" | Lowest ever: {deal['lowest_price']}")
                    message_parts.append(
                        f"\n👥 Wanted by: {', '.join(deal['interested_users'][:3])}"
                    )
                    if len(deal["interested_users"]) > 3:
                        message_parts.append(
                            f" +{len(deal['interested_users']) - 3} more"
                        )
                    message_parts.append(
                        f"\n🔗 https://store.steampowered.com/app/{deal['app_id']}\n\n"
                    )

                final_message = "".join(message_parts)
                logger.info(f"Force deals: Found {len(deals_found)} deals")
                return {"success": True, "message": final_message}
            else:
                logger.info(f"Force deals: No deals found among {games_checked} games")
                return {
                    "success": True,
                    "message": f"📊 **Force deals complete!** No significant deals found among {games_checked} games checked.",
                }

    except Exception as e:
        logger.critical(
            f"Force deals: Critical error during force deals check: {e}", exc_info=True
        )
        return {"success": False, "message": f"Critical error during force deals: {e}"}
