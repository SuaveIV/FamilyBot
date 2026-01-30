from interactions import Extension, Task, listen, GuildText, CronTrigger

from familybot.config import (
    NEW_GAME_CHANNEL_ID,
    WISHLIST_CHANNEL_ID,
)
from familybot.lib.logging_config import get_logger
from familybot.lib.types import FamilyBotClient
from familybot.lib.steam_helpers import send_admin_dm

logger = get_logger(__name__)


class steam_tasks(Extension):
    def __init__(self, bot: FamilyBotClient):
        self.bot: FamilyBotClient = bot

    @Task.create(CronTrigger("15 * * * *"))  # Every hour at :15
    async def new_game_task(self):
        """Background task to check for new games - runs at :15 past each hour."""
        logger.info("Running scheduled new game task (hourly at :15)...")
        try:
            from familybot.lib.plugin_admin_actions import check_new_game_action

            result = await check_new_game_action()  # Uses cache
            if result["success"] and "New games detected" in result["message"]:
                # Only send to channel if new games were actually found
                await self.bot.send_to_channel(
                    NEW_GAME_CHANNEL_ID, result["message"]
                )  # ignore
                logger.info("New game task: Posted new games to channel")
            else:
                logger.info(f"New game task result: {result['message']}")
        except Exception as e:
            logger.error(f"Error in new game task: {e}", exc_info=True)
            await send_admin_dm(self.bot, f"New game task error: {e}")

    @Task.create(CronTrigger("45 0,6,12,18 * * *"))  # Every 6 hours at :45
    async def wishlist_task(self):
        """Background task to refresh wishlist - runs at :45 of hours 0, 6, 12, 18."""
        logger.info("Running scheduled wishlist task (every 6 hours at :45)...")
        try:
            from familybot.lib.plugin_admin_actions import check_wishlist_action

            result = await check_wishlist_action()  # Uses cache for wishlists
            if result["success"] and "Details:" in result["message"]:
                # Only update channel if there are actual results
                wishlist_channel = await self.bot.fetch_channel(WISHLIST_CHANNEL_ID)
                if wishlist_channel and isinstance(wishlist_channel, GuildText):
                    pinned_messages = await wishlist_channel.fetch_pinned_messages()
                    if pinned_messages:
                        # Extract just the wishlist content from the result message
                        content_start = result["message"].find("Details:\n") + len(
                            "Details:\n"
                        )
                        wishlist_content = result["message"][content_start:]
                        await pinned_messages[-1].edit(content=wishlist_content)
                        logger.info("Wishlist task: Updated pinned message")
            else:
                logger.info(f"Wishlist task result: {result['message']}")
        except Exception as e:
            logger.error(f"Error in wishlist task: {e}", exc_info=True)
            await send_admin_dm(self.bot, f"Wishlist task error: {e}")

    @listen()
    async def on_startup(self):
        """Start background tasks when the bot starts."""
        self.new_game_task.start()
        self.wishlist_task.start()
        logger.info("--Steam Family background tasks started (scheduled timing)")
        logger.info("  - New games: Every hour at :15")
        logger.info("  - Wishlist: Every 6 hours at :45 (00:45, 06:45, 12:45, 18:45)")


def setup(bot):
    steam_tasks(bot)
