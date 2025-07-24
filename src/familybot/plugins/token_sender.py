# In src/familybot/plugins/token_sender.py

import base64
import binascii
import json
import logging
import os
from datetime import datetime

from interactions import Extension, IntervalTrigger, Task, listen
from interactions.ext.prefixed_commands import (PrefixedContext,
                                                prefixed_command)

# Import from config
from familybot.config import (ADMIN_DISCORD_ID, BROWSER_PROFILE_PATH,
                              PROJECT_ROOT, TOKEN_SAVE_PATH,
                              UPDATE_BUFFER_HOURS)
from familybot.lib.logging_config import get_logger
from familybot.lib.types import FamilyBotClient

# Import Playwright conditionally
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.error("Playwright not installed. Please install with: uv add playwright")

# Setup enhanced logging for this specific module
logger = get_logger(__name__)

class token_sender(Extension):
    def __init__(self, bot: FamilyBotClient):
        self.bot: FamilyBotClient = bot
        logger.info("Token Sender Plugin loaded")
        self._force_next_run = False
        self._last_checked_day = -1

        # Check if Playwright is available
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright is not available. Token sender plugin will not function properly.")
            logger.error("Please install Playwright with: uv add playwright && uv run playwright install chromium")

        # Ensure the token save path directory exists
        self.actual_token_save_dir = os.path.join(PROJECT_ROOT, TOKEN_SAVE_PATH)
        try:
            os.makedirs(self.actual_token_save_dir, exist_ok=True)
            logger.info(f"Ensured token save directory exists: {self.actual_token_save_dir}")
        except Exception as e:
            logger.critical(f"Failed to create token save directory {self.actual_token_save_dir}: {e}")

    async def _send_admin_dm(self, message: str) -> None:
        """Helper to send error/warning messages to the bot admin via DM."""
        try:
            admin_user = await self.bot.fetch_user(int(ADMIN_DISCORD_ID))
            if admin_user:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await admin_user.send(f"Token Sender Plugin ({now_str}): {message}")
        except Exception as e:
            logger.error(f"Failed to send DM to admin {ADMIN_DISCORD_ID}: {e}")

    async def _get_token_with_playwright(self) -> str:
        """Extract Steam webapi_token using Playwright."""
        logger.info("Starting token extraction using Playwright...")

        async with async_playwright() as p:
            # Launch browser with profile if specified
            if BROWSER_PROFILE_PATH and os.path.exists(BROWSER_PROFILE_PATH):
                logger.info(f"Using browser profile: {BROWSER_PROFILE_PATH}")

                # Check if storage state file exists for better session persistence
                storage_state_path = os.path.join(BROWSER_PROFILE_PATH, "storage_state.json")
                storage_state = None

                if os.path.exists(storage_state_path):
                    try:
                        with open(storage_state_path, 'r') as f:
                            storage_state = json.load(f)
                        logger.info("Loaded storage state for session persistence")
                    except Exception as e:
                        logger.warning(f"Could not load storage state: {e}")

                # Launch with persistent context (storage state is automatically loaded from user_data_dir)
                browser = await p.chromium.launch_persistent_context(
                    user_data_dir=BROWSER_PROFILE_PATH,
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage']
                )
                page = await browser.new_page()

                # If we have storage state, apply it to the context
                if storage_state:
                    try:
                        await browser.add_cookies(storage_state.get('cookies', []))
                        logger.info("Applied cookies from storage state")
                    except Exception as e:
                        logger.warning(f"Could not apply storage state cookies: {e}")
            else:
                logger.info("Using default browser profile")
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

            try:
                # Navigate to Steam points summary page
                await page.goto("https://store.steampowered.com/pointssummary/ajaxgetasyncconfig")
                await page.wait_for_load_state('networkidle')

                # Get page content
                content = await page.content()

                # Try to click rawdata-tab if it exists
                try:
                    rawdata_tab = page.locator("#rawdata-tab")
                    if await rawdata_tab.count() > 0:
                        await rawdata_tab.click()
                        await page.wait_for_timeout(1000)  # Wait 1 second
                        content = await page.content()
                except Exception as e:
                    logger.warning(f"Could not click rawdata-tab: {e}")

                # Extract token from page content
                start_token_marker = '"webapi_token":"'
                end_token_marker = '"}'

                start_index = content.find(start_token_marker)
                if start_index == -1:
                    raise ValueError("Could not find 'webapi_token' start marker in page source")

                key_start = start_index + len(start_token_marker)
                key_end = content.find(end_token_marker, key_start)
                if key_end == -1:
                    raise ValueError("Could not find 'webapi_token' end marker in page source")

                extracted_key = content[key_start:key_end]

                if not extracted_key:
                    raise ValueError("Extracted token is empty")

                logger.info(f"Successfully extracted token: {extracted_key[:20]}...")
                return extracted_key

            finally:
                await browser.close()

    async def _process_token(self, token: str) -> bool:
        """Process and save the token, return True if token was updated."""
        try:
            # Read existing token for comparison
            token_file_path = os.path.join(self.actual_token_save_dir, "token")
            saved_token = ""
            try:
                with open(token_file_path, 'r') as token_file:
                    saved_token = token_file.readline().strip()
            except FileNotFoundError:
                logger.info(f"Existing token file not found at {token_file_path}. Will create new.")

            # Check if token has changed
            if saved_token == token:
                logger.info("Token has not changed. No update needed.")
                return False

            logger.info("New token found! Processing and saving...")

            # Save new token
            with open(token_file_path, 'w') as token_file:
                token_file.write(token)

            # Decode token to get expiry time
            try:
                coded_string = token.split('.')[1]
                # Pad and replace URL-safe chars for base64 decoding
                padded_coded_string = coded_string.replace('-', '+').replace('_', '/')
                padded_coded_string += '=' * (-len(padded_coded_string) % 4)

                key_info = json.loads(base64.b64decode(padded_coded_string).decode('utf-8'))
                exp_timestamp = key_info['exp']

                # Save expiry time
                exp_file_path = os.path.join(self.actual_token_save_dir, "token_exp")
                with open(exp_file_path, "w") as exp_time_file:
                    exp_time_file.write(str(exp_timestamp))

                logger.info(f"Token expiration timestamp {exp_timestamp} saved.")
                logger.info(f"Token expires at: {datetime.fromtimestamp(exp_timestamp).strftime('%Y-%m-%d %H:%M:%S')}")

                # Token saved successfully - no additional token manager needed
                # since this plugin handles token management directly

                return True

            except (IndexError, json.JSONDecodeError, binascii.Error) as e:
                logger.error(f"Error decoding token: {e}")
                await self._send_admin_dm(f"Error decoding new token: {e}")
                return False

        except Exception as e:
            logger.error(f"Error processing token: {e}")
            await self._send_admin_dm(f"Error processing token: {e}")
            return False

    @Task.create(IntervalTrigger(hours=1))  # Check every hour
    async def token_update_scheduler(self) -> None:
        """Scheduled task to check and update Steam tokens."""
        try:
            # Check if we should run (forced or based on token expiry)
            should_run = self._force_next_run

            if not should_run:
                # Check token expiry
                exp_file_path = os.path.join(self.actual_token_save_dir, "token_exp")
                try:
                    with open(exp_file_path, "r") as exp_time_file:
                        exp_time_str = exp_time_file.readline().strip()
                        if exp_time_str:
                            exp_time = float(exp_time_str)
                            # Calculate if we should update (buffer hours before expiry)
                            buffer_seconds = UPDATE_BUFFER_HOURS * 3600
                            update_time = datetime.fromtimestamp(exp_time - buffer_seconds)
                            now = datetime.now()

                            if now >= update_time:
                                should_run = True
                                logger.info(f"Token update needed. Current: {now.strftime('%Y-%m-%d %H:%M:%S')}, Update time: {update_time.strftime('%Y-%m-%d %H:%M:%S')}")
                            else:
                                logger.debug(f"Token update not needed yet. Next update: {update_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        else:
                            should_run = True  # No expiry time, force update
                            logger.info("No token expiry time found, forcing update")
                except FileNotFoundError:
                    should_run = True  # No token file, force update
                    logger.info("No token expiry file found, forcing update")
                except Exception as e:
                    logger.error(f"Error reading token expiry: {e}")
                    should_run = True  # Error reading, force update

            if should_run:
                if not PLAYWRIGHT_AVAILABLE:
                    logger.error("Cannot update token: Playwright is not available")
                    await self._send_admin_dm("Cannot update Steam token: Playwright is not installed")
                    self._force_next_run = False
                    return

                logger.info("Starting token update process...")
                try:
                    token = await self._get_token_with_playwright()
                    updated = await self._process_token(token)

                    if updated:
                        logger.info("Token successfully updated")
                        await self._send_admin_dm("Steam token successfully updated")
                    else:
                        logger.info("Token check completed, no update needed")

                except Exception as e:
                    logger.error(f"Error during token update: {e}")
                    await self._send_admin_dm(f"Error updating Steam token: {e}")
                finally:
                    self._force_next_run = False

        except Exception as e:
            logger.critical(f"Critical error in token_update_scheduler: {e}", exc_info=True)
            await self._send_admin_dm(f"Critical error in token scheduler: {e}")

    """
    [help]|force_token|Force Steam token update|!force_token|Admin only command to force token update
    """
    @prefixed_command(name="force_token")
    async def force_token_command(self, ctx: PrefixedContext):
        """Force Steam token update (admin only, DM only)."""
        if str(ctx.author_id) == str(ADMIN_DISCORD_ID) and ctx.guild is None:
            self._force_next_run = True
            await ctx.send("🔄 Forcing Steam token update... This will trigger on the next scheduled check.")
            logger.info("Force token update initiated by admin.")
            await self._send_admin_dm("Force token update initiated.")
        else:
            await ctx.send("❌ You do not have permission to use this command, or it must be used in DMs.")

    """
    [help]|token_status|Check Steam token status|!token_status|Admin only command to check token status
    """
    @prefixed_command(name="token_status")
    async def token_status_command(self, ctx: PrefixedContext):
        """Check Steam token status (admin only, DM only)."""
        if str(ctx.author_id) == str(ADMIN_DISCORD_ID) and ctx.guild is None:
            try:
                token_file_path = os.path.join(self.actual_token_save_dir, "token")
                exp_file_path = os.path.join(self.actual_token_save_dir, "token_exp")

                # Check if token exists
                if not os.path.exists(token_file_path):
                    await ctx.send("❌ No Steam token found.")
                    return

                # Read token info
                with open(token_file_path, 'r') as f:
                    token = f.read().strip()

                if os.path.exists(exp_file_path):
                    with open(exp_file_path, 'r') as f:
                        exp_timestamp = float(f.read().strip())

                    exp_time = datetime.fromtimestamp(exp_timestamp)
                    now = datetime.now()
                    time_remaining = exp_time - now

                    status_msg = "🔑 **Steam Token Status**\n"
                    status_msg += f"📅 Expires: {exp_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
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
                logger.error(f"Error checking token status: {e}")
                await ctx.send(f"❌ Error checking token status: {e}")
        else:
            await ctx.send("❌ You do not have permission to use this command, or it must be used in DMs.")

    @listen()
    async def on_startup(self):
        """Start the token update scheduler when the bot starts."""
        self.token_update_scheduler.start()
        logger.info("--Token Sender Task Started")

def setup(bot):
    """Setup function to register the plugin with the bot."""
    token_sender(bot)
