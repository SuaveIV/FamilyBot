# Import core interactions components needed for the Extension and Tasks
from interactions import Extension, Task, IntervalTrigger, listen # Client is not needed unless you use it directly (e.g., Client.create_context)
# Import prefixed command specific items from their extension ONLY
from interactions.ext.prefixed_commands import prefixed_command, PrefixedContext
import requests
import json
import logging
import os
from datetime import datetime, timedelta

# Import necessary items from your config and lib modules
from familybot.config import (
    NEW_GAME_CHANNEL_ID, WISHLIST_CHANNEL_ID, FAMILY_STEAM_ID, FAMILY_USER_DICT,
    ADMIN_DISCORD_ID, STEAMWORKS_API_KEY, PROJECT_ROOT
)
from familybot.lib.family_utils import get_family_game_list_url, find_in_2d_list, format_message
from familybot.lib.familly_game_manager import get_saved_games, set_saved_games

# Setup logging for this specific module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class steam_family(Extension):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Steam Family Plugin loaded")

    async def _send_admin_dm(self, message: str) -> None:
        """Helper to send error/warning messages to the bot admin via DM."""
        try:
            admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await admin_user.send(f"Steam Family Plugin Error ({now_str}): {message}")
        except Exception as e:
            logger.error(f"Failed to send DM to admin {ADMIN_DISCORD_ID}: {e}")

    async def _handle_api_response(self, api_name: str, response: requests.Response) -> dict or None:
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

        # Removed STEAMWORKS_API_KEY check for this command, as it now relies on webapi_token via get_family_game_list_url()

        loading_message = await ctx.send(f"Searching for games with {number} copies...")

        games_json = None
        try:
            url_family_list = get_family_game_list_url() # This function now uses webapi_token
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

            for game in game_list:
                if game.get("exclude_reason") != 3 and len(game.get("owner_steamids", [])) >= number:
                    game_array.append(str(game.get("appid")))

            for game_appid in game_array:
                game_url = f"https://store.steampowered.com/api/appdetails?appids={game_appid}&cc=fr&l=fr"
                logger.info(f"Fetching app details for AppID: {game_appid} for coop check")
                app_info_response = requests.get(game_url, timeout=10)
                game_info_json = await self._handle_api_response("AppDetails", app_info_response)
                if not game_info_json: continue

                game_data = game_info_json.get(str(game_appid), {}).get("data")
                if not game_data:
                    logger.warning(f"No game data found for AppID {game_appid} in app details response for coop check.")
                    continue

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

        except ValueError as e: # Catch ValueError if webapi_token is missing/invalid
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
            await self.bot.send_log_dm("Force Notification")
        else:
            await ctx.send("You do not have permission to use this command, or it must be used in DMs.")

    @prefixed_command(name="force_wishlist")
    async def force_wishlist_command(self, ctx: PrefixedContext):
        if str(ctx.author_id) == str(ADMIN_DISCORD_ID) and ctx.guild is None:
            await ctx.send("Forcing wishlist refresh...")
            await self.refresh_wishlist()
            logger.info("Force wishlist refresh initiated by admin.")
            await self.bot.send_log_dm("Force Wishlist")
        else:
            await ctx.send("You do not have permission to use this command, or it must be used in DMs.")

    @Task.create(IntervalTrigger(hours=1))
    async def send_new_game(self) -> None:
        logger.info("Running send_new_game task...")
        # Removed STEAMWORKS_API_KEY check for this task, as it now relies on webapi_token

        games_json = None
        try:
            url_family_list = get_family_game_list_url() # This function now uses webapi_token
            answer = requests.get(url_family_list, timeout=15)
            games_json = await self._handle_api_response("GetFamilySharedApps", answer)
            if not games_json: return

            game_list = games_json.get("response", {}).get("apps", [])
            if not game_list:
                logger.warning("No apps found in family game list response for new game check.")
                return

            game_owner_list = {}
            game_array = []
            for game in game_list:
                if game.get("exclude_reason") != 3:
                    appid = str(game.get("appid"))
                    game_array.append(appid)
                    if len(game.get("owner_steamids", [])) == 1:
                        game_owner_list[appid] = str(game["owner_steamids"][0])

            game_file_list = get_saved_games()
            new_games = set(game_array) - set(game_file_list)

            # --- NEW LOGIC: Rate-limiting for large number of new games ---
            new_games_list = sorted(list(new_games)) # Sort for consistent "latest"
            if len(new_games_list) > 10: # If more than 10 new games
                logger.warning(f"Detected {len(new_games_list)} new games. Processing only the latest 10 to avoid rate limits.")
                await self.bot.send_to_channel(NEW_GAME_CHANNEL_ID, f"Detected {len(new_games_list)} new games in the Family Library. Processing only the latest 10 to avoid API rate limits. More may be announced in subsequent checks.")
                new_games_to_process = new_games_list[-10:] # Get the latest 10
            else:
                new_games_to_process = new_games_list
            # --- End NEW LOGIC ---

            if new_games_to_process:
                logger.info(f"Processing {len(new_games_to_process)} new games.")
                for new_appid in new_games_to_process: # Iterate over the potentially limited list
                    game_url = f"https://store.steampowered.com/api/appdetails?appids={new_appid}&cc=fr&l=fr"
                    logger.info(f"Fetching app details for new game AppID: {new_appid}")
                    app_info_response = requests.get(game_url, timeout=10)
                    game_info_json = await self._handle_api_response("AppDetails (New Game)", app_info_response)
                    if not game_info_json: continue

                    game_data = game_info_json.get(str(new_appid), {}).get("data")
                    if not game_data:
                        logger.warning(f"No game data found for new game AppID {new_appid} in app details response.")
                        continue

                    is_family_shared_game = any(cat.get("id") == 62 for cat in game_data.get("categories", []))

                    if game_data.get("type") == "game" and game_data.get("is_free") == False and is_family_shared_game:
                        owner_steam_id = game_owner_list.get(str(new_appid))
                        owner_name = FAMILY_USER_DICT.get(owner_steam_id, "Unknown Owner")
                        await self.bot.send_to_channel(NEW_GAME_CHANNEL_ID, f"Thank you to {owner_name} for \n https://store.steampowered.com/app/{new_appid}")
                    else:
                        logger.debug(f"Skipping new game {new_appid}: not a paid game, not family shared, or not type 'game'.")

                # set_saved_games(game_array) # Moved to after processing
                # Save the ENTIRE game_array here, not just the processed subset
                # This ensures future checks don't re-detect already processed games
                set_saved_games(game_array)
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
        # THIS COMMAND *STILL NEEDS* STEAMWORKS_API_KEY
        if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
            logger.error("STEAMWORKS_API_KEY is not configured for wishlist task.")
            await self._send_admin_dm("Steam API key is not configured for wishlist task.")
            return

        global_wishlist = []

        for user_steam_id, user_name in FAMILY_USER_DICT.items():
            wishlist_url = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?key={STEAMWORKS_API_KEY}&steamid={user_steam_id}"
            logger.info(f"Fetching wishlist for {user_name} (Steam ID: {user_steam_id})")

            wishlist_json = None
            try:
                wishlist_response = requests.get(wishlist_url, timeout=15)
                if wishlist_response.text == "{\"success\":2}":
                    logger.info(f"{user_name}'s wishlist is private or empty.")
                    continue

                wishlist_json = await self._handle_api_response(f"GetWishlist ({user_name})", wishlist_response)
                if not wishlist_json: continue

                wishlist_items = wishlist_json.get("response", {}).get("items", [])

                if not wishlist_items:
                    logger.info(f"No items found in {user_name}'s wishlist.")
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
                logger.critical(f"An unexpected error occurred fetching/processing {user_name}'s wishlist: {e}", exc_info=True)
                await self._send_admin_dm(f"Critical error wishlist {user_name}: {e}")

        duplicate_games_for_display = []
        for item in global_wishlist:
            app_id = item[0]
            owner_steam_ids = item[1]

            if len(owner_steam_ids) > 1:
                game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=fr&l=fr"
                logger.info(f"Fetching app details for wishlist AppID: {app_id}")

                game_info_json = None
                try:
                    game_info_response = requests.get(game_url, timeout=10)
                    game_info_json = await self._handle_api_response("AppDetails (Wishlist)", game_info_response)
                    if not game_info_json: continue

                    game_data = game_info_json.get(str(app_id), {}).get("data")
                    if not game_data:
                        logger.warning(f"No game data found for wishlist AppID {app_id} in app details response.")
                        continue

                    is_family_shared_category = any(cat.get("id") == 62 for cat in game_data.get("categories", []))

                    if (game_data.get("type") == "game"
                        and game_data.get("is_free") == False
                        and is_family_shared_category
                        and "recommendations" in game_data
                        and app_id not in get_saved_games()
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

        pinned_messages = []
        try:
            pinned_messages = await wishlist_channel.fetch_pinned_messages()
        except Exception as e:
            logger.error(f"Error fetching pinned messages from channel {WISHLIST_CHANNEL_ID}: {e}")
            await self._send_admin_dm(f"Error fetching pinned messages: {e}")

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

def setup(bot):
    steam_family(bot)