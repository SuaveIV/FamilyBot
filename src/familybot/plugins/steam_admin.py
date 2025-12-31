import time
from datetime import datetime
import requests
from interactions import Extension, GuildText
from interactions.ext.prefixed_commands import PrefixedContext, prefixed_command

from familybot.config import (
    ADMIN_DISCORD_ID,
    STEAMWORKS_API_KEY,
    WISHLIST_CHANNEL_ID,
)
from familybot.lib.database import (
    cache_game_details,
    cache_wishlist,
    get_cached_game_details,
    get_cached_wishlist,
    load_family_members_from_db,
)
from familybot.lib.familly_game_manager import get_saved_games
from familybot.lib.family_utils import find_in_2d_list, format_message
from familybot.lib.logging_config import get_logger, log_private_profile_detection
from familybot.lib.types import FamilyBotClient
from familybot.lib.utils import ProgressTracker, get_lowest_price, split_message
from familybot.lib.steam_api_manager import SteamAPIManager
from familybot.lib.steam_helpers import send_admin_dm

logger = get_logger(__name__)


class steam_admin(Extension):
    def __init__(self, bot: FamilyBotClient):
        self.bot: FamilyBotClient = bot
        self.steam_api_manager = SteamAPIManager()
        self.steam_api = self.steam_api_manager.steam_api

    @prefixed_command(name="force")
    async def force_new_game_command(self, ctx: PrefixedContext):
        if str(ctx.author_id) == str(ADMIN_DISCORD_ID) and ctx.guild is None:
            await ctx.send("Forcing new game notification check...")
            from familybot.lib.plugin_admin_actions import force_new_game_action

            result = await force_new_game_action()
            await ctx.send(result["message"])
            # Also post the result message to the wishlist channel
            await self.bot.send_to_channel(
                WISHLIST_CHANNEL_ID, result["message"]
            )  # ignore
            logger.info("Force new game notification posted to both DM and channel.")
            await self.bot.send_log_dm("Force Notification")  # ignore
        else:
            await ctx.send(
                "You do not have permission to use this command, or it must be used in DMs."
            )

    @prefixed_command(name="force_wishlist")
    async def force_wishlist_command(self, ctx: PrefixedContext):
        if str(ctx.author_id) == str(ADMIN_DISCORD_ID) and ctx.guild is None:
            await ctx.send("Forcing wishlist refresh...")
            from familybot.lib.plugin_admin_actions import force_wishlist_action

            result = await force_wishlist_action()
            await ctx.send(result["message"])
            logger.info("Force wishlist refresh initiated by admin.")
            await self.bot.send_log_dm("Force Wishlist")  # ignore
        else:
            await ctx.send(
                "You do not have permission to use this command, or it must be used in DMs."
            )

    @prefixed_command(name="force_deals")
    async def force_deals_command(
        self, ctx: PrefixedContext, target_friendly_name: str | None = None
    ):
        """
        Admin command to force check deals for a specific user's wishlist or all wishlists.
        Usage: !force_deals [friendly_name]
        If friendly_name is provided, checks only that user's wishlist.
        If no friendly_name is provided, checks all family wishlists.
        """
        if str(ctx.author_id) != str(ADMIN_DISCORD_ID) or ctx.guild is not None:
            await ctx.send(
                "You do not have permission to use this command, or it must be used in DMs."
            )
            return

        start_time = time.time()  # Initialize start time for tracking progress
        await ctx.send("🔍 **Forcing deals check and posting to wishlist channel...**")

        try:
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
                    await ctx.send(
                        f"🔍 **Checking deals for {target_friendly_name}'s wishlist...**"
                    )
                else:
                    await ctx.send(
                        f"❌ Friendly name '{target_friendly_name}' not found. Available names: {', '.join(current_family_members.values())}"
                    )
                    return
            else:
                target_user_steam_ids = list(current_family_members.keys())
                await ctx.send("🔍 **Forcing deals check for all family wishlists...**")

            # Collect wishlist games from the target user(s)
            global_wishlist: list[list] = []
            for user_steam_id in target_user_steam_ids:
                user_name_for_log = current_family_members.get(
                    user_steam_id, f"Unknown ({user_steam_id})"
                )

                # Try to get cached wishlist first
                cached_wishlist = get_cached_wishlist(user_steam_id)
                if cached_wishlist is not None:
                    logger.info(
                        f"Force deals: Using cached wishlist for {user_name_for_log} ({len(cached_wishlist)} items)"
                    )
                    for app_id in cached_wishlist:
                        # Ensure app_id is added with its interested users
                        if app_id not in [item[0] for item in global_wishlist]:
                            global_wishlist.append([app_id, [user_steam_id]])
                        else:
                            for item in global_wishlist:
                                if item[0] == app_id:
                                    item[1].append(user_steam_id)
                                    break
                else:
                    # If not cached, fetch fresh wishlist data from API
                    if (
                        not STEAMWORKS_API_KEY
                        or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE"
                    ):
                        logger.warning(
                            f"Force deals: Cannot fetch wishlist for {user_name_for_log} - Steam API key not configured"
                        )
                        continue

                    logger.info(
                        f"Force deals: Fetching fresh wishlist from API for {user_name_for_log}"
                    )

                    try:
                        if not self.steam_api:
                            log_private_profile_detection(
                                logger, user_name_for_log, user_steam_id, "wishlist"
                            )
                            continue
                        await self.steam_api_manager.rate_limit_steam_api()
                        wishlist_json = self.steam_api.call(
                            "IWishlistService.GetWishlist", steamid=user_steam_id
                        )
                        if not wishlist_json:
                            log_private_profile_detection(
                                logger, user_name_for_log, user_steam_id, "wishlist"
                            )
                            continue
                        wishlist_items = wishlist_json.get("response", {}).get(
                            "items", []
                        )
                        if not wishlist_items:
                            logger.info(
                                f"Force deals: No items found in {user_name_for_log}'s wishlist."
                            )
                            continue

                        # Extract app IDs and add to global wishlist
                        user_wishlist_appids = []
                        for game_item in wishlist_items:
                            app_id = str(game_item.get("appid"))
                            if not app_id:
                                logger.warning(
                                    f"Force deals: Skipping wishlist item due to missing appid: {game_item}"
                                )
                                continue

                            user_wishlist_appids.append(app_id)
                            if app_id not in [item[0] for item in global_wishlist]:
                                global_wishlist.append([app_id, [user_steam_id]])
                            else:
                                # Add user to existing entry
                                for item in global_wishlist:
                                    if item[0] == app_id:
                                        item[1].append(user_steam_id)
                                        break

                        # Cache the wishlist for 2 hours
                        cache_wishlist(
                            user_steam_id, user_wishlist_appids, cache_hours=2
                        )
                        logger.info(
                            f"Force deals: Fetched and cached {len(user_wishlist_appids)} wishlist items for {user_name_for_log}"
                        )

                    except Exception as e:
                        logger.error(
                            f"Force deals: Error fetching wishlist for {user_name_for_log}: {e}"
                        )
                        await send_admin_dm(
                            self.bot,
                            f"Force deals wishlist error for {user_name_for_log}: {e}",
                        )
                        continue

            if not global_wishlist:
                await ctx.send(
                    "❌ No wishlist games found to check for deals. This could be due to private profiles or empty wishlists."
                )
                return

            deals_found: list = []
            games_checked = 0
            total_games = len(global_wishlist)
            progress_tracker = ProgressTracker(total_games)

            await ctx.send(f"📊 **Checking {total_games} games for deals...**")

            for index, item in enumerate(global_wishlist):
                app_id = item[0]
                interested_users = item[1]
                games_checked += 1

                # Report progress using ProgressTracker
                if progress_tracker.should_report_progress(index + 1):
                    context_info = f"games checked | {len(deals_found)} deals found"
                    progress_msg = progress_tracker.get_progress_message(
                        index + 1, context_info
                    )
                    await ctx.send(progress_msg)

                try:
                    # Get cached game details first
                    cached_game = get_cached_game_details(app_id)
                    if cached_game:
                        game_data = cached_game
                    else:
                        # If not cached, fetch from API with enhanced retry logic
                        await self.steam_api_manager.rate_limit_steam_store_api()
                        game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                        app_info_response = (
                            await self.steam_api_manager.make_request_with_retry(
                                game_url
                            )
                        )
                        if app_info_response is None:
                            continue
                        game_info_json = app_info_response.json()
                        if not game_info_json:
                            continue

                        game_data = game_info_json.get(str(app_id), {}).get("data")
                        if not game_data:
                            continue

                        # Cache the game details
                        cache_game_details(app_id, game_data, permanent=True)

                    game_name = game_data.get("name", f"Unknown Game ({app_id})")
                    # Handle both cached data (price_data) and fresh API data (price_overview)
                    price_overview = game_data.get("price_overview") or game_data.get(
                        "price_data"
                    )

                    if not price_overview:
                        logger.debug(
                            f"Force deals: No price data found for {app_id} ({game_name})"
                        )
                        continue

                    # Check if game is on sale
                    discount_percent = price_overview.get("discount_percent", 0)
                    current_price = price_overview.get("final_formatted", "N/A")
                    original_price = price_overview.get(
                        "initial_formatted", current_price
                    )

                    # Get historical low price
                    lowest_price = get_lowest_price(int(app_id))

                    # Determine if this is a good deal (more lenient criteria for force command)
                    is_good_deal = False
                    deal_reason = ""

                    if discount_percent >= 30:  # Lower threshold for force command
                        is_good_deal = True
                        deal_reason = f"🔥 **{discount_percent}% OFF**"
                    elif discount_percent >= 15 and lowest_price != "N/A":
                        # Check if current price is close to historical low
                        try:
                            current_price_num = (
                                float(price_overview.get("final", 0)) / 100
                            )
                            lowest_price_num = float(lowest_price)
                            if (
                                current_price_num <= lowest_price_num * 1.2
                            ):  # Within 20% of historical low
                                is_good_deal = True
                                deal_reason = f"💎 **Near Historical Low** ({discount_percent}% off)"
                        except (ValueError, TypeError):
                            pass

                    if is_good_deal:
                        user_names = [
                            current_family_members.get(uid, "Unknown")
                            for uid in interested_users
                        ]
                        deal_info = {
                            "name": game_name,
                            "app_id": app_id,
                            "current_price": current_price,
                            "original_price": original_price,
                            "discount_percent": discount_percent,
                            "lowest_price": lowest_price,
                            "deal_reason": deal_reason,
                            "interested_users": user_names,
                        }
                        deals_found.append(deal_info)

                except Exception as e:
                    logger.warning(
                        f"Force deals: Error checking deals for game {app_id}: {e}"
                    )
                    continue

            # Format and send results to wishlist channel
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
                        # Handle both formatted ($X.XX) and unformatted (X.XX) prices
                        lowest_price = deal["lowest_price"]
                        if lowest_price.startswith("$"):
                            message_parts.append(f" | Lowest ever: {lowest_price}")
                        else:
                            message_parts.append(f" | Lowest ever: ${lowest_price}")
                    message_parts.append(
                        f"\n👥 Wanted by: {', '.join(deal['interested_users'][:3])}"
                    )
                    if len(deal["interested_users"]) > 3:
                        message_parts.append(
                            f" +{len(deal['interested_users']) - 3} more"
                        )
                    message_parts.append(
                        f"\n🔗 <https://store.steampowered.com/app/{deal['app_id']}>\n\n"
                    )

                final_message = "".join(message_parts)
                message_chunks = split_message(final_message)

                # Send to wishlist channel
                try:
                    for chunk in message_chunks:
                        await self.bot.send_to_channel(
                            WISHLIST_CHANNEL_ID, chunk
                        )  # ignore
                    # Also send the same message as a DM to the admin
                    admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
                    if admin_user is not None:
                        for chunk in message_chunks:
                            await admin_user.send(chunk)
                    await ctx.send(
                        f"✅ **Force deals complete!** Posted {len(deals_found)} deals to wishlist channel and sent DM to admin."
                    )
                    logger.info(
                        f"Force deals: Posted {len(deals_found)} deals to wishlist channel and sent DM to admin"
                    )
                    await self.bot.send_log_dm("Force Deals")  # ignore
                except Exception as e:
                    logger.error(
                        f"Force deals: Error posting to wishlist channel or sending DM: {e}"
                    )
                    await ctx.send(
                        f"❌ **Error posting deals to channel or sending DM:** {e}"
                    )
                    await send_admin_dm(
                        self.bot, f"Force deals channel or DM error: {e}"
                    )
            else:
                await ctx.send(
                    f"📊 **Force deals complete!** No significant deals found among {games_checked} games checked."
                )
                logger.info(f"Force deals: No deals found among {games_checked} games")

        except Exception as e:
            logger.critical(
                f"Force deals: Critical error during force deals check: {e}",
                exc_info=True,
            )
            await ctx.send(f"❌ **Critical error during force deals:** {e}")
            await send_admin_dm(self.bot, f"Force deals critical error: {e}")
        finally:
            elapsed_time = time.time() - start_time
            logger.info(f"force_deals_command completed in {elapsed_time:.2f} seconds")

    @prefixed_command(name="force_deals_unlimited")
    async def force_deals_unlimited_command(self, ctx: PrefixedContext):
        """
        Admin command to force check deals for ALL wishlist games (no limit) and post results to the wishlist channel.
        Only posts deals for games that are family sharing enabled.
        """
        if str(ctx.author_id) != str(ADMIN_DISCORD_ID) or ctx.guild is not None:
            await ctx.send(
                "You do not have permission to use this command, or it must be used in DMs."
            )
            return

        start_time = time.time()
        await ctx.send(
            "🔍 **Forcing unlimited deals check and posting to wishlist channel...** (no game limit, family sharing only)"
        )
        try:
            current_family_members = load_family_members_from_db()
            all_unique_steam_ids_to_check = set(current_family_members.keys())
            global_wishlist: list[list] = []
            for user_steam_id in all_unique_steam_ids_to_check:
                cached_wishlist = get_cached_wishlist(user_steam_id)
                if cached_wishlist is not None:
                    for app_id in cached_wishlist:
                        if app_id not in [item[0] for item in global_wishlist]:
                            global_wishlist.append([app_id, [user_steam_id]])
                        else:
                            for item in global_wishlist:
                                if item[0] == app_id:
                                    item[1].append(user_steam_id)
                                    break
            if not global_wishlist:
                await ctx.send("❌ No wishlist games found to check for deals.")
                return
            deals_found = []
            games_checked = 0
            for item in global_wishlist:
                app_id = item[0]
                interested_users = item[1]
                games_checked += 1
                try:
                    cached_game = get_cached_game_details(app_id)
                    if cached_game:
                        game_data = cached_game
                    else:
                        await self.steam_api_manager.rate_limit_steam_store_api()
                        game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                        app_info_response = requests.get(game_url, timeout=10)
                        game_info_json = app_info_response.json()
                        if not game_info_json:
                            continue
                        game_data = game_info_json.get(str(app_id), {}).get("data")
                        if not game_data:
                            continue
                        cache_game_details(app_id, game_data, permanent=True)
                    # Only include games that are family sharing enabled
                    if not game_data.get("is_family_shared", False):
                        continue
                    game_name = game_data.get("name", f"Unknown Game ({app_id})")
                    # Handle both cached data (price_data) and fresh API data (price_overview)
                    price_overview = game_data.get("price_overview") or game_data.get(
                        "price_data"
                    )
                    if not price_overview:
                        logger.debug(
                            f"Force deals unlimited: No price data found for {app_id} ({game_name})"
                        )
                        continue
                    discount_percent = price_overview.get("discount_percent", 0)
                    current_price = price_overview.get("final_formatted", "N/A")
                    original_price = price_overview.get(
                        "initial_formatted", current_price
                    )
                    lowest_price = get_lowest_price(int(app_id))
                    is_good_deal = False
                    deal_reason = ""
                    if discount_percent >= 30:
                        is_good_deal = True
                        deal_reason = f"🔥 **{discount_percent}% OFF**"
                    elif discount_percent >= 15 and lowest_price != "N/A":
                        try:
                            current_price_num = (
                                float(price_overview.get("final", 0)) / 100
                            )
                            lowest_price_num = float(lowest_price)
                            if current_price_num <= lowest_price_num * 1.2:
                                is_good_deal = True
                                deal_reason = f"💎 **Near Historical Low** ({discount_percent}% off)"
                        except (ValueError, TypeError):
                            pass
                    if is_good_deal:
                        user_names = [
                            current_family_members.get(uid, "Unknown")
                            for uid in interested_users
                        ]
                        deal_info = {
                            "name": game_name,
                            "app_id": app_id,
                            "current_price": current_price,
                            "original_price": original_price,
                            "discount_percent": discount_percent,
                            "lowest_price": lowest_price,
                            "deal_reason": deal_reason,
                            "interested_users": user_names,
                        }
                        deals_found.append(deal_info)
                except Exception as e:
                    logger.warning(
                        f"Force deals unlimited: Error checking deals for game {app_id}: {e}"
                    )
                    continue
            if deals_found:
                message_parts = [
                    f"🎯 **Current Deals Alert (Unlimited, Family Sharing Only)** (found {len(deals_found)} deals from {games_checked} games checked):\n\n"
                ]
                for deal in deals_found:
                    message_parts.append(f"**{deal['name']}**\n")
                    message_parts.append(f"{deal['deal_reason']}\n")
                    message_parts.append(f"💰 {deal['current_price']}")
                    if deal["discount_percent"] > 0:
                        message_parts.append(f" ~~{deal['original_price']}~~")
                    if deal["lowest_price"] != "N/A":
                        # Handle both formatted ($X.XX) and unformatted (X.XX) prices
                        lowest_price = deal["lowest_price"]
                        if lowest_price.startswith("$"):
                            message_parts.append(f" | Lowest ever: {lowest_price}")
                        else:
                            message_parts.append(f" | Lowest ever: ${lowest_price}")
                    message_parts.append(
                        f"\n👥 Wanted by: {', '.join(deal['interested_users'][:3])}"
                    )
                    if len(deal["interested_users"]) > 3:
                        message_parts.append(
                            f" +{len(deal['interested_users']) - 3} more"
                        )
                    message_parts.append(
                        f"\n🔗 <https://store.steampowered.com/app/{deal['app_id']}>\n\n"
                    )
                final_message = "".join(message_parts)
                message_chunks = split_message(final_message)
                try:
                    for chunk in message_chunks:
                        await self.bot.send_to_channel(
                            WISHLIST_CHANNEL_ID, chunk
                        )  # ignore
                    await ctx.send(
                        f"✅ **Force deals unlimited complete!** Posted {len(deals_found)} deals to wishlist channel."
                    )
                    logger.info(
                        f"Force deals unlimited: Posted {len(deals_found)} deals to wishlist channel"
                    )
                    await self.bot.send_log_dm("Force Deals Unlimited")  # ignore
                except Exception as e:
                    logger.error(
                        f"Force deals unlimited: Error posting to wishlist channel: {e}"
                    )
                    await ctx.send(f"❌ **Error posting deals to channel:** {e}")
                    await send_admin_dm(
                        self.bot, f"Force deals unlimited channel error: {e}"
                    )
            else:
                await ctx.send(
                    f"📊 **Force deals unlimited complete!** No significant deals found among {games_checked} games checked."
                )
                logger.info(
                    f"Force deals unlimited: No deals found among {games_checked} games"
                )
        except Exception as e:
            logger.critical(
                f"Force deals unlimited: Critical error during force deals unlimited check: {e}",
                exc_info=True,
            )
            await ctx.send(f"❌ **Critical error during force deals unlimited:** {e}")
            await send_admin_dm(self.bot, f"Force deals unlimited critical error: {e}")
        finally:
            elapsed_time = time.time() - start_time
            logger.info(
                f"force_deals_unlimited_command completed in {elapsed_time:.2f} seconds"
            )

    @prefixed_command(name="purge_cache")
    async def purge_cache_command(self, ctx: PrefixedContext):
        """
        Admin command to purge game details cache and force fresh data with USD pricing.
        """
        if str(ctx.author_id) != str(ADMIN_DISCORD_ID) or ctx.guild is not None:
            await ctx.send(
                "You do not have permission to use this command, or it must be used in DMs."
            )
            return

        await ctx.send("🗑️ **Purging game details cache...**")
        from familybot.lib.plugin_admin_actions import purge_game_details_cache_action

        result = await purge_game_details_cache_action()
        await ctx.send(result["message"])
        if result["success"]:
            logger.info("Admin purged game details cache via command.")
            await self.bot.send_log_dm("Cache Purge")
        else:
            await send_admin_dm(self.bot, f"Cache purge error: {result['message']}")

    @prefixed_command(name="full_library_scan")
    async def full_library_scan_command(self, ctx: PrefixedContext):
        """
        Admin command to scan all family members' complete game libraries.
        Uses rate limiting to avoid API limits and caches all owned games.
        """
        if str(ctx.author_id) != str(ADMIN_DISCORD_ID) or ctx.guild is not None:
            await ctx.send(
                "You do not have permission to use this command, or it must be used in DMs."
            )
            return

        if (
            not STEAMWORKS_API_KEY
            or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE"
        ):
            await ctx.send(
                "❌ Steam API key is not configured. Cannot perform full library scan."
            )
            return

        start_time = datetime.now()
        await ctx.send(
            "🔄 **Starting full library scan...**\nThis will scan all family members' complete game libraries with rate limiting to avoid API limits.\n⏱️ This may take several minutes depending on library sizes."
        )

        try:
            current_family_members = load_family_members_from_db()
            all_unique_steam_ids_to_check = set(current_family_members.keys())

            if not all_unique_steam_ids_to_check:
                await ctx.send("❌ No family members found to scan.")
                return

            total_members = len(all_unique_steam_ids_to_check)
            await ctx.send(f"📊 **Found {total_members} family members to scan.**")

            total_games_processed = 0
            total_games_cached = 0
            processed_members = 0
            error_count = 0

            for user_steam_id in all_unique_steam_ids_to_check:
                user_name_for_log = current_family_members.get(
                    user_steam_id, f"Unknown ({user_steam_id})"
                )
                processed_members += 1

                try:
                    # Get user's owned games
                    if not self.steam_api:
                        error_count += 1
                        logger.warning(
                            f"Full library scan: Steam API not configured. Cannot fetch games for {user_name_for_log}."
                        )
                        continue
                    await self.steam_api_manager.rate_limit_steam_api()
                    owned_games_json = self.steam_api.call(
                        "IPlayerService.GetOwnedGames",
                        steamid=user_steam_id,
                        include_appinfo=1,
                        include_played_free_games=1,
                    )
                    if not owned_games_json:
                        error_count += 1
                        continue

                    games = owned_games_json.get("response", {}).get("games", [])
                    if not games:
                        logger.info(
                            f"Full library scan: No games found for {user_name_for_log} (private profile?)"
                        )
                        continue

                    user_games_cached = 0
                    await ctx.send(
                        f"⏳ **Processing {user_name_for_log}**: {len(games)} games found..."
                    )

                    # Process each game with rate limiting and progress updates
                    for i, game in enumerate(games):
                        app_id = str(game.get("appid"))
                        if not app_id:
                            continue

                        total_games_processed += 1

                        # Check if we already have cached details
                        cached_game = get_cached_game_details(app_id)
                        if cached_game:
                            logger.debug(
                                f"Full library scan: Using cached details for AppID: {app_id}"
                            )
                            continue

                        # Fetch game details from Steam Store API
                        try:
                            await self.steam_api_manager.rate_limit_steam_store_api()
                            game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                            logger.debug(
                                f"Full library scan: Fetching details for AppID: {app_id}"
                            )

                            game_info_response = requests.get(game_url, timeout=10)
                            game_info_json = game_info_response.json()

                            if not game_info_json:
                                continue

                            game_data = game_info_json.get(str(app_id), {}).get("data")
                            if not game_data:
                                logger.debug(
                                    f"Full library scan: No data for AppID {app_id}"
                                )
                                continue

                            # Cache the game details permanently
                            cache_game_details(app_id, game_data, permanent=True)
                            user_games_cached += 1
                            total_games_cached += 1

                        except Exception as e:
                            logger.warning(
                                f"Full library scan: Error processing game {app_id} for {user_name_for_log}: {e}"
                            )
                            continue

                    await ctx.send(
                        f"✅ **{user_name_for_log} complete**: {user_games_cached} new games cached ({processed_members}/{total_members})"
                    )

                except Exception as e:
                    error_count += 1
                    logger.error(
                        f"Full library scan: Error processing {user_name_for_log}: {e}",
                        exc_info=True,
                    )
                    await ctx.send(f"❌ **Error processing {user_name_for_log}**: {e}")

            # Final summary
            end_time = datetime.now()
            scan_duration = end_time - start_time

            summary_msg = "✅ **Full library scan complete!**\n"
            summary_msg += (
                f"⏱️ **Duration:** {scan_duration.total_seconds():.1f} seconds\n"
            )
            summary_msg += (
                f"👥 **Members processed:** {processed_members}/{total_members}\n"
            )
            summary_msg += f"🎮 **Games processed:** {total_games_processed}\n"
            summary_msg += f"💾 **New games cached:** {total_games_cached}\n"
            if error_count > 0:
                summary_msg += f"❌ **Errors:** {error_count}\n"
            summary_msg += (
                "🚀 **All future commands will benefit from cached game data!"
            )

            await ctx.send(summary_msg)
            logger.info(
                f"Full library scan completed: {processed_members} members, {total_games_cached} games cached, {scan_duration.total_seconds():.1f}s duration"
            )
            await self.bot.send_log_dm("Full Library Scan")  # ignore

        except Exception as e:
            logger.critical(
                f"Full library scan: Critical error during scan: {e}", exc_info=True
            )
            await ctx.send(f"❌ **Critical error during full library scan:** {e}")
            await send_admin_dm(self.bot, f"Full library scan critical error: {e}")

    @prefixed_command(name="full_wishlist_scan")
    async def full_wishlist_scan_command(self, ctx: PrefixedContext):
        """
        Admin command to perform a comprehensive wishlist scan of ALL common games.
        Uses slower rate limiting to avoid API limits and provides progress updates.
        """
        if str(ctx.author_id) != str(ADMIN_DISCORD_ID) or ctx.guild is not None:
            await ctx.send(
                "You do not have permission to use this command, or it must be used in DMs."
            )
            return

        if (
            not STEAMWORKS_API_KEY
            or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE"
        ):
            await ctx.send(
                "❌ Steam API key is not configured. Cannot perform full wishlist scan."
            )
            return

        start_time = datetime.now()
        await ctx.send(
            "🔄 **Starting comprehensive wishlist scan...**\nThis will process ALL common wishlist games with slower rate limiting to avoid API limits.\n⏱️ This may take several minutes depending on the number of games."
        )

        try:
            # Step 1: Collect all wishlist data (same as regular refresh)
            logger.info("Full wishlist scan: Starting comprehensive scan...")
            global_wishlist: list[list] = []
            current_family_members = load_family_members_from_db()
            all_unique_steam_ids_to_check = set(current_family_members.keys())

            # Collect wishlists from all family members
            for user_steam_id in all_unique_steam_ids_to_check:
                user_name_for_log = current_family_members.get(
                    user_steam_id, f"Unknown ({user_steam_id})"
                )

                # Try to get cached wishlist first
                cached_wishlist = get_cached_wishlist(user_steam_id)
                if cached_wishlist is not None:
                    logger.info(
                        f"Full scan: Using cached wishlist for {user_name_for_log} ({len(cached_wishlist)} items)"
                    )
                    for app_id in cached_wishlist:
                        idx = find_in_2d_list(app_id, global_wishlist)
                        if idx is not None:
                            global_wishlist[idx][1].append(user_steam_id)
                        else:
                            global_wishlist.append([app_id, [user_steam_id]])
                    continue

                # If not cached, fetch from API
                logger.info(
                    f"Full scan: Fetching wishlist from API for {user_name_for_log}"
                )

                try:
                    if not self.steam_api:
                        logger.warning(
                            f"Full scan: Steam API key not configured. Cannot fetch wishlist for {user_name_for_log}."
                        )
                        continue

                    await self.steam_api_manager.rate_limit_steam_api()
                    wishlist_json = self.steam_api.call(
                        "IWishlistService.GetWishlist", steamid=user_steam_id
                    )
                    if not wishlist_json:
                        logger.info(
                            f"Full scan: {user_name_for_log}'s wishlist is private or empty."
                        )
                        continue
                    wishlist_items = wishlist_json.get("response", {}).get("items", [])
                    if not wishlist_items:
                        logger.info(
                            f"Full scan: No items found in {user_name_for_log}'s wishlist."
                        )
                        continue

                    # Extract app IDs for caching
                    user_wishlist_appids = []
                    for game_item in wishlist_items:
                        app_id = str(game_item.get("appid"))
                        if not app_id:
                            logger.warning(
                                f"Full scan: Skipping wishlist item due to missing appid: {game_item}"
                            )
                            continue

                        user_wishlist_appids.append(app_id)
                        idx = find_in_2d_list(app_id, global_wishlist)
                        if idx is not None:
                            global_wishlist[idx][1].append(user_steam_id)
                        else:
                            global_wishlist.append([app_id, [user_steam_id]])

                    # Cache the wishlist for 2 hours
                    cache_wishlist(user_steam_id, user_wishlist_appids, cache_hours=2)

                except Exception as e:
                    logger.critical(
                        f"Full scan: Error fetching/processing {user_name_for_log}'s wishlist: {e}",
                        exc_info=True,
                    )
                    await send_admin_dm(
                        self.bot, f"Full scan error for {user_name_for_log}: {e}"
                    )

            # Step 2: Collect ALL duplicate games (no limit)
            all_duplicate_games: list[list] = []
            for item in global_wishlist:
                app_id = item[0]
                owner_steam_ids = item[1]
                if len(owner_steam_ids) > 1:
                    all_duplicate_games.append(item)

            if not all_duplicate_games:
                await ctx.send(
                    "✅ **Full scan complete!** No common wishlist games found."
                )
                return

            # Sort by AppID (descending) for consistent processing order
            sorted_all_duplicate_games = sorted(
                all_duplicate_games, key=lambda x: x[0], reverse=True
            )

            total_games = len(sorted_all_duplicate_games)
            await ctx.send(
                f"📊 **Found {total_games} common wishlist games to process.**\n🐌 Using {self.steam_api_manager.FULL_SCAN_RATE_LIMIT}s delays between API calls to avoid rate limits..."
            )

            # Step 3: Process ALL games with slower rate limiting
            duplicate_games_for_display: list = []
            saved_game_appids = {item[0] for item in get_saved_games()}
            processed_count = 0
            skipped_count = 0
            error_count = 0

            # Initialize progress tracker with more frequent updates for better user feedback
            total_games = len(sorted_all_duplicate_games)
            progress_tracker = ProgressTracker(
                total_games, progress_interval=5
            )  # Report every 5% instead of 10%

            for item in sorted_all_duplicate_games:
                app_id = item[0]
                processed_count += 1

                # Report progress using ProgressTracker
                if progress_tracker.should_report_progress(processed_count):
                    context_info = f"games | ✅ {len(duplicate_games_for_display)} qualified | ⏭️ {skipped_count} skipped"
                    if error_count > 0:
                        context_info += f" | ❌ {error_count} errors"
                    progress_msg = progress_tracker.get_progress_message(
                        processed_count, context_info
                    )
                    await ctx.send(progress_msg)

                try:
                    # Check if we have cached game details first
                    cached_game = get_cached_game_details(app_id)
                    if cached_game:
                        logger.info(
                            f"Full scan: Using cached game details for AppID: {app_id}"
                        )
                        game_data = cached_game
                    else:
                        # Use slower rate limiting for full scan
                        await self.steam_api_manager.rate_limit_full_scan()

                        game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                        logger.info(
                            f"Full scan: Fetching app details for AppID: {app_id} ({processed_count}/{total_games})"
                        )

                        game_info_response = requests.get(game_url, timeout=10)
                        game_info_json = game_info_response.json()
                        if not game_info_json:
                            error_count += 1
                            continue

                        game_data = game_info_json.get(str(app_id), {}).get("data")
                        if not game_data:
                            logger.warning(
                                f"Full scan: No game data found for AppID {app_id}"
                            )
                            error_count += 1
                            continue

                        # Cache the game details permanently
                        cache_game_details(app_id, game_data, permanent=True)

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
                        logger.info(
                            f"Full scan: Added {game_data.get('name', 'Unknown')} to display list"
                        )
                    else:
                        skipped_count += 1
                        logger.debug(
                            f"Full scan: Skipped {app_id}: filtering criteria not met"
                        )

                except Exception as e:
                    error_count += 1
                    logger.critical(
                        f"Full scan: Error processing game {app_id}: {e}", exc_info=True
                    )

            # Step 4: Update the wishlist channel with results
            end_time = datetime.now()
            scan_duration = end_time - start_time

            try:
                wishlist_channel = await self.bot.fetch_channel(WISHLIST_CHANNEL_ID)
                if not wishlist_channel or not isinstance(wishlist_channel, GuildText):
                    await ctx.send(
                        "❌ Could not access wishlist channel to update results."
                    )
                    return

                # Generate the message using the same format_message function
                wishlist_new_message = format_message(
                    duplicate_games_for_display, short=False
                )

                # Update the pinned message
                pinned_messages = await wishlist_channel.fetch_pinned_messages()
                if not pinned_messages:
                    message_obj = await wishlist_channel.send(wishlist_new_message)
                    await message_obj.pin()
                    logger.info(
                        f"Full scan: New wishlist message pinned in channel {WISHLIST_CHANNEL_ID}"
                    )
                else:
                    await pinned_messages[-1].edit(content=wishlist_new_message)
                    logger.info(
                        f"Full scan: Wishlist message updated in channel {WISHLIST_CHANNEL_ID}"
                    )

                # Send completion summary
                summary_msg = "✅ **Full wishlist scan complete!**\n"
                summary_msg += (
                    f"⏱️ **Duration:** {scan_duration.total_seconds():.1f} seconds\n"
                )
                summary_msg += f"📊 **Processed:** {processed_count} games\n"
                summary_msg += (
                    f"✅ **Qualified games:** {len(duplicate_games_for_display)}\n"
                )
                summary_msg += f"⏭️ **Skipped:** {skipped_count}\n"
                if error_count > 0:
                    summary_msg += f"❌ **Errors:** {error_count}\n"
                summary_msg += "📝 **Wishlist channel updated with all results.**"

                await ctx.send(summary_msg)
                logger.info(
                    f"Full wishlist scan completed: {processed_count} processed, {len(duplicate_games_for_display)} qualified, {scan_duration.total_seconds():.1f}s duration"
                )

            except Exception as e:
                logger.error(
                    f"Full scan: Error updating wishlist channel: {e}", exc_info=True
                )
                await ctx.send(
                    f"⚠️ **Scan completed but failed to update wishlist channel:** {e}"
                )
                await send_admin_dm(self.bot, f"Full scan channel update error: {e}")

        except Exception as e:
            logger.critical(
                f"Full scan: Critical error during comprehensive wishlist scan: {e}",
                exc_info=True,
            )
            await ctx.send(f"❌ **Critical error during full scan:** {e}")
            await send_admin_dm(self.bot, f"Full scan critical error: {e}")


def setup(bot):
    steam_admin(bot)
