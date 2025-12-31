import asyncio
from interactions import Extension, Task, IntervalTrigger, listen
from interactions.ext.prefixed_commands import prefixed_command, PrefixedContext

from familybot.config import ADMIN_DISCORD_ID
from familybot.lib.backup_manager import backup_database
from familybot.lib.types import FamilyBotClient
from familybot.lib.logging_config import get_logger

logger = get_logger(__name__)


class Maintenance(Extension):
    def __init__(self, bot: FamilyBotClient):
        self.bot: FamilyBotClient = bot

    @Task.create(IntervalTrigger(days=7))
    async def weekly_backup_task(self):
        """Runs the database backup every 7 days."""
        logger.info("Starting scheduled weekly database backup...")
        # Run blocking I/O in a separate thread
        success = await asyncio.to_thread(backup_database)

        if success:
            logger.info("Weekly database backup completed successfully.")
            await self.bot.send_log_dm(
                "✅ Weekly database backup completed successfully."
            )
        else:
            logger.error("Weekly database backup failed.")
            await self.bot.send_log_dm("❌ Weekly database backup failed. Check logs.")

    @listen()
    async def on_startup(self):
        """Start maintenance tasks on bot startup."""
        self.weekly_backup_task.start()
        logger.info("Maintenance tasks started (Weekly Backup).")

    @prefixed_command(name="backup")
    async def backup_command(self, ctx: PrefixedContext):
        """Manually trigger a database backup (Admin only)."""
        if str(ctx.author.id) != str(ADMIN_DISCORD_ID):
            return

        await ctx.send("⏳ Starting database backup...")
        success = await asyncio.to_thread(backup_database)

        if success:
            await ctx.send("✅ Database backup completed successfully.")
        else:
            await ctx.send("❌ Database backup failed. Check logs.")


def setup(bot: FamilyBotClient):
    Maintenance(bot)
