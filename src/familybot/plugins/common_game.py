# In src/familybot/plugins/common_game.py

from interactions import Extension, Client, listen, Task, IntervalTrigger # Client, Task, IntervalTrigger are likely not needed here; keep if used elsewhere
from interactions.ext.prefixed_commands import prefixed_command, PrefixedContext
import json
import requests
import os # For os.path.join
import logging # For better logging

# Import necessary items from your config and lib modules
from familybot.config import ADMIN_DISCORD_ID, STEAMWORKS_API_KEY, PROJECT_ROOT
from familybot.lib.utils import get_common_elements_in_lists

# Setup logging for this specific module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the path to register.csv using PROJECT_ROOT
REGISTER_CSV_PATH = os.path.join(PROJECT_ROOT, 'register.csv')

class common_games(Extension):
    def __init__(self, bot):
        self.bot = bot # Store bot instance for sending DMs
        logger.info("common Games Plugin loaded")

    async def _send_admin_dm(self, message: str) -> None:
        """Helper to send error/warning messages to the bot admin via DM."""
        try:
            admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
            await admin_user.send(message)
        except Exception as e:
            logger.error(f"Failed to send DM to admin {ADMIN_DISCORD_ID}: {e}")

    async def _load_registered_users(self) -> dict:
        """Loads registered users from register.csv into a dictionary."""
        users = {}
        try:
            with open(REGISTER_CSV_PATH, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(',')
                    if len(parts) == 2:
                        discord_id, steam_id = parts
                        users[discord_id] = steam_id
                    else:
                        logger.warning(f"Malformed line in register.csv: '{line}'")
            return users
        except FileNotFoundError:
            logger.error(f"register.csv not found at {REGISTER_CSV_PATH}")
            await self._send_admin_dm(f"Error: register.csv not found at {REGISTER_CSV_PATH}")
            return {}
        except Exception as e:
            logger.error(f"Error reading register.csv: {e}")
            await self._send_admin_dm(f"Error reading register.csv: {e}")
            return {}

    """
    [help]|!register|make the link between a discord account and a steam one| !register YOUR_STEAM_ID | to get your steam id you cans go on this page and put the url of your steam profile page: https://steamdb.info/calculator/. ***This command can be used in bot DM***
    """
    @prefixed_command(name="register")
    async def register(self, ctx: PrefixedContext, steam_id: str):
        discord_id = str(ctx.author_id)
        registered_users = await self._load_registered_users()

        if len(steam_id) != 17 or not steam_id.isdigit():
            logger.warning(f"Invalid Steam ID provided by {discord_id}: {steam_id}")
            await ctx.send("You've made a mistake on your Steam ID. Please ensure it's a 17-digit number (e.g., from steamid.pro) or contact an admin.")
            return

        if discord_id in registered_users or steam_id in registered_users.values():
            await ctx.send("You are already registered with this Discord ID or Steam ID.")
            return

        try:
            with open(REGISTER_CSV_PATH, 'a') as f:
                f.write(f"{discord_id},{steam_id}\n")
            await ctx.send("You have been successfully registered!")
            logger.info(f"Registered Discord ID {discord_id} with Steam ID {steam_id}")
        except Exception as e:
            logger.error(f"Error writing to register.csv for {discord_id}: {e}")
            await ctx.send("An error occurred during registration. Please try again or contact an admin.")
            await self._send_admin_dm(f"Error registering user {discord_id} to register.csv: {e}")


    """
    [help]|!common_games|get the multiplayer games that the given person have in common and send the result in dm| !common_games @user1 @user2 ... | the users put in the command needs to be registered before. ***This command can be used in bot DM***
    """
    @prefixed_command(name="common_games")
    async def get_common_games(self, ctx: PrefixedContext, *args):
        target_discord_ids = [str(ctx.author_id)] # Always include author's ID
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
        # Separate check for missing users to give better feedback
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
            temp_game_list = []
            steam_get_games_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAMWORKS_API_KEY}&steamid={steam_id}&format=json&include_appinfo=1"
            logger.info(f"Fetching games for Steam ID: {steam_id}")
            try:
                answer = requests.get(steam_get_games_url, timeout=10)
                answer.raise_for_status()

                logger.debug(f"Status Code: {answer.status_code}")
                logger.debug(f"Raw Response Text (GetOwnedGames):\n{answer.text[:500]}")

                response_data = json.loads(answer.text)
                user_game_list_json = response_data.get("response", {}).get("games", [])

                if not user_game_list_json:
                    logger.warning(f"No games found or 'games' key missing for Steam ID {steam_id}. Full response: {response_data}")
                    # A user might genuinely have no games, or a private profile.
                    # We continue here, as we can still find common games among other users.
                    continue

                for game in user_game_list_json:
                    temp_game_list.append(game["appid"])
                game_lists.append(temp_game_list)

            except requests.exceptions.RequestException as e:
                logger.error(f"Request error fetching games for Steam ID {steam_id}: {e}")
                await self.bot.send_dm(ctx.author_id, f"Error fetching games for Steam ID {steam_id}. Steam API issue. Check logs.")
                # Don't return here, continue with other users if possible
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error for Steam ID {steam_id}. Response: {answer.text[:200]}")
                await self.bot.send_dm(ctx.author_id, f"Error processing Steam API response for Steam ID {steam_id}. Check logs.")
                # Don't return here
            except KeyError as e:
                logger.error(f"Missing key in Steam API response for Steam ID {steam_id}: {e}. Response: {response_data}")
                await self.bot.send_dm(ctx.author_id, f"Unexpected response format from Steam API for Steam ID {steam_id}. Check logs.")
                # Don't return here
            except Exception as e:
                logger.critical(f"An unexpected error occurred during game fetching for Steam ID {steam_id}: {e}", exc_info=True)
                await self._send_admin_dm(f"Critical error fetching games for {steam_id}: {e}")
                # Don't return here

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

        message_parts = ["Common Multiplayer Games:\n"] # Use a list to build parts
        for game_appid in common_game_appids:
            game_url = f"https://store.steampowered.com/api/appdetails?appids={game_appid}&cc=fr&l=fr"
            logger.info(f"Fetching app details for AppID: {game_appid}")
            try:
                app_info_response = requests.get(game_url, timeout=5)
                app_info_response.raise_for_status()

                logger.debug(f"Status Code: {app_info_response.status_code}")
                logger.debug(f"Raw Response Text (AppDetails):\n{app_info_response.text[:500]}")

                game_info_json = json.loads(app_info_response.text)
                game_data = game_info_json.get(str(game_appid), {}).get("data")

                if not game_data or not game_info_json.get(str(game_appid), {}).get("success"):
                    logger.warning(f"Could not get data for AppID {game_appid} or success=false. Response: {app_info_response.text}")
                    continue

                if game_data.get("type") == "game":
                    categories = game_data.get("categories", [])
                    is_multiplayer = any(cat.get("id") in [1, 36, 38] for cat in categories)

                    if is_multiplayer:
                        game_name = game_data.get("name", f"Unknown Game ({game_appid})")
                        message_parts.append(f"- {game_name}\n")

            except requests.exceptions.RequestException as e:
                logger.error(f"Request error fetching app details for AppID {game_appid}: {e}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error for AppID {game_appid}. Response: {app_info_response.text[:200]}")
            except Exception as e:
                logger.error(f"Unexpected error processing game {game_appid}: {e}", exc_info=True)

        final_message = "".join(message_parts)
        if len(final_message) <= 25: # If only "Common Multiplayer Games:\n"
            final_message += "None found."

        # Send the final message, handling Discord's message limits if it becomes too long
        if len(final_message) > 1950: # Adjust buffer as needed, Discord limit is 2000
            truncated_message = final_message[:1950] + "\n... (Message too long, truncated)"
            await self.bot.send_dm(ctx.author_id, truncated_message)
            self.bot.send_log_dm(f"Common games message for {ctx.author_id} was truncated.")
        else:
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

        list_message = "Here are the users currently registered:\n"
        for discord_id in registered_users.keys():
            # Attempt to fetch user name for better display, but use ID as fallback
            try:
                user_obj = await self.bot.fetch_user(discord_id)
                list_message += f"- {user_obj.username} (<@{discord_id}>)\n"
            except Exception:
                list_message += f"- <@{discord_id}> (User Not Found/Error)\n"

        # Handle message length
        if len(list_message) > 1950:
            list_message = list_message[:1950] + "\n... (List too long, truncated)"
        
        await self.bot.send_dm(ctx.author_id, list_message)

def setup(bot):
    common_games(bot)