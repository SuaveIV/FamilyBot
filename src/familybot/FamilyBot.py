# In src/familybot/FamilyBot.py

# Import necessary libraries
import os
import asyncio
import signal
import sys
import logging # Import logging module here for main setup
from datetime import datetime
from typing import cast, TYPE_CHECKING
from interactions import Client, Intents, listen, GuildText, BaseChannel, Message # Ensure Client and listen are imported
from interactions.ext import prefixed_commands

if TYPE_CHECKING:
    from interactions import User

# Import modules from your project's new package structure
from familybot.config import DISCORD_API_KEY, ADMIN_DISCORD_ID
from familybot.WebSocketServer import start_websocket_server_task # Import the async server task
from familybot.lib.database import init_db # <<< Import init_db
from familybot.lib.types import FamilyBotClient # Import the protocol type


# Setup global logging for the entire bot (this will be the root logger)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Logger for this main script

# --- Client Setup ---
client = Client(token=DISCORD_API_KEY, intents=Intents.ALL)
prefixed_commands.setup(client, default_prefix="!")

# List to keep track of background tasks for graceful shutdown
_running_tasks = []

# --- Plugin Loading ---
def get_plugins(directory: str) -> list:
    plugin_list = []
    dir_name = os.path.basename(os.path.normpath(directory)) # Get directory name without trailing slash
    try:
        for file_name in os.listdir(directory):
            if file_name.endswith(".py") and not file_name.startswith("__"): # Exclude __init__.py
                plugin_name = f"familybot.plugins.{file_name[:-3]}" # Correct import path
                plugin_list.append(plugin_name)
        return plugin_list
    except FileNotFoundError:
        logger.error(f"Plugin directory not found: {directory}")
        return []
    except Exception as e:
        logger.error(f"Error listing plugin directory: {e}")
        return []

plugin_list = get_plugins(os.path.join(os.path.dirname(__file__), 'plugins')) # Point to src/familybot/plugins/
if plugin_list:
    for plugin in plugin_list:
        try:
            client.load_extension(plugin)
            logger.info(f"Loaded plugin: {plugin}")
        except Exception as e:
            logger.error(f"Failed to load plugin {plugin}: {e}", exc_info=True)
else:
    logger.warning("No plugins found to load.")


# --- Global Utility Functions for Bot Instance ---
# These are exposed as methods of the client instance for convenience in plugins
async def send_to_channel(channel_id: int, message: str) -> None:
    try:
        channel = await client.fetch_channel(channel_id)
        # Type guard to check if channel supports sending messages
        if channel and isinstance(channel, GuildText):
            await channel.send(message)
        elif channel and hasattr(channel, 'send'):
            # Fallback for other sendable channel types
            await channel.send(message)  # type: ignore
        else:
            logger.warning(f"Could not find channel with ID: {channel_id} or channel doesn't support sending messages")
    except Exception as e:
        logger.error(f"Error sending message to channel {channel_id}: {e}")

async def send_log_dm(message: str) -> None:
    try:
        user = await client.fetch_user(ADMIN_DISCORD_ID)
        if user:
            now = datetime.now().strftime("%d/%m/%y %H:%M:%S")
            await user.send(f"{now} -> {message}")
    except Exception as e:
        logger.error(f"Error sending log DM to admin {ADMIN_DISCORD_ID}: {e}")

async def send_dm(discord_id: int, message: str) -> None:
    try:
        user = await client.fetch_user(discord_id)
        if user:
            await user.send(message)
    except Exception as e:
        logger.error(f"Error sending DM to user {discord_id}: {e}")

async def edit_msg(chan_id: int, msg_id: int, message: str) -> None:
    try:
        channel = client.get_channel(chan_id)
        # Type guard to check if channel supports message operations
        if channel and isinstance(channel, GuildText):
            msg = await channel.fetch_message(msg_id)
            if msg:
                await msg.edit(content=message)
            else:
                logger.warning(f"Message {msg_id} not found in channel {chan_id} for editing.")
        elif channel and hasattr(channel, 'fetch_message'):
            # Fallback for other channel types that support message fetching
            msg = await channel.fetch_message(msg_id)  # type: ignore
            if msg:
                await msg.edit(content=message)
            else:
                logger.warning(f"Message {msg_id} not found in channel {chan_id} for editing.")
        else:
            logger.warning(f"Channel {chan_id} not found for editing message {msg_id} or channel doesn't support message fetching.")
    except Exception as e:
        logger.error(f"Error editing message {msg_id} in channel {chan_id}: {e}")

async def get_pinned_message(chan_id: int) -> list:
    try:
        channel = client.get_channel(chan_id)
        # Type guard to check if channel supports pinned messages
        if channel and isinstance(channel, GuildText):
            pinned_messages = await channel.fetch_pinned_messages()
            return pinned_messages
        elif channel and hasattr(channel, 'fetch_pinned_messages'):
            # Fallback for other channel types that support pinned messages
            pinned_messages = await channel.fetch_pinned_messages()  # type: ignore
            return pinned_messages
        else:
            logger.warning(f"Channel {chan_id} not found for fetching pinned messages or channel doesn't support pinned messages.")
            return []
    except Exception as e:
        logger.error(f"Error fetching pinned messages from channel {chan_id}: {e}")
        return []

# Cast client to our protocol type and assign methods
typed_client = cast(FamilyBotClient, client)
typed_client.send_to_channel = send_to_channel
typed_client.send_log_dm = send_log_dm
typed_client.send_dm = send_dm
typed_client.edit_msg = edit_msg
typed_client.get_pinned_message = get_pinned_message

# Update the global client reference to use the typed version
client = typed_client


# --- Event Listeners and Background Tasks ---
@listen()
async def on_startup():
    logger.info("Bot is ready! Starting background tasks...")
    # Initialize the database
    try:
        init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}", exc_info=True)
        await send_log_dm(f"CRITICAL ERROR: Database failed to initialize: {e}")
        # Consider exiting if database is critical for bot function
        sys.exit(1)

    # Start the WebSocket server as an asyncio task
    ws_server_task = asyncio.create_task(start_websocket_server_task())
    _running_tasks.append(ws_server_task)
    logger.info("WebSocket server task scheduled.")
    await send_log_dm("Bot ready")
    
@listen()
async def on_disconnect():
    logger.info("Bot disconnected. Initiating graceful shutdown of background tasks.")
    for task in _running_tasks:
        if not task.done():
            task.cancel()
            logger.info(f"Task {task.get_name() if task.get_name() else task} cancelled.")
    try:
        await asyncio.gather(*_running_tasks, return_exceptions=True)
        logger.info("All background tasks confirmed cancelled.")
    except asyncio.CancelledError:
        logger.info("Some tasks were already cancelled during disconnect.")
    except Exception as e:
        logger.error(f"Error during background task cleanup on disconnect: {e}", exc_info=True)
    logger.info("FamilyBot graceful shutdown complete.")


# --- Main Bot Execution ---
if __name__ == "__main__":
    # interactions.py's client.start() is a blocking call that runs the event loop
    # and usually handles SIGINT (Ctrl+C) by stopping the bot and triggering on_disconnect.
    # No explicit signal handlers are typically needed here for Windows.
    logger.info("Starting FamilyBot client...")
    client.start()
