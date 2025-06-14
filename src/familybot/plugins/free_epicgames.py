# In src/familybot/plugins/free_epicgames.py

# Explicitly import what's needed from interactions
from interactions import Extension, listen, Task, IntervalTrigger
from interactions.ext.prefixed_commands import prefixed_command, PrefixedContext
from datetime import datetime, timedelta
import requests
import json
import logging

# Import from config
from familybot.config import EPIC_CHANNEL_ID, ADMIN_DISCORD_ID
from familybot.lib.types import FamilyBotClient

# Setup logging for this specific module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class free_epicgames(Extension):
    def __init__(self, bot: FamilyBotClient):
        self.bot: FamilyBotClient = bot  # Explicit type annotation for the bot attribute
        logger.info("Epic Games Plugin loaded")
        self._force_next_run = False
        self._last_checked_day = -1 # To prevent multiple checks on same day if scheduled

    async def _send_admin_dm(self, message: str) -> None:
        """Helper to send error/warning messages to the bot admin via DM."""
        try:
            admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
            if admin_user:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await admin_user.send(f"Epic Games Plugin Error ({now_str}): {message}")
        except Exception as e:
            logger.error(f"Failed to send DM to admin {ADMIN_DISCORD_ID}: {e}")

    @Task.create(IntervalTrigger(minutes=1)) # Check every minute
    async def send_epic_free_games(self) -> None:
        now = datetime.now()
        # Trigger condition: Thursday at 17:30 (5:30 PM)
        is_scheduled_time = (now.weekday() == 3 and now.hour == 17 and now.minute == 30)

        # Prevent multiple runs on the same scheduled minute on the same day
        if is_scheduled_time and self._last_checked_day == now.day:
             logger.debug("Scheduled Epic Games check already performed today.")
             return

        should_run = self._force_next_run or is_scheduled_time

        if should_run:
            if is_scheduled_time:
                self._last_checked_day = now.day # Mark that we ran for this day

            logger.info("Checking for free Epic Games...")
            epic_games_channel = None
            try:
                epic_games_channel = await self.bot.fetch_channel(EPIC_CHANNEL_ID)
                if not epic_games_channel:
                    logger.error(f"Epic Games channel not found for ID: {EPIC_CHANNEL_ID}. Check config.yml.")
                    await self._send_admin_dm(f"Epic Games channel not found for ID: {EPIC_CHANNEL_ID}.")
                    self._force_next_run = False # Reset force if channel is unreachable
                    return
            except Exception as e:
                logger.error(f"Error fetching Epic Games channel (ID: {EPIC_CHANNEL_ID}): {e}")
                await self._send_admin_dm(f"Error fetching Epic Games channel: {e}")
                self._force_next_run = False
                return

            epic_url = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions?locale=fr&country=FR&allowCountries=FR"
            base_shop_url = "https://store.epicgames.com/fr/p/"

            try:
                answer = requests.get(epic_url, timeout=10)
                answer.raise_for_status()

                json_answer = json.loads(answer.text)
                game_list = json_answer.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])

                if not game_list:
                    logger.warning("No game elements found in Epic Games API response.")
                    if hasattr(epic_games_channel, 'send'):
                        await epic_games_channel.send("Couldn't retrieve free games information this week.")  # type: ignore
                    self._force_next_run = False
                    return

                messages_to_send = []

                for game in game_list:
                    title = game.get("title", "Unknown Title")
                    promotions = game.get("promotions")

                    if not promotions:
                        logger.debug(f"Skipping {title} due to missing promotions data.")
                        continue

                    current_promotions = promotions.get("promotionalOffers")

                    if current_promotions:
                        for offer_bundle in current_promotions:
                            for offer_item in offer_bundle.get("promotionalOffers", []):
                                if offer_item.get("discountSetting", {}).get("discountPercentage") == 0:
                                    game_epic_slug = None
                                    for attr in game.get("customAttributes", []):
                                        if attr.get("key") == "com.epicgames.app.productSlug":
                                            game_epic_slug = attr.get("value")
                                            break
                                    if game_epic_slug:
                                        messages_to_send.append(base_shop_url + game_epic_slug)
                                        logger.info(f"Found current free game: {title}")
                                        break
                            if messages_to_send: break

                if messages_to_send and hasattr(epic_games_channel, 'send'):
                    await epic_games_channel.send("The free games on the Epic Game Store this week are:")  # type: ignore
                    for msg_url in messages_to_send:
                        await epic_games_channel.send(msg_url)  # type: ignore
                elif hasattr(epic_games_channel, 'send'):
                    await epic_games_channel.send("No new free games found for this week, or already announced.")  # type: ignore

            except requests.exceptions.RequestException as e:
                logger.error(f"Request error fetching Epic Games: {e}")
                if hasattr(epic_games_channel, 'send'):
                    await epic_games_channel.send("An error occurred while fetching free Epic Games. Please try again later.")  # type: ignore
                await self._send_admin_dm(f"Error fetching Epic Games: {e}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error for Epic Games response: {e}. Raw: {answer.text[:200]}")
                if hasattr(epic_games_channel, 'send'):
                    await epic_games_channel.send("An error occurred processing Epic Games data. Please try again later.")  # type: ignore
                await self._send_admin_dm(f"JSON error Epic Games: {e}")
            except Exception as e:
                logger.critical(f"An unexpected error occurred in send_epic_free_games: {e}", exc_info=True)
                if hasattr(epic_games_channel, 'send'):
                    await epic_games_channel.send("An unexpected error occurred with Epic Games task.")  # type: ignore
                await self._send_admin_dm(f"Critical error Epic Games: {e}")
            finally:
                self._force_next_run = False

    @prefixed_command(name="force_epic")
    async def force_command(self, ctx: PrefixedContext):
        if str(ctx.author_id) == str(ADMIN_DISCORD_ID) and ctx.guild is None:
            self._force_next_run = True
            await ctx.send("Attempting to force Epic Games update... This will trigger on the next minute interval.")
            logger.info("Force Epic Games update initiated by admin.")
            await self._send_admin_dm("Force epic update initiated.")
        else:
            await ctx.send("You do not have permission to use this command, or it must be used in DMs.")


    @listen()
    async def on_startup(self):
        self.send_epic_free_games.start()
        logger.info("--Epic Games Task Started")

def setup(bot):  # Remove type annotation to avoid Extension constructor conflict
    free_epicgames(bot)
