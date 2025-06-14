# In src/familybot/plugins/help_message.py

# Explicitly import what's needed from interactions
from interactions import Extension, listen
from string import Template
import os
import logging
from datetime import datetime # For admin DM timestamp
from familybot.config import HELP_CHANNEL_ID, ADMIN_DISCORD_ID, PLUGIN_PATH
from familybot.lib.types import FamilyBotClient

# Setup logging for this specific module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class help_message(Extension):
    def __init__(self, bot: FamilyBotClient):
        self.bot: FamilyBotClient = bot  # Explicit type annotation for the bot attribute
        logger.info("Help Message Plugin loaded")

    async def _send_admin_dm(self, message: str) -> None:
        """Helper to send error/warning messages to the bot admin via DM."""
        try:
            admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
            if admin_user:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await admin_user.send(f"Help Message Plugin Error ({now_str}): {message}")
        except Exception as e:
            logger.error(f"Failed to send DM to admin {ADMIN_DISCORD_ID}: {e}")

    async def write_help(self):
        """Generates, sends, and pins/edits the help message in the designated channel."""
        help_channel = None
        try:
            help_channel = await self.bot.fetch_channel(HELP_CHANNEL_ID)
            if not help_channel:
                logger.error(f"Help channel not found for ID: {HELP_CHANNEL_ID}. Check config.yml.")
                await self._send_admin_dm(f"Help channel not found for ID: {HELP_CHANNEL_ID}.")
                return
        except Exception as e:
            logger.error(f"Error fetching help channel (ID: {HELP_CHANNEL_ID}): {e}")
            await self._send_admin_dm(f"Error fetching help channel: {e}")
            return

        pinned_messages = []
        try:
            if hasattr(help_channel, 'fetch_pinned_messages'):
                pinned_messages = await help_channel.fetch_pinned_messages()  # type: ignore
        except Exception as e:
            logger.error(f"Error fetching pinned messages from channel {HELP_CHANNEL_ID}: {e}")
            await self._send_admin_dm(f"Error fetching pinned messages: {e}")

        full_help_message = "# __🤖 Bot Command Usage__ \n"
        command_template = Template("""
### `!${name}`
*${description}*
**Usage:** `${usage}`
*${comment}*
""")

        plugin_files = []
        try:
            plugin_files = os.listdir(PLUGIN_PATH)
            if not plugin_files:
                logger.warning(f"No plugin files found in {PLUGIN_PATH}. Help message will be empty.")
        except FileNotFoundError:
            logger.error(f"Plugin directory not found: {PLUGIN_PATH}. Cannot generate help message.")
            await self._send_admin_dm(f"Plugin directory not found: {PLUGIN_PATH}")
            return
        except Exception as e:
            logger.error(f"Error listing plugin directory {PLUGIN_PATH}: {e}")
            await self._send_admin_dm(f"Error listing plugin directory: {e}")
            return

        plugin_files.sort() # Sort plugin files for consistent help message order

        for file_name in plugin_files:
            if file_name.endswith(".py") and not file_name.startswith("__"):
                file_path = os.path.join(PLUGIN_PATH, file_name)
                commands_in_file = []
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("[help]") and "if \"[help]\"" not in line and "if '[help]'" not in line:
                                parts = line.split("|")
                                if len(parts) == 5:
                                    data = {
                                        'name' : parts[1].strip(),
                                        'description' : parts[2].strip(),
                                        'usage' : parts[3].strip(),
                                        'comment' : parts[4].strip()
                                    }
                                    commands_in_file.append(data)
                                else:
                                    logger.warning(f"Malformed help line in {file_name}: '{line}' (Expected 5 parts, got {len(parts)})")
                                    await self._send_admin_dm(f"Malformed help line in {file_name}: {line}")
                except FileNotFoundError:
                    logger.error(f"Plugin file not found: {file_path}")
                    await self._send_admin_dm(f"Error generating help: {file_name} not found.")
                except Exception as e:
                    logger.error(f"Error reading plugin file {file_name}: {e}", exc_info=True)
                    await self._send_admin_dm(f"Error reading plugin file {file_name}: {e}")

                if commands_in_file:
                    full_help_message += f"\n## __📚 {file_name.replace('.py', '').replace('_', ' ').title()} Commands__\n"
                    for cmd_data in commands_in_file:
                        full_help_message += command_template.substitute(cmd_data)

        if len(full_help_message) > 1950:
            logger.warning(f"Generated help message is very long ({len(full_help_message)} chars). It might be truncated by Discord.")
            full_help_message = full_help_message[:1950] + "\n... (Message too long, truncated)"
            await self._send_admin_dm("Help message truncated due to Discord's character limit.")

        try:
            if not pinned_messages:
                if hasattr(help_channel, 'send'):
                    help_message_obj = await help_channel.send(full_help_message)  # type: ignore
                    await help_message_obj.pin()
                    logger.info(f"New help message pinned in channel {HELP_CHANNEL_ID}")
                else:
                    logger.error(f"Channel {HELP_CHANNEL_ID} does not support sending messages")
                    await self._send_admin_dm(f"Channel {HELP_CHANNEL_ID} does not support sending messages")
            else:
                await pinned_messages[-1].edit(content=full_help_message)
                logger.info(f"Help message updated in channel {HELP_CHANNEL_ID}")
        except Exception as e:
            logger.error(f"Error sending/editing/pinning help message in channel {HELP_CHANNEL_ID}: {e}", exc_info=True)
            await self._send_admin_dm(f"Error with help message (send/edit/pin): {e}")

    @listen()
    async def on_startup(self):
        await self.write_help()
        logger.info("--Help Message created/modified")

def setup(bot):  # Remove type annotation to avoid Extension constructor conflict
    help_message(bot)
