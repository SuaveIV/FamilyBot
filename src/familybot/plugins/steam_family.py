# In src/familybot/plugins/steam_family.py

from interactions import Extension, listen, Task, IntervalTrigger, GuildText
from interactions.ext.prefixed_commands import prefixed_command, PrefixedContext
import requests
import json
import logging
import os
from datetime import datetime, timedelta
import sqlite3
import asyncio
import time # <<< Import time for time.time()

# Import necessary items from your config and lib modules
from familybot.config import (
    NEW_GAME_CHANNEL_ID, WISHLIST_CHANNEL_ID, FAMILY_STEAM_ID, FAMILY_USER_DICT, # FAMILY_USER_DICT kept for migration
    ADMIN_DISCORD_ID, STEAMWORKS_API_KEY, PROJECT_ROOT
)
from familybot.lib.family_utils import get_family_game_list_url, find_in_2d_list, format_message
from familybot.lib.familly_game_manager import get_saved_games, set_saved_games
from familybot.lib.database import (
    get_db_connection, get_cached_game_details, cache_game_details,
    get_cached_wishlist, cache_wishlist, get_cached_family_library, cache_family_library
)
from familybot.lib.utils import get_lowest_price, ProgressTracker, truncate_message_list
from familybot.lib.types import FamilyBotClient, DISCORD_MESSAGE_LIMIT

# Setup logging for this specific module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Migration Flag for Family Members ---
_family_members_migrated_this_run = False


