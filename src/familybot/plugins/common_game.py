# In src/familybot/plugins/common_game.py

import json
import os
import sqlite3  # Import sqlite3 for specific error handling

import aiohttp
from interactions import Extension, IntervalTrigger, Task, listen
from interactions.ext.prefixed_commands import PrefixedContext, prefixed_command

from familybot.config import ADMIN_DISCORD_ID, PROJECT_ROOT, STEAMWORKS_API_KEY
from familybot.lib.database import (
    cleanup_expired_cache,
    get_db_connection,
)
from familybot.lib.discord_user_repository import (
    cache_discord_user,
    get_cached_discord_user,
)
from familybot.lib.game_details_repository import (
    cache_game_details,
    get_cached_game_details,
)
from familybot.lib.user_games_repository import (
    cache_user_games,
    get_cached_user_games,
)
from familybot.lib.logging_config import get_logger
from familybot.lib.types import FamilyBotClient
from familybot.lib.discord_utils import truncate_message_list
from familybot.lib.utils import get_common_elements_in_lists

# Setup enhanced logging for this specific module
logger = get_logger(__name__)

# Define the path to OLD register.csv for migration (if it exists)
OLD_REGISTER_CSV_PATH = os.path.join(PROJECT_ROOT, "register.csv")


def _migrate_users_to_db(conn: sqlite3.Connection):
    """Internal function to migrate existing register.csv data to the database."""
    if os.path.exists(OLD_REGISTER_CSV_PATH):
        logger.info(
            f"Attempting to migrate users from old file: {OLD_REGISTER_CSV_PATH}"
        )
        try:
            with open(OLD_REGISTER_CSV_PATH, "r") as f:
                users_to_insert = []
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(",")
                    if len(parts) == 2:
                        discord_id, steam_id = parts
                        users_to_insert.append((discord_id, steam_id))

                if users_to_insert:
                    cursor = conn.cursor()
                    cursor.executemany(
                        "INSERT OR IGNORE INTO users (discord_id, steam_id) VALUES (?, ?)",
                        users_to_insert,
                    )
                    conn.commit()
                    logger.info(
                        f"Migrated {len(users_to_insert)} users from {OLD_REGISTER_CSV_PATH} to database."
                    )
                    # Optionally, remove the old file after successful migration
                    # os.remove(OLD_REGISTER_CSV_PATH)
                    # logger.info(f"Removed old register.csv file: {OLD_REGISTER_CSV_PATH}")
                else:
                    logger.info("No users found in old register.csv for migration.")
        except Exception as e:
            logger.error(
                f"Error during register.csv migration to DB: {e}", exc_info=True
            )
    else:
        logger.info("No old register.csv found for migration. Skipping.")


