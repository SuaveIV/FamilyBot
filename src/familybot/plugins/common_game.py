# In src/familybot/plugins/common_game.py

from interactions import Extension, listen, Task, IntervalTrigger
from interactions.ext.prefixed_commands import prefixed_command, PrefixedContext
import json
import requests
import os
import logging
import sqlite3 # Import sqlite3 for specific error handling

from familybot.config import ADMIN_DISCORD_ID, STEAMWORKS_API_KEY, PROJECT_ROOT
from familybot.lib.utils import get_common_elements_in_lists, truncate_message_list
from familybot.lib.database import (
    get_db_connection, get_cached_user_games, cache_user_games,
    get_cached_discord_user, cache_discord_user, cleanup_expired_cache,
    get_cached_game_details, cache_game_details
)
from familybot.lib.types import FamilyBotClient, FamilyBotClientProtocol, DISCORD_MESSAGE_LIMIT
from familybot.lib.logging_config import get_logger, log_private_profile_detection, log_api_error
from typing import cast

# Setup enhanced logging for this specific module
logger = get_logger(__name__)

# Define the path to OLD register.csv for migration (if it exists)
OLD_REGISTER_CSV_PATH = os.path.join(PROJECT_ROOT, 'register.csv')


def _migrate_users_to_db(conn: sqlite3.Connection):
    """Internal function to migrate existing register.csv data to the database."""
    if os.path.exists(OLD_REGISTER_CSV_PATH):
        logger.info(f"Attempting to migrate users from old file: {OLD_REGISTER_CSV_PATH}")
        try:
            with open(OLD_REGISTER_CSV_PATH, 'r') as f:
                users_to_insert = []
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(',')
                    if len(parts) == 2:
                        discord_id, steam_id = parts
                        users_to_insert.append((discord_id, steam_id))

                if users_to_insert:
                    cursor = conn.cursor()
                    cursor.executemany("INSERT OR IGNORE INTO users (discord_id, steam_id) VALUES (?, ?)", users_to_insert)
                    conn.commit()
                    logger.info(f"Migrated {len(users_to_insert)} users from {OLD_REGISTER_CSV_PATH} to database.")
                    # Optionally, remove the old file after successful migration
                    # os.remove(OLD_REGISTER_CSV_PATH)
                    # logger.info(f"Removed old register.csv file: {OLD_REGISTER_CSV_PATH}")
                else:
                    logger.info("No users found in old register.csv for migration.")
        except Exception as e:
            logger.error(f"Error during register.csv migration to DB: {e}", exc_info=True)
    else:
        logger.info("No old register.csv found for migration. Skipping.")


