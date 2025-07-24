# In src/familybot/plugins/help_message.py

# Explicitly import what's needed from interactions
import os
from datetime import datetime  # For admin DM timestamp
from string import Template

from interactions import Extension, listen

from familybot.config import ADMIN_DISCORD_ID, HELP_CHANNEL_ID, PLUGIN_PATH
from familybot.lib.logging_config import get_logger
from familybot.lib.types import FamilyBotClient
from familybot.lib.utils import truncate_message_list

# Setup enhanced logging for this specific module
logger = get_logger(__name__)

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

        header = "# __🤖 Bot Command Usage__ \n"
        command_template = Template("""
### `${name}`
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

        # Build command sections as separate items for better truncation control
        command_sections = []

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
                                    # Fix the !! issue by cleaning the name field
                                    name = parts[1].strip()
                                    if name.startswith("!"):
                                        name = name[1:]  # Remove the leading !

                                    data = {
                                        'name' : name,
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
                    section_content = f"\n## __📚 {file_name.replace('.py', '').replace('_', ' ').title()} Commands__\n"
                    for cmd_data in commands_in_file:
                        section_content += command_template.substitute(cmd_data)
                    command_sections.append(section_content)

        # Use utility function to handle message truncation
        footer_template = "\n... and {count} more command sections!"
        full_help_message = truncate_message_list(command_sections, header, footer_template)

        try:
            if not pinned_messages:
                # Use centralized send_to_channel function which handles message splitting
                await self.bot.send_to_channel(HELP_CHANNEL_ID, full_help_message)

                # Get the channel to pin the message
                if help_channel and hasattr(help_channel, 'fetch_message'):
                    # Get the last message in the channel (should be our help message)
                    try:
                        messages = await help_channel.history(limit=1).flatten()  # type: ignore
                        if messages:
                            await messages[0].pin()
                            logger.info(f"New help message pinned in channel {HELP_CHANNEL_ID}")
                    except Exception as pin_error:
                        logger.warning(f"Could not pin help message: {pin_error}")
                        await self._send_admin_dm(f"Help message sent but could not pin: {pin_error}")
                else:
                    logger.info(f"Help message sent to channel {HELP_CHANNEL_ID}")
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
