from datetime import datetime

from familybot.config import ADMIN_DISCORD_ID
from familybot.lib.logging_config import get_logger
from familybot.lib.types import FamilyBotClient

logger = get_logger(__name__)

async def send_admin_dm(bot: FamilyBotClient, message: str) -> None:
    """Helper to send error/warning messages to the bot admin via DM."""
    try:
        admin_user = await bot.fetch_user(ADMIN_DISCORD_ID)
        if admin_user is not None:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await admin_user.send(
                f"Steam Family Plugin Error ({now_str}): {message}"
            )
        else:
            logger.error(
                f"Admin user with ID {ADMIN_DISCORD_ID} not found or could not be fetched. Cannot send DM."
            )
    except Exception as e:
        logger.error(
            f"Failed to send DM to admin {ADMIN_DISCORD_ID} (after initial fetch attempt): {e}"
        )