class common_games(Extension):
    def __init__(self, bot: FamilyBotClient):
        self.bot: FamilyBotClientProtocol = cast(FamilyBotClientProtocol, bot)  # Cast to protocol for type checking
        logger.info("common Games Plugin loaded")

    async def _send_admin_dm(self, message: str) -> None:
        """Helper to send error/warning messages to the bot admin via DM."""
        try:
            admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
            if admin_user:
                await admin_user.send(message)
        except Exception as e:
            logger.error(f"Failed to send DM to admin {ADMIN_DISCORD_ID}: {e}")

    async def _load_registered_users(self) -> dict:
        """Loads registered users from the database into a dictionary."""
        users = {}
        conn = None
        try:
            conn = get_db_connection()
            _migrate_users_to_db(conn) # Attempt migration if file exists on first read
            cursor = conn.cursor()
            cursor.execute("SELECT discord_id, steam_id FROM users")
            for row in cursor.fetchall():
                users[row["discord_id"]] = row["steam_id"]
            logger.debug(f"Loaded {len(users)} users from database.")
        except sqlite3.Error as e:
            logger.error(f"Error reading registered users from DB: {e}")
            await self._send_admin_dm(f"Error reading registered users from DB: {e}")
        finally:
            if conn:
                conn.close()
        return users

    """
    [help]|!register|make the link between a discord account and a steam one| !register YOUR_STEAM_ID | To get your Steam ID (SteamID64), go to https://steamdb.info/calculator/ and paste your Steam profile URL. ***This command can be used in bot DM***
    """
    @prefixed_command(name="register")
    async def register(self, ctx: PrefixedContext, steam_id: str):
        discord_id = str(ctx.author_id)
        registered_users = await self._load_registered_users() # Check existing from DB

        if len(steam_id) != 17 or not steam_id.isdigit():
            logger.warning(f"Invalid Steam ID provided by {discord_id}: {steam_id}")
            await ctx.send("You've made a mistake on your Steam ID. Please ensure it's a 17-digit number (e.g., from steamid.pro) or contact an admin.")
            return

        if discord_id in registered_users:
            await ctx.send("You are already registered with this Discord ID.")
            return
        if steam_id in registered_users.values():
            await ctx.send("This Steam ID is already registered to another Discord user.")
            return

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Insert into 'users' table
            cursor.execute("INSERT INTO users (discord_id, steam_id) VALUES (?, ?)", (discord_id, steam_id))
            
            # Also insert into 'family_members' table for Web UI display
            # Use ctx.author.display_name for friendly_name
            friendly_name = ctx.author.display_name
            cursor.execute(
                "INSERT OR IGNORE INTO family_members (steam_id, friendly_name, discord_id) VALUES (?, ?, ?)",
                (steam_id, friendly_name, discord_id)
            )
            
            conn.commit()
            await ctx.send(f"You have been successfully registered as '{friendly_name}'!")
            logger.info(f"Registered Discord ID {discord_id} with Steam ID {steam_id} in 'users' and 'family_members' DB tables.")
        except sqlite3.IntegrityError: # Specific error for UNIQUE constraint violation
            logger.warning(f"Attempted to register existing Discord ID {discord_id} or Steam ID {steam_id} (IntegrityError).")
            await ctx.send("An error occurred: This Discord ID or Steam ID might already be registered. Try `!list_users`.")
        except Exception as e:
            logger.error(f"Error writing to database for {discord_id}: {e}", exc_info=True)
            await ctx.send("An error occurred during registration. Please try again or contact an admin.")
            await self._send_admin_dm(f"Error registering user {discord_id} to DB: {e}")
        finally:
            if conn:
                conn.close()

    """
    [help]|!common_games|get the multiplayer games that the given person have in common and send the result in dm| !common_games @user1 @user2 ... | the users put in the command needs to be registered before. ***This command can be used in bot DM***
    """
    @prefixed_command(name="common_games")
    async def get_common_games(self, ctx: PrefixedContext, *args):
        target_discord_ids = [str(ctx.author_id)]
        for arg in args:
            if arg.startswith("<@") and arg.endswith(">"):
                clean_id = arg.strip("<@!>")
                if clean_id.isdigit() and clean_id not in target_discord_ids:
                    target_discord_ids.append(clean_id)
            else:
                await ctx.send("Please mention users using `@user` format. Example: `!common_games @user1 @user2`")
                return

        registered_users = await self._load_registered_users()
        steam_ids_to_check = []
        missing_discord_ids = []

        for discord_id in target_discord_ids:
            if discord_id in registered_users:
                steam_ids_to_check.append(registered_users[discord_id])
            else:
                missing_discord_ids.append(discord_id)

        if missing_discord_ids:
            mentions = [f"<@{uid}>" for uid in missing_discord_ids]
            await self.bot.send_dm(ctx.author_id, f"Not all users listed are registered. Please register them or use `!list_users` to see registered users. Missing: {', '.join(mentions)}")
            return

        if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
            logger.error("STEAMWORKS_API_KEY is missing or is a placeholder. Cannot fetch Steam games.")
            await self.bot.send_dm(ctx.author_id, "Steam API key is not configured. Please contact an admin.")
            return

        game_lists = []
        for steam_id in steam_ids_to_check:
            # Try to get cached games first
            cached_games = get_cached_user_games(steam_id)
            if cached_games is not None:
                logger.info(f"Using cached games for Steam ID: {steam_id} ({len(cached_games)} games)")
                game_lists.append([int(appid) for appid in cached_games])
                continue

            # If not cached, fetch from API
            temp_game_list = []
            steam_get_games_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAMWORKS_API_KEY}&steamid={steam_id}&format=json&include_appinfo=1"
            logger.info(f"Fetching games from API for Steam ID: {steam_id}")
            try:
                answer = requests.get(steam_get_games_url, timeout=10)
                answer.raise_for_status()

                logger.debug(f"Status Code: {answer.status_code}")
                logger.debug(f"Raw Response Text (GetOwnedGames):\n{answer.text[:500]}")

                response_data = json.loads(answer.text)
                user_game_list_json = response_data.get("response", {}).get("games", [])

                if not user_game_list_json:
                    logger.warning(f"No games found or 'games' key missing for Steam ID {steam_id}. Full response: {response_data}")
                    continue

                for game in user_game_list_json:
                    temp_game_list.append(game["appid"])
                
                # Cache the results for 6 hours
                cache_user_games(steam_id, temp_game_list, cache_hours=6)
                game_lists.append(temp_game_list)

            except requests.exceptions.RequestException as e:
                logger.error(f"Request error fetching games for Steam ID {steam_id}: {e}")
                await self.bot.send_dm(ctx.author_id, f"Error fetching games for Steam ID {steam_id}. Steam API issue. Check logs.")
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error for Steam ID {steam_id}. Response: {answer.text[:200]}")
                await self.bot.send_dm(ctx.author_id, f"Error processing Steam API response for Steam ID {steam_id}. Check logs.")
            except KeyError as e:
                logger.error(f"Missing key in Steam API response for Steam ID {steam_id}: {e}. Response: {response_data}")
                await self.bot.send_dm(ctx.author_id, f"Unexpected response format from Steam API for Steam ID {steam_id}. Check logs.")
            except Exception as e:
                logger.critical(f"An unexpected error occurred during game fetching for Steam ID {steam_id}: {e}", exc_info=True)
                await self._send_admin_dm(f"Critical error fetching games for {steam_id}: {e}")

        if not game_lists or len(game_lists) < len(steam_ids_to_check):
            if len(steam_ids_to_check) > 1:
                await self.bot.send_dm(ctx.author_id, "Could not retrieve game lists for all specified users. Some users might have private profiles or an API error occurred. Cannot find common games.")
            else:
                await self.bot.send_dm(ctx.author_id, "Could not retrieve your game list. Your profile might be private or an API error occurred.")
            return

        common_game_appids = get_common_elements_in_lists(game_lists)
        if not common_game_appids:
            await self.bot.send_dm(ctx.author_id, "No common games found among the specified users.")
            return

        header = "Common Multiplayer Games:\n"
        game_entries = []
        
        for game_appid in common_game_appids:
            try:
                # Try to get cached game details first
                cached_game = get_cached_game_details(str(game_appid))
                if cached_game:
                    logger.info(f"Using cached game details for AppID: {game_appid}")
                    game_data = cached_game
                else:
                    # If not cached, fetch from API
                    game_url = f"https://store.steampowered.com/api/appdetails?appids={game_appid}&cc=us&l=en"
                    logger.info(f"Fetching app details from API for AppID: {game_appid}")
                    
                    app_info_response = requests.get(game_url, timeout=10)
                    app_info_response.raise_for_status()

                    logger.debug(f"Status Code: {app_info_response.status_code}")
                    logger.debug(f"Raw Response Text (AppDetails):\n{app_info_response.text[:500]}")

                    game_info_json = json.loads(app_info_response.text)
                    game_data = game_info_json.get(str(game_appid), {}).get("data")

                    if not game_data or not game_info_json.get(str(game_appid), {}).get("success"):
                        logger.warning(f"Could not get data for AppID {game_appid} or success=false. Response: {app_info_response.text}")
                        continue
                    
                    # Cache the game details permanently
                    cache_game_details(str(game_appid), game_data, permanent=True)

                if game_data.get("type") == "game":
                    # Use cached boolean fields for faster performance if available
                    is_multiplayer = game_data.get("is_multiplayer")
                    
                    # Fallback to category analysis if boolean field not available
                    if is_multiplayer is None:
                        categories = game_data.get("categories", [])
                        is_multiplayer = any(cat.get("id") in [1, 36, 38] for cat in categories)
                    
                    if is_multiplayer:
                        game_name = game_data.get("name", f"Unknown Game ({game_appid})")
                        game_entries.append(f"- {game_name}")

            except requests.exceptions.RequestException as e:
                logger.error(f"Request error fetching app details for AppID {game_appid}: {e}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error for AppID {game_appid}. Response: {app_info_response.text[:200]}")
            except Exception as e:
                logger.error(f"Unexpected error processing game {game_appid}: {e}", exc_info=True)

        if not game_entries:
            final_message = header + "None found."
        else:
            # Use utility function to handle message truncation
            footer_template = "\n... and {count} more games!"
            final_message = truncate_message_list(game_entries, header, footer_template)

        await self.bot.send_dm(ctx.author_id, final_message)


    """
    [help]|!list_users|list the registered users|!list_users | the list of registered user will be sent to you in dm. ***This command can be used in bot DM***
    """
    @prefixed_command(name="list_users")
    async def list_users(self, ctx: PrefixedContext):
        registered_users = await self._load_registered_users()
        if not registered_users:
            await self.bot.send_dm(ctx.author_id, "No users are currently registered.")
            return

        header = "Here are the users currently registered:\n"
        user_entries = []
        
        for discord_id in registered_users.keys():
            # Try to get cached username first
            cached_username = get_cached_discord_user(discord_id)
            if cached_username:
                user_entries.append(f"- {cached_username} (<@{discord_id}>)")
                continue

            # If not cached, fetch from Discord API
            try:
                user_obj = await self.bot.fetch_user(discord_id)
                if user_obj:
                    # Cache the username for 1 hour
                    cache_discord_user(discord_id, user_obj.username, cache_hours=1)
                    user_entries.append(f"- {user_obj.username} (<@{discord_id}>)")
                else:
                    user_entries.append(f"- <@{discord_id}> (User Not Found)")
            except Exception:
                user_entries.append(f"- <@{discord_id}> (User Not Found/Error)")

        # Use utility function to handle message truncation
        footer_template = "\n... and {count} more users!"
        final_message = truncate_message_list(user_entries, header, footer_template)
        
        await self.bot.send_dm(ctx.author_id, final_message)

    @Task.create(IntervalTrigger(hours=6))
    async def cleanup_cache_task(self):
        """Periodic task to clean up expired cache entries."""
        logger.info("Running cache cleanup task...")
        cleanup_expired_cache()

    @listen()
    async def on_startup(self):
        self.cleanup_cache_task.start()
        logger.info("--Common Games cache cleanup task started")

def setup(bot):  # Remove type annotation to avoid Extension constructor conflict
    common_games(bot)
