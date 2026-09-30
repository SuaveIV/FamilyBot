"""Token sender Discord plugin for automatic and manual Steam token management."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from interactions import Extension, IntervalTrigger, Task, listen
from interactions.ext.prefixed_commands import PrefixedContext, prefixed_command

from familybot.config import (
    ADMIN_DISCORD_ID,
    BROWSER_PROFILE_PATH,
    PROJECT_ROOT,
    TOKEN_SAVE_PATH,
    UPDATE_BUFFER_HOURS,
)
from familybot.lib.logging_config import get_logger
from familybot.lib.token_service import (
    CAMOUFOX_AVAILABLE,
    acquire_fresh_token,
    save_token_files,
)

if TYPE_CHECKING:
    from familybot.lib.types import FamilyBotClient

logger = get_logger(__name__)


class token_sender(Extension):  # noqa: N801
    """Extension to schedule and manage Steam Web API tokens."""

    def __init__(self, bot: FamilyBotClient) -> None:
        """Initialize the Token Sender extension."""
        self.bot: FamilyBotClient = bot
        logger.info("Token Sender Plugin loaded")
        self._force_next_run = False
        self._last_checked_day = -1

        if not CAMOUFOX_AVAILABLE:
            logger.info(
                "Camoufox not installed. Token sender running in HTTP mode with stored credentials."
            )

        # Ensure the token save path directory exists
        base_dir = Path(TOKEN_SAVE_PATH) if TOKEN_SAVE_PATH else Path("tokens")
        self.actual_token_save_dir = (
            base_dir if base_dir.is_absolute() else Path(PROJECT_ROOT) / base_dir
        )
        try:
            self.actual_token_save_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Ensured token save directory exists: %s", self.actual_token_save_dir)
        except OSError as e:
            logger.critical(
                "Failed to create token save directory %s: %s", self.actual_token_save_dir, e
            )

    async def _send_admin_dm(self, message: str) -> None:
        """Send error/warning messages to the bot admin via DM."""
        try:
            admin_user = await self.bot.fetch_user(int(ADMIN_DISCORD_ID))
            if admin_user:
                now_str = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
                await admin_user.send(f"Token Sender Plugin ({now_str}): {message}")
        except Exception as e:
            logger.error("Failed to send DM to admin %s: %s", ADMIN_DISCORD_ID, e)

    async def _get_token(self) -> tuple[str, str]:
        """Acquire a fresh Steam webapi_token using HTTP first, with browser fallback."""
        return await acquire_fresh_token(
            profile_path=BROWSER_PROFILE_PATH,
            token_dir=self.actual_token_save_dir,
            prefer_http=True,
        )

    async def _get_token_with_camoufox(self) -> str:
        """Acquire token with browser extraction for backwards compatibility."""
        token, _ = await acquire_fresh_token(
            profile_path=BROWSER_PROFILE_PATH,
            token_dir=self.actual_token_save_dir,
            prefer_http=False,
        )
        return token

    async def _process_token(self, token: str) -> bool:
        """Process and save the token, return True if token was updated."""
        try:
            changed, exp_timestamp = save_token_files(token, self.actual_token_save_dir)
            if changed:
                exp_dt = datetime.fromtimestamp(exp_timestamp, tz=UTC)
                logger.info("Token successfully updated (expires: %s)", exp_dt)
            else:
                logger.info("Token has not changed. No update needed.")
            return changed
        except Exception as e:
            logger.error("Error processing token: %s", e)
            await self._send_admin_dm(f"Error processing token: {e}")
            return False

    def _should_update_token(self) -> bool:
        """Determine if an automatic token refresh is required."""
        if self._force_next_run:
            return True

        exp_file_path = self.actual_token_save_dir / "token_exp"
        if not exp_file_path.is_file():
            logger.info("No token expiry file found, forcing update")
            return True

        try:
            exp_time_str = exp_file_path.read_text(encoding="utf-8").strip()
            if not exp_time_str:
                logger.info("Token expiry file is empty, forcing update")
                return True

            exp_time = float(exp_time_str)
            buffer_seconds = UPDATE_BUFFER_HOURS * 3600
            update_time = datetime.fromtimestamp(exp_time - buffer_seconds, tz=UTC)
            now = datetime.now(tz=UTC)

            if now >= update_time:
                logger.info(
                    "Token update needed. Current: %s, Update time: %s",
                    now.strftime("%Y-%m-%d %H:%M:%S"),
                    update_time.strftime("%Y-%m-%d %H:%M:%S"),
                )
                return True

            logger.debug(
                "Token update not needed yet. Next update: %s",
                update_time.strftime("%Y-%m-%d %H:%M:%S"),
            )
            return False

        except (ValueError, OSError) as e:
            logger.error("Error reading token expiry: %s", e)
            return True

    @Task.create(IntervalTrigger(hours=1))
    async def token_update_scheduler(self) -> None:
        """Schedule hourly task to check and update Steam tokens."""
        try:
            if not self._should_update_token():
                return

            logger.info("Starting token update process...")
            try:
                token, method = await self._get_token()
                updated = await self._process_token(token)

                if updated:
                    logger.info("Token successfully updated via %s", method)
                    await self._send_admin_dm(f"Steam token successfully updated ({method})")
                else:
                    logger.info("Token check completed via %s, no update needed", method)

            except Exception as e:
                logger.error("Error during token update: %s", e)
                await self._send_admin_dm(f"Error updating Steam token: {e}")
            finally:
                self._force_next_run = False

        except Exception as e:
            logger.critical("Critical error in token_update_scheduler: %s", e, exc_info=True)
            await self._send_admin_dm(f"Critical error in token scheduler: {e}")

    """
    [help]|force_token|Force Steam token update|!force_token|Admin command to force token update
    """

    @prefixed_command(name="force_token")
    async def force_token_command(self, ctx: PrefixedContext) -> None:
        """Force Steam token update (admin only, DM only)."""
        if str(ctx.author_id) == str(ADMIN_DISCORD_ID) and ctx.guild is None:
            self._force_next_run = True
            await ctx.send(
                "🔄 Forcing Steam token update... This will trigger on the next scheduled check."
            )
            logger.info("Force token update initiated by admin.")
            await self._send_admin_dm("Force token update initiated.")
        else:
            await ctx.send(
                "❌ You do not have permission to use this command, or it must be used in DMs."
            )

    """
    [help]|token_status|Check Steam token status|!token_status|Admin command to check token status
    """

    @prefixed_command(name="token_status")
    async def token_status_command(self, ctx: PrefixedContext) -> None:
        """Check Steam token status (admin only, DM only)."""
        if str(ctx.author_id) != str(ADMIN_DISCORD_ID) or ctx.guild is not None:
            await ctx.send(
                "❌ You do not have permission to use this command, or it must be used in DMs."
            )
            return

        try:
            token_file_path = self.actual_token_save_dir / "token"
            exp_file_path = self.actual_token_save_dir / "token_exp"

            if not token_file_path.is_file():
                await ctx.send("❌ No Steam token found.")
                return

            token = token_file_path.read_text(encoding="utf-8").strip()

            if exp_file_path.is_file():
                exp_timestamp = float(exp_file_path.read_text(encoding="utf-8").strip())
                exp_time = datetime.fromtimestamp(exp_timestamp, tz=UTC)
                now = datetime.now(tz=UTC)
                time_remaining = exp_time - now

                status_msg = "🔑 **Steam Token Status**\n"
                status_msg += f"📅 Expires: {exp_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                status_msg += f"⏰ Time remaining: {str(time_remaining).split('.')[0]}\n"
                status_msg += f"🔢 Token preview: {token[:20]}...\n"

                if time_remaining.total_seconds() < 0:
                    status_msg += "⚠️ **Token has expired!**"
                elif time_remaining.total_seconds() < UPDATE_BUFFER_HOURS * 3600:
                    status_msg += "🟡 **Token will be updated soon**"
                else:
                    status_msg += "✅ **Token is valid**"
            else:
                status_msg = "🔑 **Steam Token Status**\n"
                status_msg += f"🔢 Token preview: {token[:20]}...\n"
                status_msg += "⚠️ No expiration info found"

            await ctx.send(status_msg)

        except Exception as e:
            logger.error("Error checking token status: %s", e)
            await ctx.send(f"❌ Error checking token status: {e}")

    @listen()
    async def on_startup(self) -> None:
        """Start the token update scheduler when the bot starts."""
        self.token_update_scheduler.start()
        logger.info("--Token Sender Task Started")


def setup(bot: FamilyBotClient) -> None:
    """Register the token_sender extension with the bot."""
    token_sender(bot)