class steam_family(Extension):
    # --- RATE LIMITING CONSTANTS ---
    MAX_WISHLIST_GAMES_TO_PROCESS = 100 # Limit appdetails calls to 100 games per run
    STEAM_API_RATE_LIMIT = 3.0 # Minimum seconds between Steam API calls (e.g., GetOwnedGames, GetFamilySharedApps) - increased to prevent 429 errors
    STEAM_STORE_API_RATE_LIMIT = 2.0 # Minimum seconds between Steam Store API calls (e.g., appdetails) - increased to prevent 429 errors
    FULL_SCAN_RATE_LIMIT = 5.0 # Minimum seconds between Steam Store API calls for full wishlist scans - increased to prevent 429 errors
    # --- END RATE LIMITING CONSTANTS ---

    def __init__(self, bot: FamilyBotClient):
        self.bot: FamilyBotClient = bot  # Explicit type annotation for the bot attribute
        # Rate limiting tracking
        self._last_steam_api_call = 0.0
        self._last_steam_store_api_call = 0.0
        logger.info("Steam Family Plugin loaded")

    async def _rate_limit_steam_api(self) -> None:
        """Enforce rate limiting for Steam API calls (non-storefront)."""
        current_time = time.time()
        time_since_last_call = current_time - self._last_steam_api_call
        
        if time_since_last_call < self.STEAM_API_RATE_LIMIT:
            sleep_time = self.STEAM_API_RATE_LIMIT - time_since_last_call
            logger.debug(f"Rate limiting Steam API call, sleeping for {sleep_time:.2f} seconds")
            await asyncio.sleep(sleep_time)
        
        self._last_steam_api_call = time.time()

    async def _rate_limit_steam_store_api(self) -> None:
        """Enforce rate limiting for Steam Store API calls (e.g., appdetails)."""
        current_time = time.time()
        time_since_last_call = current_time - self._last_steam_store_api_call
        
        if time_since_last_call < self.STEAM_STORE_API_RATE_LIMIT:
            sleep_time = self.STEAM_STORE_API_RATE_LIMIT - time_since_last_call
            logger.debug(f"Rate limiting Steam Store API call, sleeping for {sleep_time:.2f} seconds")
            await asyncio.sleep(sleep_time)
        
        self._last_steam_store_api_call = time.time()

    async def _rate_limit_full_scan(self) -> None:
        """Enforce slower rate limiting for full wishlist scans to avoid hitting API limits."""
        current_time = time.time()
        time_since_last_call = current_time - self._last_steam_store_api_call
        
        if time_since_last_call < self.FULL_SCAN_RATE_LIMIT:
            sleep_time = self.FULL_SCAN_RATE_LIMIT - time_since_last_call
            logger.debug(f"Rate limiting full scan API call, sleeping for {sleep_time:.2f} seconds")
            await asyncio.sleep(sleep_time)
        
        self._last_steam_store_api_call = time.time()

    async def _send_admin_dm(self, message: str) -> None:
        """Helper to send error/warning messages to the bot admin via DM."""
        try:
            admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
            if admin_user is not None:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await admin_user.send(f"Steam Family Plugin Error ({now_str}): {message}")
            else:
                logger.error(f"Admin user with ID {ADMIN_DISCORD_ID} not found or could not be fetched. Cannot send DM.")
        except Exception as e:
            logger.error(f"Failed to send DM to admin {ADMIN_DISCORD_ID} (after initial fetch attempt): {e}")

    async def _handle_api_response(self, api_name: str, response: requests.Response) -> dict | None: # Fix type annotation syntax
        """Helper to process API responses, handle errors, and return JSON data."""
        try:
            response.raise_for_status()
            json_data = json.loads(response.text)
            return json_data
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for {api_name}: {e}. URL: {response.request.url}")
            await self._send_admin_dm(f"Req error {api_name}: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {api_name}: {e}. Raw: {response.text[:200]}")
            await self._send_admin_dm(f"JSON error {api_name}: {e}")
        except Exception as e:
            logger.critical(f"An unexpected error occurred processing {api_name} response: {e}", exc_info=True)
            await self._send_admin_dm(f"Critical error {api_name}: {e}")
        return None

    async def _load_family_members_from_db(self) -> dict:
        """
        Loads family member data (steam_id: friendly_name) from the database,
        performing a one-time migration from config.yml if necessary.
        """
        global _family_members_migrated_this_run
        members = {}
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            if not _family_members_migrated_this_run:
                cursor.execute("SELECT COUNT(*) FROM family_members")
                if cursor.fetchone()[0] == 0 and FAMILY_USER_DICT:
                    logger.info("Database: 'family_members' table is empty. Attempting to migrate from config.yml.")
                    config_members_to_insert = []
                    for steam_id, name in FAMILY_USER_DICT.items():
                        config_members_to_insert.append((steam_id, name, None))
                    
                    try:
                        if config_members_to_insert:
                            cursor.executemany("INSERT OR IGNORE INTO family_members (steam_id, friendly_name, discord_id) VALUES (?, ?, ?)", config_members_to_insert)
                            conn.commit()
                            logger.info(f"Database: Migrated {len(config_members_to_insert)} family members from config.yml.")
                            _family_members_migrated_this_run = True
                        else:
                            logger.info("Database: No family members found in config.yml for migration.")
                            _family_members_migrated_this_run = True
                    except sqlite3.Error as e:
                        logger.error(f"Database: Error during family_members migration from config.yml: {e}")
                else:
                    logger.debug("Database: 'family_members' table already has data or config.yml is empty. Skipping config.yml migration.")
                    _family_members_migrated_this_run = True

            cursor.execute("SELECT steam_id, friendly_name FROM family_members")
            for row in cursor.fetchall():
                members[row["steam_id"]] = row["friendly_name"]
            logger.debug(f"Loaded {len(members)} family members from database.")

        except sqlite3.Error as e:
            logger.error(f"Error reading family members from DB: {e}")
            await self._send_admin_dm(f"Error reading family members from DB: {e}")
        finally:
            if conn:
                conn.close()
        return members

    async def _load_all_registered_users_from_db(self) -> dict:
        """Loads all registered users (discord_id: steam_id) from the database."""
        users = {}
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT discord_id, steam_id FROM users")
            for row in cursor.fetchall():
                users[row["discord_id"]] = row["steam_id"]
            logger.debug(f"Loaded {len(users)} registered users from database.")
        except sqlite3.Error as e:
            logger.error(f"Error reading all registered users from DB: {e}")
            await self._send_admin_dm(f"Error reading all registered users from DB: {e}")
        finally:
            if conn:
                conn.close()
        return users

    """
    [help]|coop| it returns all the family shared multiplayer games in the shared library with a given numbers of copies| !coop NUMBER_OF_COPIES | ***This command can be used in bot DM***
    """
    @prefixed_command(name="coop")
    async def coop_command(self, ctx: PrefixedContext, number_str: str | None = None):
        start_time = time.time()  # Add this near the start of each command function

        if number_str is None:
            await ctx.send("❌ **Missing required parameter!**\n\n**Usage:** `!coop NUMBER_OF_COPIES`\n**Example:** `!coop 2` (to find games with 2+ copies)\n\n**Note:** The number must be greater than 1.")
            return
            
        try:
            number = int(number_str)
        except ValueError:
            await ctx.send("❌ **Invalid number format!**\n\n**Usage:** `!coop NUMBER_OF_COPIES`\n**Example:** `!coop 2` (to find games with 2+ copies)\n\nPlease provide a valid number.")
            return

        if number <= 1:
            await ctx.send("❌ **Invalid number!**\n\nThe number after the command must be greater than 1.\n**Example:** `!coop 2` (to find games with 2+ copies)")
            return

        loading_message = await ctx.send(f"Searching for games with {number} copies...")

        games_json = None
        try:
            # Try to get cached family library first
            cached_family_library = get_cached_family_library()
            if cached_family_library is not None:
                logger.info(f"Using cached family library ({len(cached_family_library)} games)")
                game_list = cached_family_library
            else:
                # If not cached, fetch from API
                await self._rate_limit_steam_api() # Apply rate limit before API call
                url_family_list = get_family_game_list_url()
                answer = requests.get(url_family_list, timeout=15)
                games_json = await self._handle_api_response("GetFamilySharedApps", answer)
                if not games_json:
                    await loading_message.edit(content="Error retrieving family game list.")
                    return

                game_list = games_json.get("response", {}).get("apps", [])
                if not game_list:
                    logger.warning("No games found in family game list response.")
                    await loading_message.edit(content="No games found in the family library.")
                    return
                
                # Cache the family library for 30 minutes
                cache_family_library(game_list, cache_minutes=30)

            game_array = []
            coop_game_names = []

            current_family_members = await self._load_family_members_from_db()

            for game in game_list:
                if game.get("exclude_reason") != 3 and len(game.get("owner_steamids", [])) >= number:
                    game_array.append(str(game.get("appid")))

            for game_appid in game_array:
                # Try to get cached game details first
                cached_game = get_cached_game_details(game_appid)
                if cached_game:
                    logger.info(f"Using cached game details for AppID: {game_appid}")
                    game_data = cached_game
                else:
                    # If not cached, fetch from API
                    await self._rate_limit_steam_store_api() # Apply store API rate limit
                    game_url = f"https://store.steampowered.com/api/appdetails?appids={game_appid}&cc=us&l=en"
                    logger.info(f"Fetching app details from API for AppID: {game_appid} for coop check")
                    app_info_response = requests.get(game_url, timeout=10)
                    game_info_json = await self._handle_api_response("AppDetails", app_info_response)
                    if not game_info_json: continue

                    game_data = game_info_json.get(str(game_appid), {}).get("data")
                    if not game_data:
                        logger.warning(f"No game data found for AppID {game_appid} in app details response for coop check.")
                        continue
                    
                    # Cache the game details permanently (game details rarely change)
                    cache_game_details(game_appid, game_data, permanent=True)

                if game_data.get("type") == "game" and game_data.get("is_free") == False:
                    # Use cached boolean fields for faster performance
                    is_family_shared = game_data.get("is_family_shared", False)
                    is_multiplayer = game_data.get("is_multiplayer", False)
                    
                    if is_family_shared and is_multiplayer:
                            game_name = game_data.get("name", f"Unknown Game ({game_appid})")
                            
                            # Add pricing information if available
                            try:
                                current_price = game_data.get('price_overview', {}).get('final_formatted', 'N/A')
                                lowest_price = get_lowest_price(int(game_appid))
                                
                                price_info = []
                                if current_price != 'N/A':
                                    price_info.append(f"Current: {current_price}")
                                if lowest_price != 'N/A':
                                    price_info.append(f"Lowest: ${lowest_price}")
                                
                                if price_info:
                                    game_name += f" ({' | '.join(price_info)})"
                            except Exception as e:
                                logger.warning(f"Could not get pricing info for coop game {game_appid}: {e}")
                            
                            coop_game_names.append(game_name)
                    else:
                        logger.debug(f"Game {game_appid} is not categorized as family shared (ID 62).")

            if coop_game_names:
                # Use the utility function to handle message truncation
                header = '__Common shared multiplayer games__:\n'
                footer_template = "\n... and {count} more games!"
                final_message = truncate_message_list(coop_game_names, header, footer_template)
                await loading_message.edit(content=final_message)
            else:
                await loading_message.edit(content=f"No common shared multiplayer games found with {number} copies.")

        except ValueError as e: # Catch ValueError if webapi_token is missing
            logger.error(f"Error in coop_command: {e}")
            await loading_message.edit(content=f"Error: {e}. Cannot retrieve family games.")
            await self._send_admin_dm(f"Error in coop_command: {e}")
        except Exception as e:
            logger.critical(f"An unexpected error occurred in coop_command: {e}", exc_info=True)
            await loading_message.edit(content="An unexpected error occurred during common games search.")
            await self._send_admin_dm(f"Critical error coop command: {e}")


    @prefixed_command(name="force")
    async def force_new_game_command(self, ctx: PrefixedContext):
        if str(ctx.author_id) == str(ADMIN_DISCORD_ID) and ctx.guild is None:
            await ctx.send("Forcing new game notification check...")
            await self.send_new_game()
            logger.info("Force new game notification initiated by admin.")
            await self.bot.send_log_dm("Force Notification") # type: ignore
        else:
            await ctx.send("You do not have permission to use this command, or it must be used in DMs.")

    @prefixed_command(name="force_wishlist")
    async def force_wishlist_command(self, ctx: PrefixedContext):
        if str(ctx.author_id) == str(ADMIN_DISCORD_ID) and ctx.guild is None:
            await ctx.send("Forcing wishlist refresh...")
            await self.refresh_wishlist()
            logger.info("Force wishlist refresh initiated by admin.")
            await self.bot.send_log_dm("Force Wishlist") # type: ignore
        else:
            await ctx.send("You do not have permission to use this command, or it must be used in DMs.")

    @prefixed_command(name="force_deals")
    async def force_deals_command(self, ctx: PrefixedContext):
        """
        Admin command to force check deals and post results to the wishlist channel.
        """
        if str(ctx.author_id) != str(ADMIN_DISCORD_ID) or ctx.guild is not None:
            await ctx.send("You do not have permission to use this command, or it must be used in DMs.")
            return

        start_time = time.time()  # Initialize start time for tracking progress
        await ctx.send("🔍 **Forcing deals check and posting to wishlist channel...**")
        
        try:
            current_family_members = await self._load_family_members_from_db()
            all_unique_steam_ids_to_check = set(current_family_members.keys())
            
            # Collect all wishlist games from family members
            global_wishlist = []
            for user_steam_id in all_unique_steam_ids_to_check:
                user_name_for_log = current_family_members.get(user_steam_id, f"Unknown ({user_steam_id})")
                
                # Try to get cached wishlist first
                cached_wishlist = get_cached_wishlist(user_steam_id)
                if cached_wishlist is not None:
                    logger.info(f"Force deals: Using cached wishlist for {user_name_for_log} ({len(cached_wishlist)} items)")
                    for app_id in cached_wishlist:
                        if app_id not in [item[0] for item in global_wishlist]:
                            global_wishlist.append([app_id, [user_steam_id]])
                        else:
                            # Add user to existing entry
                            for item in global_wishlist:
                                if item[0] == app_id:
                                    item[1].append(user_steam_id)
                                    break
            
            if not global_wishlist:
                await ctx.send("❌ No wishlist games found to check for deals.")
                return
            
            deals_found = []
            games_checked = 0
            max_games_to_check = 100  # Higher limit for force command
            total_games = min(len(global_wishlist), max_games_to_check)
            progress_tracker = ProgressTracker(total_games)

            await ctx.send(f"📊 **Checking {total_games} games for deals...**")

            for index, item in enumerate(global_wishlist[:max_games_to_check]):
                app_id = item[0]
                interested_users = item[1]
                games_checked += 1
                
                # Report progress using ProgressTracker
                if progress_tracker.should_report_progress(index + 1):
                    context_info = f"games checked | {len(deals_found)} deals found"
                    progress_msg = progress_tracker.get_progress_message(index + 1, context_info)
                    await ctx.send(progress_msg)
                
                try:
                    # Get cached game details first
                    cached_game = get_cached_game_details(app_id)
                    if cached_game:
                        game_data = cached_game
                    else:
                        # If not cached, fetch from API
                        await self._rate_limit_steam_store_api()
                        game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                        app_info_response = requests.get(game_url, timeout=10)
                        game_info_json = await self._handle_api_response("AppDetails (Force Deals)", app_info_response)
                        if not game_info_json: continue
                        
                        game_data = game_info_json.get(str(app_id), {}).get("data")
                        if not game_data: continue
                        
                        # Cache the game details
                        cache_game_details(app_id, game_data, permanent=True)
                    
                    game_name = game_data.get("name", f"Unknown Game ({app_id})")
                    price_overview = game_data.get("price_overview")
                    
                    if not price_overview:
                        continue
                    
                    # Check if game is on sale
                    discount_percent = price_overview.get("discount_percent", 0)
                    current_price = price_overview.get("final_formatted", "N/A")
                    original_price = price_overview.get("initial_formatted", current_price)
                    
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
                            current_price_num = float(price_overview.get("final", 0)) / 100
                            lowest_price_num = float(lowest_price)
                            if current_price_num <= lowest_price_num * 1.2:  # Within 20% of historical low
                                is_good_deal = True
                                deal_reason = f"💎 **Near Historical Low** ({discount_percent}% off)"
                        except (ValueError, TypeError):
                            pass
                    
                    if is_good_deal:
                        user_names = [current_family_members.get(uid, f"Unknown") for uid in interested_users]
                        deal_info = {
                            'name': game_name,
                            'app_id': app_id,
                            'current_price': current_price,
                            'original_price': original_price,
                            'discount_percent': discount_percent,
                            'lowest_price': lowest_price,
                            'deal_reason': deal_reason,
                            'interested_users': user_names
                        }
                        deals_found.append(deal_info)
                
                except Exception as e:
                    logger.warning(f"Force deals: Error checking deals for game {app_id}: {e}")
                    continue
            
            # Format and send results to wishlist channel
            if deals_found:
                message_parts = [f"🎯 **Current Deals Alert** (found {len(deals_found)} deals from {games_checked} games checked):\n\n"]
                
                for deal in deals_found:  # Show all deals found
                    message_parts.append(f"**{deal['name']}**\n")
                    message_parts.append(f"{deal['deal_reason']}\n")
                    message_parts.append(f"💰 {deal['current_price']}")
                    if deal['discount_percent'] > 0:
                        message_parts.append(f" ~~{deal['original_price']}~~")
                    if deal['lowest_price'] != "N/A":
                        message_parts.append(f" | Lowest ever: ${deal['lowest_price']}")
                    message_parts.append(f"\n👥 Wanted by: {', '.join(deal['interested_users'][:3])}")
                    if len(deal['interested_users']) > 3:
                        message_parts.append(f" +{len(deal['interested_users']) - 3} more")
                    message_parts.append(f"\n🔗 https://store.steampowered.com/app/{deal['app_id']}\n\n")
                
                final_message = "".join(message_parts)
                
                # Send to wishlist channel
                try:
                    await self.bot.send_to_channel(WISHLIST_CHANNEL_ID, final_message)  # type: ignore
                    await ctx.send(f"✅ **Force deals complete!** Posted {len(deals_found)} deals to wishlist channel.")
                    logger.info(f"Force deals: Posted {len(deals_found)} deals to wishlist channel")
                    await self.bot.send_log_dm("Force Deals") # type: ignore
                except Exception as e:
                    logger.error(f"Force deals: Error posting to wishlist channel: {e}")
                    await ctx.send(f"❌ **Error posting deals to channel:** {e}")
                    await self._send_admin_dm(f"Force deals channel error: {e}")
            else:
                await ctx.send(f"📊 **Force deals complete!** No significant deals found among {games_checked} games checked.")
                logger.info(f"Force deals: No deals found among {games_checked} games")
            
        except Exception as e:
            logger.critical(f"Force deals: Critical error during force deals check: {e}", exc_info=True)
            await ctx.send(f"❌ **Critical error during force deals:** {e}")
            await self._send_admin_dm(f"Force deals critical error: {e}")

    @prefixed_command(name="purge_cache")
    async def purge_cache_command(self, ctx: PrefixedContext):
        """
        Admin command to purge game details cache and force fresh data with USD pricing.
        """
        if str(ctx.author_id) != str(ADMIN_DISCORD_ID) or ctx.guild is not None:
            await ctx.send("You do not have permission to use this command, or it must be used in DMs.")
            return

        await ctx.send("🗑️ **Purging game details cache...**\nThis will clear all cached game data to force fresh USD pricing and new boolean fields on next fetch.")
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get count before deletion
            cursor.execute("SELECT COUNT(*) FROM game_details_cache")
            cache_count = cursor.fetchone()[0]
            
            # Clear the game details cache
            cursor.execute("DELETE FROM game_details_cache")
            conn.commit()
            conn.close()
            
            await ctx.send(f"✅ **Cache purge complete!**\nDeleted {cache_count} cached game entries.\n\n🔄 **Next steps:**\n- Run `!full_wishlist_scan` to rebuild cache with USD pricing\n- Run `!coop 2` to cache multiplayer games\n- All future API calls will use USD pricing and new boolean fields")
            logger.info(f"Admin purged game details cache: {cache_count} entries deleted")
            await self.bot.send_log_dm("Cache Purge") # type: ignore
            
        except Exception as e:
            logger.error(f"Error purging cache: {e}", exc_info=True)
            await ctx.send(f"❌ **Error purging cache:** {e}")
            await self._send_admin_dm(f"Cache purge error: {e}")

    @prefixed_command(name="full_library_scan")
    async def full_library_scan_command(self, ctx: PrefixedContext):
        """
        Admin command to scan all family members' complete game libraries.
        Uses rate limiting to avoid API limits and caches all owned games.
        """
        if str(ctx.author_id) != str(ADMIN_DISCORD_ID) or ctx.guild is not None:
            await ctx.send("You do not have permission to use this command, or it must be used in DMs.")
            return

        if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
            await ctx.send("❌ Steam API key is not configured. Cannot perform full library scan.")
            return

        start_time = datetime.now()
        await ctx.send("🔄 **Starting full library scan...**\nThis will scan all family members' complete game libraries with rate limiting to avoid API limits.\n⏱️ This may take several minutes depending on library sizes.")
        
        try:
            current_family_members = await self._load_family_members_from_db()
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
                user_name_for_log = current_family_members.get(user_steam_id, f"Unknown ({user_steam_id})")
                processed_members += 1
                
                try:
                    # Get user's owned games
                    await self._rate_limit_steam_api()
                    owned_games_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAMWORKS_API_KEY}&steamid={user_steam_id}&include_appinfo=1&include_played_free_games=1"
                    logger.info(f"Full library scan: Fetching owned games for {user_name_for_log}")
                    
                    owned_games_response = requests.get(owned_games_url, timeout=15)
                    owned_games_json = await self._handle_api_response(f"GetOwnedGames ({user_name_for_log})", owned_games_response)
                    
                    if not owned_games_json:
                        error_count += 1
                        continue

                    games = owned_games_json.get("response", {}).get("games", [])
                    if not games:
                        logger.info(f"Full library scan: No games found for {user_name_for_log} (private profile?)")
                        continue

                    user_games_cached = 0
                    user_games_skipped = 0
                    await ctx.send(f"⏳ **Processing {user_name_for_log}**: {len(games)} games found...")

                    # Calculate 10% intervals for progress updates
                    total_user_games = len(games)
                    progress_interval = max(1, total_user_games // 10)  # Update every 10%
                    
                    # Process each game with rate limiting and progress updates
                    for i, game in enumerate(games):
                        app_id = str(game.get("appid"))
                        if not app_id:
                            continue

                        total_games_processed += 1

                        # Check if we already have cached details
                        cached_game = get_cached_game_details(app_id)
                        if cached_game:
                            logger.debug(f"Full library scan: Using cached details for AppID: {app_id}")
                            user_games_skipped += 1
                            continue

                        # Fetch game details from Steam Store API
                        try:
                            await self._rate_limit_steam_store_api()
                            game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                            logger.debug(f"Full library scan: Fetching details for AppID: {app_id}")
                            
                            game_info_response = requests.get(game_url, timeout=10)
                            game_info_json = await self._handle_api_response("AppDetails (Library Scan)", game_info_response)
                            
                            if not game_info_json:
                                continue

                            game_data = game_info_json.get(str(app_id), {}).get("data")
                            if not game_data:
                                logger.debug(f"Full library scan: No data for AppID {app_id}")
                                continue

                            # Cache the game details permanently
                            cache_game_details(app_id, game_data, permanent=True)
                            user_games_cached += 1
                            total_games_cached += 1

                        except Exception as e:
                            logger.warning(f"Full library scan: Error processing game {app_id} for {user_name_for_log}: {e}")
                            continue

                    await ctx.send(f"✅ **{user_name_for_log} complete**: {user_games_cached} new games cached ({processed_members}/{total_members})")

                except Exception as e:
                    error_count += 1
                    logger.error(f"Full library scan: Error processing {user_name_for_log}: {e}", exc_info=True)
                    await ctx.send(f"❌ **Error processing {user_name_for_log}**: {e}")

            # Final summary
            end_time = datetime.now()
            scan_duration = end_time - start_time
            
            summary_msg = f"✅ **Full library scan complete!**\n"
            summary_msg += f"⏱️ **Duration:** {scan_duration.total_seconds():.1f} seconds\n"
            summary_msg += f"👥 **Members processed:** {processed_members}/{total_members}\n"
            summary_msg += f"🎮 **Games processed:** {total_games_processed}\n"
            summary_msg += f"💾 **New games cached:** {total_games_cached}\n"
            if error_count > 0:
                summary_msg += f"❌ **Errors:** {error_count}\n"
            summary_msg += f"🚀 **All future commands will benefit from cached game data!**"
            
            await ctx.send(summary_msg)
            logger.info(f"Full library scan completed: {processed_members} members, {total_games_cached} games cached, {scan_duration.total_seconds():.1f}s duration")
            await self.bot.send_log_dm("Full Library Scan") # type: ignore

        except Exception as e:
            logger.critical(f"Full library scan: Critical error during scan: {e}", exc_info=True)
            await ctx.send(f"❌ **Critical error during full library scan:** {e}")
            await self._send_admin_dm(f"Full library scan critical error: {e}")

    @prefixed_command(name="full_wishlist_scan")
    async def full_wishlist_scan_command(self, ctx: PrefixedContext):
        """
        Admin command to perform a comprehensive wishlist scan of ALL common games.
        Uses slower rate limiting to avoid API limits and provides progress updates.
        """
        if str(ctx.author_id) != str(ADMIN_DISCORD_ID) or ctx.guild is not None:
            await ctx.send("You do not have permission to use this command, or it must be used in DMs.")
            return

        if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
            await ctx.send("❌ Steam API key is not configured. Cannot perform full wishlist scan.")
            return

        start_time = datetime.now()
        start_time_float = time.time()  # Add float timestamp for progress calculations
        await ctx.send("🔄 **Starting comprehensive wishlist scan...**\nThis will process ALL common wishlist games with slower rate limiting to avoid API limits.\n⏱️ This may take several minutes depending on the number of games.")
        
        try:
            # Step 1: Collect all wishlist data (same as regular refresh)
            logger.info("Full wishlist scan: Starting comprehensive scan...")
            global_wishlist = []
            current_family_members = await self._load_family_members_from_db()
            all_unique_steam_ids_to_check = set(current_family_members.keys())

            # Collect wishlists from all family members
            for user_steam_id in all_unique_steam_ids_to_check:
                user_name_for_log = current_family_members.get(user_steam_id, f"Unknown ({user_steam_id})")

                # Try to get cached wishlist first
                cached_wishlist = get_cached_wishlist(user_steam_id)
                if cached_wishlist is not None:
                    logger.info(f"Full scan: Using cached wishlist for {user_name_for_log} ({len(cached_wishlist)} items)")
                    for app_id in cached_wishlist:
                        idx = find_in_2d_list(app_id, global_wishlist)
                        if idx is not None:
                            global_wishlist[idx][1].append(user_steam_id)
                        else:
                            global_wishlist.append([app_id, [user_steam_id]])
                    continue

                # If not cached, fetch from API
                wishlist_url = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?key={STEAMWORKS_API_KEY}&steamid={user_steam_id}"
                logger.info(f"Full scan: Fetching wishlist from API for {user_name_for_log}")

                try:
                    await self._rate_limit_steam_api()
                    wishlist_response = requests.get(wishlist_url, timeout=15)
                    if wishlist_response.text == "{\"success\":2}":
                        logger.info(f"Full scan: {user_name_for_log}'s wishlist is private or empty.")
                        continue

                    wishlist_json = await self._handle_api_response(f"GetWishlist ({user_name_for_log})", wishlist_response)
                    if not wishlist_json: continue

                    wishlist_items = wishlist_json.get("response", {}).get("items", [])
                    if not wishlist_items:
                        logger.info(f"Full scan: No items found in {user_name_for_log}'s wishlist.")
                        continue

                    # Extract app IDs for caching
                    user_wishlist_appids = []
                    for game_item in wishlist_items:
                        app_id = str(game_item.get("appid"))
                        if not app_id:
                            logger.warning(f"Full scan: Skipping wishlist item due to missing appid: {game_item}")
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
                    logger.critical(f"Full scan: Error fetching/processing {user_name_for_log}'s wishlist: {e}", exc_info=True)
                    await self._send_admin_dm(f"Full scan error for {user_name_for_log}: {e}")

            # Step 2: Collect ALL duplicate games (no limit)
            all_duplicate_games = []
            for item in global_wishlist:
                app_id = item[0]
                owner_steam_ids = item[1]
                if len(owner_steam_ids) > 1:
                    all_duplicate_games.append(item)

            if not all_duplicate_games:
                await ctx.send("✅ **Full scan complete!** No common wishlist games found.")
                return

            # Sort by AppID (descending) for consistent processing order
            sorted_all_duplicate_games = sorted(all_duplicate_games, key=lambda x: x[0], reverse=True)
            
            total_games = len(sorted_all_duplicate_games)
            await ctx.send(f"📊 **Found {total_games} common wishlist games to process.**\n🐌 Using {self.FULL_SCAN_RATE_LIMIT}s delays between API calls to avoid rate limits...")

            # Step 3: Process ALL games with slower rate limiting
            duplicate_games_for_display = []
            saved_game_appids = {item[0] for item in get_saved_games()}
            processed_count = 0
            skipped_count = 0
            error_count = 0

            # Initialize progress tracker with more frequent updates for better user feedback
            total_games = len(sorted_all_duplicate_games)
            progress_tracker = ProgressTracker(total_games, progress_interval=5)  # Report every 5% instead of 10%

            for item in sorted_all_duplicate_games:
                app_id = item[0]
                processed_count += 1
                
                # Report progress using ProgressTracker
                if progress_tracker.should_report_progress(processed_count):
                    context_info = f"games | ✅ {len(duplicate_games_for_display)} qualified | ⏭️ {skipped_count} skipped"
                    if error_count > 0:
                        context_info += f" | ❌ {error_count} errors"
                    progress_msg = progress_tracker.get_progress_message(processed_count, context_info)
                    await ctx.send(progress_msg)
                
                try:
                    # Check if we have cached game details first
                    cached_game = get_cached_game_details(app_id)
                    if cached_game:
                        logger.info(f"Full scan: Using cached game details for AppID: {app_id}")
                        game_data = cached_game
                    else:
                        # Use slower rate limiting for full scan
                        await self._rate_limit_full_scan()
                        
                        game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                        logger.info(f"Full scan: Fetching app details for AppID: {app_id} ({processed_count}/{total_games})")
                        
                        game_info_response = requests.get(game_url, timeout=10)
                        game_info_json = await self._handle_api_response("AppDetails (Full Scan)", game_info_response)
                        if not game_info_json:
                            error_count += 1
                            continue

                        game_data = game_info_json.get(str(app_id), {}).get("data")
                        if not game_data:
                            logger.warning(f"Full scan: No game data found for AppID {app_id}")
                            error_count += 1
                            continue
                        
                        # Cache the game details permanently
                        cache_game_details(app_id, game_data, permanent=True)

                    # Use cached boolean fields for faster performance
                    is_family_shared = game_data.get("is_family_shared", False)

                    if (game_data.get("type") == "game"
                        and game_data.get("is_free") == False
                        and is_family_shared
                        and "recommendations" in game_data
                        and app_id not in saved_game_appids
                        ):
                        duplicate_games_for_display.append(item)
                        logger.info(f"Full scan: Added {game_data.get('name', 'Unknown')} to display list")
                    else:
                        skipped_count += 1
                        logger.debug(f"Full scan: Skipped {app_id}: filtering criteria not met")


                except Exception as e:
                    error_count += 1
                    logger.critical(f"Full scan: Error processing game {app_id}: {e}", exc_info=True)

            # Step 4: Update the wishlist channel with results
            end_time = datetime.now()
            scan_duration = end_time - start_time
            
            try:
                wishlist_channel = await self.bot.fetch_channel(WISHLIST_CHANNEL_ID)
                if not wishlist_channel or not isinstance(wishlist_channel, GuildText):
                    await ctx.send("❌ Could not access wishlist channel to update results.")
                    return

                # Generate the message using the same format_message function
                wishlist_new_message = format_message(duplicate_games_for_display, short=False)

                # Update the pinned message
                pinned_messages = await wishlist_channel.fetch_pinned_messages()
                if not pinned_messages:
                    message_obj = await wishlist_channel.send(wishlist_new_message)
                    await message_obj.pin()
                    logger.info(f"Full scan: New wishlist message pinned in channel {WISHLIST_CHANNEL_ID}")
                else:
                    await pinned_messages[-1].edit(content=wishlist_new_message)
                    logger.info(f"Full scan: Wishlist message updated in channel {WISHLIST_CHANNEL_ID}")

                # Send completion summary
                summary_msg = f"✅ **Full wishlist scan complete!**\n"
                summary_msg += f"⏱️ **Duration:** {scan_duration.total_seconds():.1f} seconds\n"
                summary_msg += f"📊 **Processed:** {processed_count} games\n"
                summary_msg += f"✅ **Qualified games:** {len(duplicate_games_for_display)}\n"
                summary_msg += f"⏭️ **Skipped:** {skipped_count}\n"
                if error_count > 0:
                    summary_msg += f"❌ **Errors:** {error_count}\n"
                summary_msg += f"📝 **Wishlist channel updated with all results.**"
                
                await ctx.send(summary_msg)
                logger.info(f"Full wishlist scan completed: {processed_count} processed, {len(duplicate_games_for_display)} qualified, {scan_duration.total_seconds():.1f}s duration")

            except Exception as e:
                logger.error(f"Full scan: Error updating wishlist channel: {e}", exc_info=True)
                await ctx.send(f"⚠️ **Scan completed but failed to update wishlist channel:** {e}")
                await self._send_admin_dm(f"Full scan channel update error: {e}")

        except Exception as e:
            logger.critical(f"Full scan: Critical error during comprehensive wishlist scan: {e}", exc_info=True)
            await ctx.send(f"❌ **Critical error during full scan:** {e}")
            await self._send_admin_dm(f"Full scan critical error: {e}")

    """
    [help]|deals|check current deals for family wishlist games|!deals|Shows games from family wishlists that are currently on sale or at historical low prices. ***This command can be used in bot DM***
    """
    @prefixed_command(name="deals")
    async def check_deals_command(self, ctx: PrefixedContext):
        loading_message = await ctx.send("🔍 Checking for current deals on family wishlist games...")
        
        try:
            current_family_members = await self._load_family_members_from_db()
            all_unique_steam_ids_to_check = set(current_family_members.keys())
            
            # Collect all wishlist games from family members
            global_wishlist = []
            for user_steam_id in all_unique_steam_ids_to_check:
                user_name_for_log = current_family_members.get(user_steam_id, f"Unknown ({user_steam_id})")
                
                # Try to get cached wishlist first
                cached_wishlist = get_cached_wishlist(user_steam_id)
                if cached_wishlist is not None:
                    logger.info(f"Using cached wishlist for deals check: {user_name_for_log} ({len(cached_wishlist)} items)")
                    for app_id in cached_wishlist:
                        if app_id not in [item[0] for item in global_wishlist]:
                            global_wishlist.append([app_id, [user_steam_id]])
                        else:
                            # Add user to existing entry
                            for item in global_wishlist:
                                if item[0] == app_id:
                                    item[1].append(user_steam_id)
                                    break
            
            if not global_wishlist:
                await loading_message.edit(content="No wishlist games found to check for deals.")
                return
            
            deals_found = []
            games_checked = 0
            max_games_to_check = 15  # Limit to avoid rate limits
            
            for item in global_wishlist[:max_games_to_check]:
                app_id = item[0]
                interested_users = item[1]
                games_checked += 1
                
                try:
                    # Get cached game details first
                    cached_game = get_cached_game_details(app_id)
                    if cached_game:
                        game_data = cached_game
                    else:
                        # If not cached, fetch from API
                        await self._rate_limit_steam_store_api()
                        game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                        app_info_response = requests.get(game_url, timeout=10)
                        game_info_json = await self._handle_api_response("AppDetails (Deals)", app_info_response)
                        if not game_info_json: continue
                        
                        game_data = game_info_json.get(str(app_id), {}).get("data")
                        if not game_data: continue
                        
                        # Cache the game details
                        cache_game_details(app_id, game_data, permanent=True)
                    
                    game_name = game_data.get("name", f"Unknown Game ({app_id})")
                    price_overview = game_data.get("price_overview")
                    
                    if not price_overview:
                        continue
                    
                    # Check if game is on sale
                    discount_percent = price_overview.get("discount_percent", 0)
                    current_price = price_overview.get("final_formatted", "N/A")
                    original_price = price_overview.get("initial_formatted", current_price)
                    
                    # Get historical low price
                    lowest_price = get_lowest_price(int(app_id))
                    
                    # Determine if this is a good deal
                    is_good_deal = False
                    deal_reason = ""
                    
                    if discount_percent >= 50:  # 50% or more discount
                        is_good_deal = True
                        deal_reason = f"🔥 **{discount_percent}% OFF**"
                    elif discount_percent >= 25 and lowest_price != "N/A":
                        # Check if current price is close to historical low
                        try:
                            current_price_num = float(price_overview.get("final", 0)) / 100
                            lowest_price_num = float(lowest_price)
                            if current_price_num <= lowest_price_num * 1.1:  # Within 10% of historical low
                                is_good_deal = True
                                deal_reason = f"💎 **Near Historical Low** ({discount_percent}% off)"
                        except (ValueError, TypeError):
                            pass
                    
                    if is_good_deal:
                        user_names = [current_family_members.get(uid, f"Unknown") for uid in interested_users]
                        deal_info = {
                            'name': game_name,
                            'app_id': app_id,
                            'current_price': current_price,
                            'original_price': original_price,
                            'discount_percent': discount_percent,
                            'lowest_price': lowest_price,
                            'deal_reason': deal_reason,
                            'interested_users': user_names
                        }
                        deals_found.append(deal_info)
                
                except Exception as e:
                    logger.warning(f"Error checking deals for game {app_id}: {e}")
                    continue
            
            # Format and send results
            if deals_found:
                header = f"🎯 **Found {len(deals_found)} good deals** (checked {games_checked} games):\n\n"
                
                # Build deal entries
                deal_entries = []
                for deal in deals_found:
                    deal_entry = f"**{deal['name']}**\n"
                    deal_entry += f"{deal['deal_reason']}\n"
                    deal_entry += f"💰 {deal['current_price']}"
                    if deal['discount_percent'] > 0:
                        deal_entry += f" ~~{deal['original_price']}~~"
                    if deal['lowest_price'] != "N/A":
                        deal_entry += f" | Lowest ever: ${deal['lowest_price']}"
                    deal_entry += f"\n👥 Wanted by: {', '.join(deal['interested_users'][:3])}"
                    if len(deal['interested_users']) > 3:
                        deal_entry += f" +{len(deal['interested_users']) - 3} more"
                    deal_entry += f"\n🔗 https://store.steampowered.com/app/{deal['app_id']}\n"
                    deal_entries.append(deal_entry)
                
                # Use utility function to handle message truncation
                footer_template = "\n... and {count} more deals!"
                final_message = truncate_message_list(deal_entries, header, footer_template)
            else:
                final_message = f"No significant deals found among {games_checked} wishlist games checked. Try again later!"
            
            await loading_message.edit(content=final_message)
            
        except Exception as e:
            logger.critical(f"An unexpected error occurred in check_deals_command: {e}", exc_info=True)
            await loading_message.edit(content="An error occurred while checking for deals. Please try again later.")
            await self._send_admin_dm(f"Critical error in deals command: {e}")

    @Task.create(IntervalTrigger(hours=1))
    async def send_new_game(self) -> None:
        logger.info("Running send_new_game task...")

        games_json = None
        try:
            # Try to get cached family library first
            cached_family_library = get_cached_family_library()
            if cached_family_library is not None:
                logger.info(f"Using cached family library for new game check ({len(cached_family_library)} games)")
                game_list = cached_family_library
            else:
                # If not cached, fetch from API
                await self._rate_limit_steam_api() # Apply rate limit before API call
                url_family_list = get_family_game_list_url()
                answer = requests.get(url_family_list, timeout=15)
                games_json = await self._handle_api_response("GetFamilySharedApps", answer)
                if not games_json: return

                game_list = games_json.get("response", {}).get("apps", [])
                if not game_list:
                    logger.warning("No apps found in family game list response for new game check.")
                    return
                
                # Cache the family library for 30 minutes
                cache_family_library(game_list, cache_minutes=30)

            current_family_members = await self._load_family_members_from_db()
            
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
            current_utc_iso = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'

            for appid in game_array:
                if appid in new_appids:
                    all_games_for_db_update.append((appid, current_utc_iso))
                else:
                    found_timestamp = next((ts for ap, ts in saved_games_with_timestamps if ap == appid), None)
                    if found_timestamp:
                        all_games_for_db_update.append((appid, found_timestamp))
                    else:
                        all_games_for_db_update.append((appid, current_utc_iso))


            new_games_to_notify_raw = [(appid, current_utc_iso) for appid in new_appids]
            new_games_to_notify_raw.sort(key=lambda x: x[1], reverse=True)

            if len(new_games_to_notify_raw) > 10:
                logger.warning(f"Detected {len(new_games_to_notify_raw)} new games. Processing only the latest 10 (by AppID) to avoid rate limits.")
                await self.bot.send_to_channel(NEW_GAME_CHANNEL_ID, f"Detected {len(new_games_to_notify_raw)} new games in the Family Library. Processing only the latest 10 (most recently added) to avoid API rate limits. More may be announced in subsequent checks.")  # type: ignore
                new_games_to_process = new_games_to_notify_raw[:10]
            else:
                new_games_to_process = new_games_to_notify_raw

            if new_games_to_process:
                logger.info(f"Processing {len(new_games_to_process)} new games for notification.")
                for new_appid_tuple in new_games_to_process:
                    new_appid = new_appid_tuple[0]

                    # Try to get cached game details first
                    cached_game = get_cached_game_details(new_appid)
                    if cached_game:
                        logger.info(f"Using cached game details for new game AppID: {new_appid}")
                        game_data = cached_game
                    else:
                        # If not cached, fetch from API
                        await self._rate_limit_steam_store_api() # Apply store API rate limit
                        game_url = f"https://store.steampowered.com/api/appdetails?appids={new_appid}&cc=us&l=en"
                        logger.info(f"Fetching app details from API for new game AppID: {new_appid}")
                        app_info_response = requests.get(game_url, timeout=10)
                        game_info_json = await self._handle_api_response("AppDetails (New Game)", app_info_response)
                        if not game_info_json: continue

                        game_data = game_info_json.get(str(new_appid), {}).get("data")
                        if not game_data:
                            logger.warning(f"No game data found for new game AppID {new_appid} in app details response.")
                            continue
                        
                        # Cache the game details permanently (game details rarely change)
                        cache_game_details(new_appid, game_data, permanent=True)

                    is_family_shared_game = any(cat.get("id") == 62 for cat in game_data.get("categories", []))

                    if game_data.get("type") == "game" and game_data.get("is_free") == False and is_family_shared_game:
                        owner_steam_id = game_owner_list.get(str(new_appid))
                        owner_name = current_family_members.get(owner_steam_id, f"Unknown Owner ({owner_steam_id})")
                        
                        # Build the base message
                        game_name = game_data.get("name", f"Unknown Game")
                        message = f"Thank you to {owner_name} for **{game_name}**\nhttps://store.steampowered.com/app/{new_appid}"
                        
                        # Add pricing information if available
                        try:
                            current_price = game_data.get('price_overview', {}).get('final_formatted', 'N/A')
                            lowest_price = get_lowest_price(int(new_appid))
                            
                            if current_price != 'N/A' or lowest_price != 'N/A':
                                price_info = []
                                if current_price != 'N/A':
                                    price_info.append(f"Current: {current_price}")
                                if lowest_price != 'N/A':
                                    price_info.append(f"Lowest ever: ${lowest_price}")
                                
                                if price_info:
                                    message += f"\n💰 {'|'.join(price_info)}"
                        except Exception as e:
                            logger.warning(f"Could not get pricing info for new game {new_appid}: {e}")
                        
                        await self.bot.send_to_channel(NEW_GAME_CHANNEL_ID, message)  # type: ignore
                    else:
                        logger.debug(f"Skipping new game {new_appid}: not a paid game, not family shared, or not type 'game'.")

                set_saved_games(all_games_for_db_update)
            else:
                logger.info('No new games detected.')

        except ValueError as e:
            logger.error(f"Error in send_new_game: {e}")
            await self._send_admin_dm(f"Error in send_new_game: {e}")
        except Exception as e:
            logger.critical(f"An unexpected error occurred in send_new_game task main block: {e}", exc_info=True)
            await self._send_admin_dm(f"Critical error send_new_game task: {e}")

    @Task.create(IntervalTrigger(hours=24))
    async def refresh_wishlist(self) -> None:
        logger.info("Running refresh_wishlist task...")
        if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
            logger.error("STEAMWORKS_API_KEY is not configured for wishlist task.")
            await self._send_admin_dm("Steam API key is not configured for wishlist task.")
            return

        global_wishlist = []

        current_family_members = await self._load_family_members_from_db()
        
        all_unique_steam_ids_to_check = set(current_family_members.keys())

        for user_steam_id in all_unique_steam_ids_to_check:
            user_name_for_log = current_family_members.get(user_steam_id, f"Unknown ({user_steam_id})")

            # Try to get cached wishlist first
            cached_wishlist = get_cached_wishlist(user_steam_id)
            if cached_wishlist is not None:
                logger.info(f"Using cached wishlist for {user_name_for_log} ({len(cached_wishlist)} items)")
                for app_id in cached_wishlist:
                    idx = find_in_2d_list(app_id, global_wishlist)
                    if idx is not None:
                        global_wishlist[idx][1].append(user_steam_id)
                    else:
                        global_wishlist.append([app_id, [user_steam_id]])
                continue

            # If not cached, fetch from API
            wishlist_url = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?key={STEAMWORKS_API_KEY}&steamid={user_steam_id}"
            logger.info(f"Fetching wishlist from API for {user_name_for_log} (Steam ID: {user_steam_id})")

            wishlist_json = None
            try:
                await self._rate_limit_steam_api() # Apply rate limit here
                wishlist_response = requests.get(wishlist_url, timeout=15)
                if wishlist_response.text == "{\"success\":2}":
                    logger.info(f"{user_name_for_log}'s wishlist is private or empty.")
                    continue

                wishlist_json = await self._handle_api_response(f"GetWishlist ({user_name_for_log})", wishlist_response)
                if not wishlist_json: continue

                wishlist_items = wishlist_json.get("response", {}).get("items", [])

                if not wishlist_items:
                    logger.info(f"No items found in {user_name_for_log}'s wishlist.")
                    continue

                # Extract app IDs for caching
                user_wishlist_appids = []
                for game_item in wishlist_items:
                    app_id = str(game_item.get("appid"))
                    if not app_id:
                        logger.warning(f"Skipping wishlist item due to missing appid: {game_item}")
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
                logger.critical(f"An unexpected error occurred fetching/processing {user_name_for_log}'s wishlist: {e}", exc_info=True)
                await self._send_admin_dm(f"Critical error wishlist {user_name_for_log}: {e}")

        # First, collect all duplicate games without fetching details
        potential_duplicate_games = []
        for item in global_wishlist:
            app_id = item[0]
            owner_steam_ids = item[1]
            if len(owner_steam_ids) > 1:
                potential_duplicate_games.append(item)

        # Sort and slice the potential duplicate games for processing
        sorted_duplicate_games = sorted(potential_duplicate_games, key=lambda x: x[0], reverse=True)
        
        if len(sorted_duplicate_games) > self.MAX_WISHLIST_GAMES_TO_PROCESS:
            logger.warning(f"Detected {len(sorted_duplicate_games)} common wishlist games. Processing only the latest {self.MAX_WISHLIST_GAMES_TO_PROCESS} to avoid rate limits.")
            await self.bot.send_to_channel(WISHLIST_CHANNEL_ID, f"Detected {len(sorted_duplicate_games)} common wishlist games. Processing only the latest {self.MAX_WISHLIST_GAMES_TO_PROCESS} (by AppID) for this update to avoid API rate limits. More may be announced in subsequent checks.")  # type: ignore
            games_to_process = sorted_duplicate_games[:self.MAX_WISHLIST_GAMES_TO_PROCESS]
        else:
            games_to_process = sorted_duplicate_games

        # Now process the selected games and fetch their details
        duplicate_games_for_display = []
        saved_game_appids = {item[0] for item in get_saved_games()}  # Get saved game app IDs for comparison

        for item in games_to_process:
            app_id = item[0]
            
            game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
            logger.info(f"Fetching app details for wishlist AppID: {app_id}")

            game_info_json = None
            try:
                await self._rate_limit_steam_store_api() # Apply store API rate limit
                game_info_response = requests.get(game_url, timeout=10)
                game_info_json = await self._handle_api_response("AppDetails (Wishlist)", game_info_response)
                if not game_info_json: continue

                game_data = game_info_json.get(str(app_id), {}).get("data")
                if not game_data:
                    logger.warning(f"No game data found for wishlist AppID {app_id} in app details response.")
                    continue

                # Use cached boolean fields for faster performance
                is_family_shared = game_data.get("is_family_shared", False)

                if (game_data.get("type") == "game"
                    and game_data.get("is_free") == False
                    and is_family_shared
                    and "recommendations" in game_data
                    and app_id not in saved_game_appids
                    ):
                    duplicate_games_for_display.append(item)
                else:
                    logger.debug(f"Skipping wishlist game {app_id}: not a paid game, not family shared category, or no recommendations, or already owned.")

            except Exception as e:
                logger.critical(f"An unexpected error occurred processing duplicate wishlist game {app_id}: {e}", exc_info=True)


        wishlist_channel = None
        try:
            wishlist_channel = await self.bot.fetch_channel(WISHLIST_CHANNEL_ID)
            if not wishlist_channel:
                logger.error(f"Wishlist channel not found for ID: {WISHLIST_CHANNEL_ID}. Check config.yml.")
                await self._send_admin_dm(f"Wishlist channel not found for ID: {WISHLIST_CHANNEL_ID}.")
                return
        except Exception as e:
            logger.error(f"Could not fetch wishlist channel (ID: {WISHLIST_CHANNEL_ID}): {e}")
            await self._send_admin_dm(f"Error fetching wishlist channel: {e}")
            return

        if not isinstance(wishlist_channel, GuildText):
            logger.error(f"Wishlist channel {WISHLIST_CHANNEL_ID} is not a text channel (type: {type(wishlist_channel).__name__}).")
            await self._send_admin_dm(f"Wishlist channel {WISHLIST_CHANNEL_ID} is not a text channel.")
            return

        pinned_messages = []
        try:
            pinned_messages = await wishlist_channel.fetch_pinned_messages()
        except Exception as e:
            logger.error(f"Error fetching pinned messages from channel {WISHLIST_CHANNEL_ID}: {e}")
            await self._send_admin_dm(f"Error fetching pinned messages: {e}")

        # Pass the duplicate games to format_message
        wishlist_new_message = format_message(duplicate_games_for_display, short=False)

        try:
            if not pinned_messages:
                message_obj = await wishlist_channel.send(wishlist_new_message)
                await message_obj.pin()
                logger.info(f"New wishlist message pinned in channel {WISHLIST_CHANNEL_ID}")
            else:
                await pinned_messages[-1].edit(content=wishlist_new_message)
                logger.info(f"Wishlist message updated in channel {WISHLIST_CHANNEL_ID}")
        except Exception as e:
            logger.error(f"Error sending/editing/pinning wishlist message in channel {WISHLIST_CHANNEL_ID}: {e}", exc_info=True)
            await self._send_admin_dm(f"Error with wishlist message (send/edit/pin): {e}")


    @listen()
    async def on_startup(self):
        self.refresh_wishlist.start()
        self.send_new_game.start()
        logger.info("--Steam Family Tasks Started")

def setup(bot):  # Remove type annotation to avoid Extension constructor conflict
    steam_family(bot)
