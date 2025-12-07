import time

import requests
from interactions import Extension
from interactions.ext.prefixed_commands import PrefixedContext, prefixed_command

# Import necessary items from your config and lib modules
from familybot.config import (
    FAMILY_STEAM_ID,
    STEAMWORKS_API_KEY,
)
from familybot.lib.database import (
    cache_family_library,
    cache_game_details,
    cache_wishlist,
    get_cached_family_library,
    get_cached_game_details,
    get_cached_wishlist,
    get_steam_id_from_friendly_name,
    load_family_members_from_db,
)

# Import enhanced logging configuration
from familybot.lib.logging_config import get_logger
from familybot.lib.types import FamilyBotClient
from familybot.lib.utils import get_lowest_price, split_message
from familybot.lib.steam_api_manager import SteamAPIManager
from familybot.lib.steam_helpers import process_game_deal, send_admin_dm

# Setup enhanced logging for this specific module
logger = get_logger(__name__)


class steam_family(Extension):
    def __init__(self, bot: FamilyBotClient):
        self.bot: FamilyBotClient = bot
        self.steam_api_manager = SteamAPIManager()
        self.steam_api = self.steam_api_manager.steam_api

        logger.info("Steam Family Plugin loaded (User Commands)")

    """
    [help]|profile|Displays a user's Steam profile by friendly name (from the family members list), SteamID64, or vanity URL (e.g. gabelogannewell).|!profile <name/steamid/vanity_url>|***This command can be used in bot DM***
    """

    @prefixed_command(name="profile")
    async def profile_command(self, ctx: PrefixedContext, user_input: str):
        """Displays a user's Steam profile information by friendly name, SteamID64, or vanity URL."""
        steam_id = get_steam_id_from_friendly_name(user_input)
        resolved_method = None
        if steam_id:
            resolved_method = "family member"
        else:
            # Try to resolve as SteamID64
            if (
                user_input.isdigit()
                and len(user_input) == 17
                and user_input.startswith("7656119")
            ):
                steam_id = user_input
                resolved_method = "SteamID64"
            else:
                # Try to resolve as vanity URL
                try:
                    if not self.steam_api:
                        await ctx.send(
                            "Steam API key not configured. Cannot resolve vanity URLs."
                        )
                        return
                    vanity_name = user_input
                    if "steamcommunity.com/id/" in vanity_name:
                        vanity_name = vanity_name.split("steamcommunity.com/id/")[
                            1
                        ].strip("/")
                    resolve = self.steam_api.call(
                        "ISteamUser.ResolveVanityURL", vanityurl=vanity_name, url_type=1
                    )
                    if resolve and resolve.get("response", {}).get("success") == 1:
                        steam_id = resolve["response"]["steamid"]
                        resolved_method = "vanity URL"
                    else:
                        await ctx.send(
                            f"Could not find a user with the name, SteamID, or vanity URL '{user_input}'."
                        )
                        return
                except Exception as e:
                    logger.error(f"Error resolving vanity URL '{user_input}': {e}")
                    await ctx.send(f"Error resolving vanity URL '{user_input}': {e}")
                    return
        try:
            if not self.steam_api:
                await ctx.send(
                    "Steam API key not configured. Cannot retrieve player summaries."
                )
                return
            player_summaries = self.steam_api.call(
                "ISteamUser.GetPlayerSummaries", steamids=steam_id
            )
            if not player_summaries or not player_summaries.get("response", {}).get(
                "players"
            ):
                await ctx.send("Could not retrieve profile information for this user.")
                return
            player = player_summaries["response"]["players"][0]
            persona_name = player.get("personaname", "N/A")
            profile_url = player.get("profileurl", "#")
            avatar_full = player.get("avatarfull", "")
            status = {
                0: "Offline",
                1: "Online",
                2: "Busy",
                3: "Away",
                4: "Snooze",
                5: "Looking to trade",
                6: "Looking to play",
            }.get(player.get("personastate", 0), "Unknown")
            message = f"**{persona_name}**'s Profile\n"
            message += f"Status: {status}\n"
            if resolved_method:
                message += f"(Found by {resolved_method})\n"
            if "gameextrainfo" in player:
                message += f"Currently Playing: {player['gameextrainfo']}\n"
            try:
                recently_played = self.steam_api.call(
                    "IPlayerService.GetRecentlyPlayedGames", steamid=steam_id, count=3
                )
                if (
                    recently_played
                    and "response" in recently_played
                    and recently_played["response"].get("total_count", 0) > 0
                    and recently_played["response"].get("games")
                ):
                    message += "\n**Recently Played:**\n"
                    for game in recently_played["response"]["games"]:
                        game_name = game.get("name", "Unknown Game")
                        playtime_2weeks = game.get("playtime_2weeks", 0)
                        playtime_forever = game.get("playtime_forever", 0)
                        message += f"- {game_name} ({playtime_2weeks / 60:.1f} hrs last 2 weeks, {playtime_forever / 60:.1f} hrs total)\n"
            except Exception as e:
                logger.warning(
                    f"Could not fetch recently played games for {user_input}: {e}"
                )
            message += f"\nProfile URL: <{profile_url}>\n"
            if avatar_full:
                message += f"Avatar: {avatar_full}"
            await ctx.send(message)
        except Exception as e:
            logger.error(f"Error fetching profile for {user_input}: {e}")
            await ctx.send("An error occurred while fetching the profile.")

    @prefixed_command(name="coop")
    async def coop_command(self, ctx: PrefixedContext, number_str: str | None = None):
        start_time = time.time()  # Track execution time

        if number_str is None:
            await ctx.send(
                "❌ **Missing required parameter!**\n\n**Usage:** `!coop NUMBER_OF_COPIES`\n**Example:** `!coop 2` (to find games with 2+ copies)\n\n**Note:** The number must be greater than 1."
            )
            return

        try:
            number = int(number_str)
        except ValueError:
            await ctx.send(
                "❌ **Invalid number format!**\n\n**Usage:** `!coop NUMBER_OF_COPIES`\n**Example:** `!coop 2` (to find games with 2+ copies)\n\nPlease provide a valid number."
            )
            return

        if number <= 1:
            await ctx.send(
                "❌ **Invalid number!**\n\nThe number after the command must be greater than 1.\n**Example:** `!coop 2` (to find games with 2+ copies)"
            )
            return

        loading_message = await ctx.send(f"Searching for games with {number} copies...")

        games_json = None
        try:
            # Try to get cached family library first
            cached_family_library = get_cached_family_library()
            if cached_family_library is not None:
                logger.info(
                    f"Using cached family library ({len(cached_family_library)} games)"
                )
                game_list = cached_family_library
            else:
                # If not cached, fetch from API
                if not self.steam_api:
                    await loading_message.edit(
                        content="Steam API key not configured. Cannot fetch family games."
                    )
                    return
                await self.steam_api_manager.rate_limit_steam_api()  # Apply rate limit before API call
                try:
                    # Corrected method name based on Steam Web API documentation
                    games_json = self.steam_api.call(
                        "IPlayerService.GetFamilySharedApps",
                        steamid=FAMILY_STEAM_ID,
                        include_appinfo=1,
                        include_played_free_games=1,
                    )
                    game_list = games_json.get("response", {}).get("apps", [])
                except Exception as e:
                    logger.error(f"Error fetching family shared games: {e}")
                    await loading_message.edit(
                        content="Error retrieving family game list."
                    )
                    return
                if not game_list:
                    logger.warning("No games found in family game list response.")
                    await loading_message.edit(
                        content="No games found in the family library."
                    )
                    return

                # Cache the family library for 30 minutes
                cache_family_library(game_list, cache_minutes=30)

            game_array = []
            coop_game_names = []

            # Load family members for potential future use
            load_family_members_from_db()

            for game in game_list:
                if (
                    game.get("exclude_reason") != 3
                    and len(game.get("owner_steamids", [])) >= number
                ):
                    game_array.append(str(game.get("appid")))

            for game_appid in game_array:
                # Try to get cached game details first
                cached_game = get_cached_game_details(game_appid)
                if cached_game:
                    logger.info(f"Using cached game details for AppID: {game_appid}")
                    game_data = cached_game
                else:
                    # If not cached, fetch from API
                    await (
                        self.steam_api_manager.rate_limit_steam_store_api()
                    )  # Apply store API rate limit
                    game_url = f"https://store.steampowered.com/api/appdetails?appids={game_appid}&cc=us&l=en"
                    logger.info(
                        f"Fetching app details from API for AppID: {game_appid} for coop check"
                    )
                    app_info_response = requests.get(game_url, timeout=10)
                    game_info_json = app_info_response.json()
                    if not game_info_json:
                        continue

                    game_data = game_info_json.get(str(game_appid), {}).get("data")
                    if not game_data:
                        logger.warning(
                            f"No game data found for AppID {game_appid} in app details response for coop check."
                        )
                        continue

                    # Cache the game details permanently (game details rarely change)
                    cache_game_details(game_appid, game_data, permanent=True)

                if game_data.get("type") == "game" and not game_data.get("is_free"):
                    # Use cached boolean fields for faster performance
                    is_family_shared = game_data.get("is_family_shared", False)
                    is_multiplayer = game_data.get("is_multiplayer", False)

                    if is_family_shared and is_multiplayer:
                        game_name = game_data.get(
                            "name", f"Unknown Game ({game_appid})"
                        )

                        # Add pricing information if available
                        try:
                            current_price = game_data.get("price_overview", {}).get(
                                "final_formatted", "N/A"
                            )
                            lowest_price = get_lowest_price(int(game_appid))

                            price_info = []
                            if current_price != "N/A":
                                price_info.append(f"Current: {current_price}")
                            if lowest_price != "N/A":
                                price_info.append(f"Lowest: ${lowest_price}")

                            if price_info:
                                game_name += f" ({' | '.join(price_info)})"
                        except Exception as e:
                            logger.warning(
                                f"Could not get pricing info for coop game {game_appid}: {e}"
                            )

                        coop_game_names.append(game_name)
                    else:
                        logger.debug(
                            f"Game {game_appid} is not categorized as family shared (ID 62)."
                        )

            if coop_game_names:
                # Use the utility function to handle message truncation
                header = "__Common shared multiplayer games__:\n"
                final_message = header + "\n".join(coop_game_names)
                message_chunks = split_message(final_message)
                for chunk in message_chunks:
                    await loading_message.channel.send(content=chunk)
                await loading_message.delete()
            else:
                await loading_message.edit(
                    content=f"No common shared multiplayer games found with {number} copies."
                )

        except ValueError as e:  # Catch ValueError if webapi_token is missing
            logger.error(f"Error in coop_command: {e}")
            await loading_message.edit(
                content=f"Error: {e}. Cannot retrieve family games."
            )
            await send_admin_dm(self.bot, f"Error in coop_command: {e}")
        except Exception as e:
            logger.critical(
                f"An unexpected error occurred in coop_command: {e}", exc_info=True
            )
            await loading_message.edit(
                content="An unexpected error occurred during common games search."
            )
            await send_admin_dm(self.bot, f"Critical error coop command: {e}")
        finally:
            elapsed_time = time.time() - start_time
            logger.info(f"coop_command completed in {elapsed_time:.2f} seconds")

    """
    [help]|deals|check current deals for family wishlist games|!deals|Shows games from family wishlists that are currently on sale or at historical low prices. ***This command can be used in bot DM***
    """

    @prefixed_command(name="deals")
    async def check_deals_command(self, ctx: PrefixedContext):
        loading_message = await ctx.send(
            "🔍 Checking for current deals on your wishlist..."
        )

        try:
            # Get the SteamID of the user who called the command
            from familybot.lib.database import get_steam_id_from_discord_id

            user_steam_id = get_steam_id_from_discord_id(str(ctx.author_id))

            if not user_steam_id:
                await loading_message.edit(
                    content="❌ Your SteamID is not linked. Please link it using the `!link_steam` command."
                )
                return

            user_name_for_log = ctx.author.username  # Use Discord username for logging

            # Collect wishlist games for the calling user only
            global_wishlist = []

            # Try to get cached wishlist first
            cached_wishlist = get_cached_wishlist(user_steam_id)
            if cached_wishlist is not None:
                logger.info(
                    f"Deals: Using cached wishlist for {user_name_for_log} ({len(cached_wishlist)} items)"
                )
                for app_id in cached_wishlist:
                    global_wishlist.append([app_id, [user_steam_id]])
            else:
                # If not cached, fetch fresh wishlist data from API
                if (
                    not STEAMWORKS_API_KEY
                    or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE"
                ):
                    await loading_message.edit(
                        content="❌ Steam API key is not configured. Cannot fetch wishlist."
                    )
                    return

                try:
                    if not self.steam_api:
                        await loading_message.edit(
                            content="❌ Steam API key is not configured. Cannot fetch wishlist."
                        )
                        return
                    await self.steam_api_manager.rate_limit_steam_api()
                    wishlist_json = self.steam_api.call(
                        "IWishlistService.GetWishlist", steamid=user_steam_id
                    )
                    if not wishlist_json:
                        await loading_message.edit(
                            content="❌ Your Steam wishlist is private. Please make it public to use this command."
                        )
                        return
                    wishlist_items = wishlist_json.get("response", {}).get("items", [])
                    if not wishlist_items:
                        await loading_message.edit(
                            content="📭 Your wishlist is empty or contains no items."
                        )
                        return

                    # Extract app IDs and add to global wishlist
                    user_wishlist_appids = []
                    for game_item in wishlist_items:
                        app_id = str(game_item.get("appid"))
                        if not app_id:
                            continue
                        user_wishlist_appids.append(app_id)
                        global_wishlist.append([app_id, [user_steam_id]])

                    # Cache the wishlist for 2 hours
                    cache_wishlist(user_steam_id, user_wishlist_appids, cache_hours=2)
                    logger.info(
                        f"Deals: Fetched and cached {len(user_wishlist_appids)} wishlist items for {user_name_for_log}"
                    )

                except Exception as e:
                    logger.error(
                        f"Deals: Error fetching wishlist for {user_name_for_log}: {e}"
                    )
                    await loading_message.edit(
                        content="❌ Error fetching your wishlist. Please try again later."
                    )
                    return

            if not global_wishlist:
                await loading_message.edit(
                    content="📭 No wishlist games found to check for deals."
                )
                return

            # Check for deals
            deals_found = []
            games_checked = 0
            max_games_to_check = 50  # Reasonable limit for individual user
            total_games = min(len(global_wishlist), max_games_to_check)

            await loading_message.edit(
                content=f"📊 Checking {total_games} games for deals..."
            )

            for item in global_wishlist[:max_games_to_check]:
                app_id = item[0]
                games_checked += 1

                try:
                    deal_info = await process_game_deal(
                        app_id,
                        self.steam_api_manager,
                        high_discount_threshold=50,
                        low_discount_threshold=25,
                        historical_low_buffer=1.1,
                    )

                    if deal_info:
                        deals_found.append(deal_info)

                except Exception as e:
                    logger.warning(
                        f"Deals: Error checking deals for game {app_id}: {e}"
                    )
                    continue

            # Format and send results
            if deals_found:
                message_parts = [
                    f"🎯 **Current Deals on Your Wishlist** (found {len(deals_found)} deals from {games_checked} games checked):\n\n"
                ]

                for deal in deals_found:  # Show all deals
                    message_parts.append(f"**{deal['name']}**\n")
                    message_parts.append(f"{deal['deal_reason']}\n")
                    message_parts.append(f"💰 {deal['current_price']}")
                    if deal["discount_percent"] > 0:
                        message_parts.append(f" ~~{deal['original_price']}~~")
                    if deal["lowest_price"] != "N/A":
                        message_parts.append(f" | Lowest ever: ${deal['lowest_price']}")
                    message_parts.append(
                        f"\n🔗 <https://store.steampowered.com/app/{deal['app_id']}>\n\n"
                    )

                final_message = "".join(message_parts)
                message_chunks = split_message(final_message)
                for chunk in message_chunks:
                    await loading_message.channel.send(content=chunk)
                await loading_message.delete()
                logger.info(
                    f"Deals: Found {len(deals_found)} deals for {user_name_for_log}"
                )
            else:
                await loading_message.edit(
                    content=f"📊 **No significant deals found** among {games_checked} games checked.\n\n💡 Try the `!force_deals` command (admin only) for more lenient deal detection."
                )
                logger.info(
                    f"Deals: No deals found for {user_name_for_log} among {games_checked} games"
                )

        except Exception as e:
            logger.critical(
                f"Deals: Critical error during deals check: {e}", exc_info=True
            )
            await loading_message.edit(
                content="❌ An unexpected error occurred while checking for deals."
            )
            await send_admin_dm(self.bot, f"Deals critical error: {e}")


def setup(bot):
    steam_family(bot)
