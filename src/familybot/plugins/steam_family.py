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
from familybot.lib.database import get_db_connection, get_cached_game_details, cache_game_details
from familybot.lib.types import FamilyBotClient

# Setup logging for this specific module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Migration Flag for Family Members ---
_family_members_migrated_this_run = False


class steam_family(Extension):
    # --- RATE LIMITING CONSTANTS ---
    MAX_WISHLIST_GAMES_TO_PROCESS = 20 # Limit appdetails calls to 20 games per run
    STEAM_API_RATE_LIMIT = 1.0 # Minimum seconds between Steam API calls (e.g., GetOwnedGames, GetFamilySharedApps)
    STEAM_STORE_API_RATE_LIMIT = 1.5 # Minimum seconds between Steam Store API calls (e.g., appdetails)
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
    [help]|!coop| it returns all the family shared multiplayer games in the shared library with a given numbers of copies| !coop NUMBER_OF_COPIES | ***This command can be used in bot DM***
    """
    @prefixed_command(name="coop")
    async def coop_command(self, ctx: PrefixedContext, number_str: str):
        try:
            number = int(number_str)
        except ValueError:
            await ctx.send("Please provide a valid number for copies.")
            return

        if number <= 1:
            await ctx.send("The number after the command must be greater than 1.")
            return

        loading_message = await ctx.send(f"Searching for games with {number} copies...")

        games_json = None
        try:
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
                    game_url = f"https://store.steampowered.com/api/appdetails?appids={game_appid}&cc=fr&l=fr"
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
                    is_family_shared_category = any(cat.get("id") == 62 for cat in game_data.get("categories", []))
                    if is_family_shared_category:
                        is_multiplayer = any(cat.get("id") in [1, 36, 38] for cat in game_data.get("categories", []))
                        if is_multiplayer:
                            coop_game_names.append(game_data.get("name", f"Unknown Game ({game_appid})"))
                    else:
                        logger.debug(f"Game {game_appid} is not categorized as family shared (ID 62).")

            if coop_game_names:
                await loading_message.edit(content='__Common shared multiplayer games__:\n' + '\n'.join(coop_game_names))
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

    @Task.create(IntervalTrigger(hours=1))
    async def send_new_game(self) -> None:
        logger.info("Running send_new_game task...")

        games_json = None
        try:
            await self._rate_limit_steam_api() # Apply rate limit before API call
            url_family_list = get_family_game_list_url()
            answer = requests.get(url_family_list, timeout=15)
            games_json = await self._handle_api_response("GetFamilySharedApps", answer)
            if not games_json: return

            game_list = games_json.get("response", {}).get("apps", [])
            if not game_list:
                logger.warning("No apps found in family game list response for new game check.")
                return

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
                        game_url = f"https://store.steampowered.com/api/appdetails?appids={new_appid}&cc=fr&l=fr"
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
                        await self.bot.send_to_channel(NEW_GAME_CHANNEL_ID, f"Thank you to {owner_name} for \n https://store.steampowered.com/app/{new_appid}")  # type: ignore
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

            wishlist_url = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?key={STEAMWORKS_API_KEY}&steamid={user_steam_id}"
            logger.info(f"Fetching wishlist for {user_name_for_log} (Steam ID: {user_steam_id})")

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

                for game_item in wishlist_items:
                    app_id = str(game_item.get("appid"))
                    if not app_id:
                        logger.warning(f"Skipping wishlist item due to missing appid: {game_item}")
                        continue

                    idx = find_in_2d_list(app_id, global_wishlist)
                    if idx is not None:
                        global_wishlist[idx][1].append(user_steam_id)
                    else:
                        global_wishlist.append([app_id, [user_steam_id]])

            except Exception as e:
                logger.critical(f"An unexpected error occurred fetching/processing {user_name_for_log}'s wishlist: {e}", exc_info=True)
                await self._send_admin_dm(f"Critical error wishlist {user_name_for_log}: {e}")

        duplicate_games_for_display = []
        for item in global_wishlist:
            app_id = item[0]
            owner_steam_ids = item[1]

            if len(owner_steam_ids) > 1:
                # --- NEW LOGIC: Sort and slice duplicate games for processing ---
                # This ensures we don't hit rate limits on store API calls for many common games.
                # Assuming AppID sorting is sufficient for "most relevant/latest" in this context.
                # Or consider sorting by number of owners in `item[1]` if that's more relevant.
                sorted_duplicate_games = sorted(duplicate_games_for_display, key=lambda x: x[0], reverse=True) # Sort by AppID
                
                if len(sorted_duplicate_games) > self.MAX_WISHLIST_GAMES_TO_PROCESS:
                    logger.warning(f"Detected {len(sorted_duplicate_games)} common wishlist games. Processing only the latest {self.MAX_WISHLIST_GAMES_TO_PROCESS} to avoid rate limits.")
                    await self.bot.send_to_channel(WISHLIST_CHANNEL_ID, f"Detected {len(sorted_duplicate_games)} common wishlist games. Processing only the latest {self.MAX_WISHLIST_GAMES_TO_PROCESS} (by AppID) for this update to avoid API rate limits. More may be announced in subsequent checks.")
                    games_to_process_for_details = sorted_duplicate_games[:self.MAX_WISHLIST_GAMES_TO_PROCESS] # Slice for processing
                else:
                    games_to_process_for_details = sorted_duplicate_games
                # --- END NEW LOGIC ---

                game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=fr&l=fr"
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

                    is_family_shared_category = any(cat.get("id") == 62 for cat in game_data.get("categories", []))

                    saved_game_appids = {item[0] for item in get_saved_games()} # Get saved game app IDs for comparison

                    if (game_data.get("type") == "game"
                        and game_data.get("is_free") == False
                        and is_family_shared_category
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