class common_games(Extension):
    def __init__(self, bot: FamilyBotClient):
        self.bot: FamilyBotClient = bot
        logger.info("common Games Plugin loaded")

    async def _send_admin_dm(self, message: str) -> None:
        """Helper to send error/warning messages to the bot admin via DM."""
        try:
            admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
            if admin_user:
                await admin_user.send(message)
        except Exception as e:
            logger.error(f"Failed to send DM to admin {ADMIN_DISCORD_ID}: {e}")

    async def _load_registered_users(self) -> dict[str, str]:
        """Loads registered users from the database into a dictionary."""
        users = {}
        conn = None
        try:
            conn = get_db_connection()
            _migrate_users_to_db(conn)  # Attempt migration if file exists on first read
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
        registered_users = await self._load_registered_users()  # Check existing from DB

        if len(steam_id) != 17 or not steam_id.isdigit():
            logger.warning(f"Invalid Steam ID provided by {discord_id}: {steam_id}")
            await ctx.send(
                "You've made a mistake on your Steam ID. Please ensure it's a 17-digit number (e.g., from steamid.pro) or contact an admin."
            )
            return

        if discord_id in registered_users:
            await ctx.send("You are already registered with this Discord ID.")
            return
        if steam_id in registered_users.values():
            await ctx.send(
                "This Steam ID is already registered to another Discord user."
            )
            return

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Insert into 'users' table
            cursor.execute(
                "INSERT INTO users (discord_id, steam_id) VALUES (?, ?)",
                (discord_id, steam_id),
            )

            # Also insert/update 'family_members' table for Web UI display
            # Use INSERT OR REPLACE to backfill discord_id if member already exists from config
            friendly_name = ctx.author.display_name
            cursor.execute(
                "INSERT OR REPLACE INTO family_members (steam_id, friendly_name, discord_id) VALUES (?, ?, ?)",
                (steam_id, friendly_name, discord_id),
            )

            conn.commit()
            await ctx.send(
                f"You have been successfully registered as '{friendly_name}'!"
            )
            logger.info(
                f"Registered Discord ID {discord_id} with Steam ID {steam_id} in 'users' and 'family_members' DB tables."
            )
        except sqlite3.IntegrityError:  # Specific error for UNIQUE constraint violation
            logger.warning(
                f"Attempted to register existing Discord ID {discord_id} or Steam ID {steam_id} (IntegrityError)."
            )
            await ctx.send(
                "An error occurred: This Discord ID or Steam ID might already be registered. Try `!list_users`."
            )
        except Exception as e:
            logger.error(
                f"Error writing to database for {discord_id}: {e}", exc_info=True
            )
            await ctx.send(
                "An error occurred during registration. Please try again or contact an admin."
            )
            await self._send_admin_dm(f"Error registering user {discord_id} to DB: {e}")
        finally:
            if conn:
                conn.close()

    async def _resolve_steam_vanity_url(
        self, vanity_url: str, session: aiohttp.ClientSession | None = None
    ) -> str | None:
        """Resolve a Steam vanity URL (custom name) to a Steam ID.

        Args:
            vanity_url: The vanity URL name (e.g., "GabeNewell" from steamcommunity.com/id/GabeNewell)
            session: Optional aiohttp.ClientSession to reuse. If None, a new session is created.

        Returns:
            The Steam ID (SteamID64) if found, None otherwise.
        """
        if (
            not STEAMWORKS_API_KEY
            or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE"
        ):
            return None

        url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/"
        params = {
            "key": STEAMWORKS_API_KEY,
            "vanityurl": vanity_url,
        }

        async def _do_resolve(s: aiohttp.ClientSession) -> str | None:
            try:
                async with s.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return None
                    data = await response.json()
                    result = data.get("response", {})
                    if result.get("success") == 1:
                        return result.get("steamid")
            except Exception as e:
                logger.debug(f"Failed to resolve vanity URL '{vanity_url}': {e}")
            return None

        if session is not None:
            return await _do_resolve(session)
        else:
            async with aiohttp.ClientSession() as new_session:
                return await _do_resolve(new_session)

    """
    [help]|!common_games|get the multiplayer games that the given person have in common| !common_games user1 user2 ... | Accepts Discord IDs, @mentions, Steam IDs, Steam profile names, or Discord usernames in quotes (e.g., "Username"). The users need to be registered before. ***This command can be used in bot DM***
    """

    @prefixed_command(name="common_games")
    async def get_common_games(self, ctx: PrefixedContext, *args):
        target_discord_ids = [str(ctx.author_id)]
        # Load registered users once to avoid repeated DB queries
        registered_users = await self._load_registered_users()

        async with aiohttp.ClientSession() as session:
            for arg in args:
                # Handle quoted Discord names (e.g., "Username" or 'Display Name')
                if (arg.startswith('"') and arg.endswith('"')) or (
                    arg.startswith("'") and arg.endswith("'")
                ):
                    username = arg[1:-1]  # Strip quotes
                    if not username:
                        await ctx.send("Empty username in quotes.")
                        return

                    # Search guild members by username or display name
                    found = False
                    if ctx.guild is None:
                        await ctx.send(
                            "This command must be run in a server; username lookup is not available in DMs."
                        )
                        return
                    for member in ctx.guild.members:
                        if (
                            member.username.lower() == username.lower()
                            or member.display_name.lower() == username.lower()
                        ):
                            member_id = str(member.id)
                            if member_id not in target_discord_ids:
                                target_discord_ids.append(member_id)
                            found = True
                            break

                    if not found:
                        await ctx.send(
                            f"Could not find a user with name '{username}' in this server."
                        )
                        return
                # Handle mentions: <@123456> or <@!123456>
                elif arg.startswith("<@") and arg.endswith(">"):
                    clean_id = arg.strip("<@!>")
                    if clean_id.isdigit() and clean_id not in target_discord_ids:
                        target_discord_ids.append(clean_id)
                # Handle plain numeric IDs (Discord or Steam IDs)
                elif arg.isdigit() and len(arg) >= 17 and len(arg) <= 20:
                    # Verify if arg is a registered Discord ID
                    if arg in registered_users:
                        if arg not in target_discord_ids:
                            target_discord_ids.append(arg)
                    else:
                        # Check if arg is a registered Steam ID and map back to Discord ID
                        found_discord_id = None
                        for discord_id, steam_id in registered_users.items():
                            if steam_id == arg:
                                found_discord_id = discord_id
                                break
                        if found_discord_id is None:
                            await ctx.send(
                                f"'{arg}' could not be resolved; the user is not registered."
                            )
                            return
                        elif found_discord_id not in target_discord_ids:
                            target_discord_ids.append(found_discord_id)
                        else:
                            await ctx.send(
                                f"User with Steam ID '{arg}' is already in the target list."
                            )
                # Handle Steam vanity URLs / profile names
                else:
                    # Try to resolve as Steam vanity URL
                    steam_id = await self._resolve_steam_vanity_url(arg, session)
                    if steam_id:
                        # Find the Discord user registered with this Steam ID
                        found_discord_id = None
                        for discord_id, sid in registered_users.items():
                            if sid == steam_id:
                                found_discord_id = discord_id
                                break
                        if found_discord_id is None:
                            await ctx.send(
                                f"Steam profile '{arg}' was found, but no registered Discord user matches that Steam ID."
                            )
                            return
                        elif found_discord_id not in target_discord_ids:
                            target_discord_ids.append(found_discord_id)
                        else:
                            await ctx.send(
                                f"User '{arg}' is already in the target list."
                            )
                    else:
                        await ctx.send(
                            f"Could not resolve '{arg}'. Please use a Discord ID, @mention, Steam ID (17-20 digits), or Steam profile name."
                        )
                        return
        steam_ids_to_check = []
        missing_discord_ids = []

        for discord_id in target_discord_ids:
            if discord_id in registered_users:
                steam_ids_to_check.append(registered_users[discord_id])
            else:
                missing_discord_ids.append(discord_id)

        if missing_discord_ids:
            try:
                await ctx.author.send(
                    f"Hey {ctx.author.display_name}, not all users listed are registered. Please register them or use `!list_users` to see registered users."
                )
            except Exception as e:
                logger.warning(f"Failed to send DM to {ctx.author_id}: {e}")
                await ctx.send(
                    f"Hey {ctx.author.display_name}, not all users listed are registered. Please register them or use `!list_users` to see registered users."
                )
            return

        if (
            not STEAMWORKS_API_KEY
            or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE"
        ):
            logger.error(
                "STEAMWORKS_API_KEY is missing or is a placeholder. Cannot fetch Steam games."
            )
            await ctx.send("Steam API key is not configured. Please contact an admin.")
            return

        game_lists = []
        async with aiohttp.ClientSession() as session:
            for steam_id in steam_ids_to_check:
                # Try to get cached games first
                cached_games = get_cached_user_games(steam_id)
                if cached_games is not None:
                    logger.info(
                        f"Using cached games for Steam ID: {steam_id} ({len(cached_games)} games)"
                    )
                    game_lists.append([int(appid) for appid in cached_games])
                    continue

                # If not cached, fetch from API
                temp_game_list = []
                steam_get_games_url = (
                    "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
                )
                steam_get_games_params = {
                    "key": STEAMWORKS_API_KEY,
                    "steamid": steam_id,
                    "format": "json",
                    "include_appinfo": 1,
                }
                logger.info(f"Fetching games from API for Steam ID: {steam_id}")
                response_data = None
                try:
                    async with session.get(
                        steam_get_games_url,
                        params=steam_get_games_params,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as answer:
                        answer.raise_for_status()
                        text_response = await answer.text()
                        logger.debug(f"Status Code: {answer.status}")
                        logger.debug(
                            f"Raw Response Text (GetOwnedGames):\n{text_response[:500]}"
                        )

                        response_data = json.loads(text_response)
                        user_game_list_json = response_data.get("response", {}).get(
                            "games", []
                        )

                        if not user_game_list_json:
                            logger.warning(
                                f"No games found or 'games' key missing for Steam ID {steam_id}. Full response: {response_data}"
                            )
                            continue

                        for game in user_game_list_json:
                            temp_game_list.append(game["appid"])

                        # Cache the results for 6 hours
                        cache_user_games(steam_id, temp_game_list, cache_hours=6)
                        game_lists.append(temp_game_list)

                except aiohttp.ClientError as e:
                    logger.error(
                        f"Request error fetching games for Steam ID {steam_id}: {e}"
                    )
                    await ctx.send(
                        f"Error fetching games for Steam ID {steam_id}. Steam API issue. Check logs."
                    )
                except json.JSONDecodeError:
                    logger.error(f"JSON decode error for Steam ID {steam_id}.")
                    await ctx.send(
                        f"Error processing Steam API response for Steam ID {steam_id}. Check logs."
                    )
                except KeyError as e:
                    logger.error(
                        f"Missing key in Steam API response for Steam ID {steam_id}: {e}. Response: {response_data if response_data is not None else '<no response>'}"
                    )
                    await ctx.send(
                        f"Unexpected response format from Steam API for Steam ID {steam_id}. Check logs."
                    )
                except Exception as e:
                    logger.critical(
                        f"An unexpected error occurred during game fetching for Steam ID {steam_id}: {e}",
                        exc_info=True,
                    )
                    await self._send_admin_dm(
                        f"Critical error fetching games for {steam_id}: {e}"
                    )

        if not game_lists or len(game_lists) < len(steam_ids_to_check):
            if len(steam_ids_to_check) > 1:
                await ctx.send(
                    "Could not retrieve game lists for all specified users. Some users might have private profiles or an API error occurred. Cannot find common games."
                )
            else:
                await ctx.send(
                    "Could not retrieve your game list. Your profile might be private or an API error occurred."
                )
            return

        common_game_appids = get_common_elements_in_lists(game_lists)
        if not common_game_appids:
            await ctx.send("No common games found among the specified users.")
            return

        header = "Common Multiplayer Games:\n"
        game_entries = []

        async with aiohttp.ClientSession() as session:
            for game_appid in common_game_appids:
                try:
                    # Try to get cached game details first
                    cached_game = get_cached_game_details(str(game_appid))
                    if cached_game:
                        logger.info(
                            f"Using cached game details for AppID: {game_appid}"
                        )
                        game_data = cached_game
                    else:
                        # If not cached, fetch from API
                        game_url = f"https://store.steampowered.com/api/appdetails?appids={game_appid}&cc=us&l=en"
                        logger.info(
                            f"Fetching app details from API for AppID: {game_appid}"
                        )

                        async with session.get(
                            game_url, timeout=aiohttp.ClientTimeout(total=10)
                        ) as app_info_response:
                            app_info_response.raise_for_status()
                            text_response = await app_info_response.text()

                            logger.debug(f"Status Code: {app_info_response.status}")
                            logger.debug(
                                f"Raw Response Text (AppDetails):\n{text_response[:500]}"
                            )

                            game_info_json = json.loads(text_response)
                            game_data = game_info_json.get(str(game_appid), {}).get(
                                "data"
                            )

                            if not game_data or not game_info_json.get(
                                str(game_appid), {}
                            ).get("success"):
                                logger.warning(
                                    f"Could not get data for AppID {game_appid} or success=false. Response: {text_response}"
                                )
                                continue

                            # Cache the game details
                            cache_game_details(
                                str(game_appid), game_data, permanent=False
                            )

                    if game_data.get("type") == "game":
                        # Use cached boolean fields for faster performance if available
                        is_multiplayer = game_data.get("is_multiplayer")

                        # Fallback to category analysis if boolean field not available
                        if is_multiplayer is None:
                            categories = game_data.get("categories", [])
                            is_multiplayer = any(
                                cat.get("id") in [1, 36, 38] for cat in categories
                            )

                        if is_multiplayer:
                            game_name = game_data.get(
                                "name", f"Unknown Game ({game_appid})"
                            )
                            game_entries.append(f"- {game_name}")

                except aiohttp.ClientError as e:
                    logger.error(
                        f"Request error fetching app details for AppID {game_appid}: {e}"
                    )
                except json.JSONDecodeError:
                    logger.error(f"JSON decode error for AppID {game_appid}.")
                except Exception as e:
                    logger.error(
                        f"Unexpected error processing game {game_appid}: {e}",
                        exc_info=True,
                    )

        if not game_entries:
            final_message = header + "None found."
        else:
            # Use utility function to handle message truncation
            footer_template = "\n... and {count} more games!"
            final_message = truncate_message_list(game_entries, header, footer_template)

        await ctx.send(final_message)

    """
    [help]|!list_users|list the registered users|!list_users | the list of registered users will be shown in the channel where called. ***This command can be used in bot DM***
    """

    @prefixed_command(name="list_users")
    async def list_users(self, ctx: PrefixedContext):
        registered_users = await self._load_registered_users()
        if not registered_users:
            await ctx.send("No users are currently registered.")
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

        await ctx.send(final_message)

    @Task.create(IntervalTrigger(hours=6))
    async def cleanup_cache_task(self):
        """Periodic task to clean up expired cache entries."""
        logger.info("Running cache cleanup task...")
        cleanup_expired_cache()

    @listen()
    async def on_startup(self):
        self.cleanup_cache_task.start()
        logger.info("--Common Games cache cleanup task started")

        # Warm Discord user cache for all registered users
        try:
            registered_users = await self._load_registered_users()
            if registered_users:
                logger.info(
                    f"Warming Discord user cache for {len(registered_users)} users..."
                )
                for discord_id in registered_users.keys():
                    if not get_cached_discord_user(discord_id):
                        try:
                            user_obj = await self.bot.fetch_user(discord_id)
                            if user_obj:
                                cache_discord_user(discord_id, user_obj.username)
                        except Exception:
                            continue
                logger.info("Discord user cache warming complete")
        except Exception as e:
            logger.error(f"Error warming Discord user cache: {e}")


def setup(bot):  # Remove type annotation to avoid Extension constructor conflict
    common_games(bot)
