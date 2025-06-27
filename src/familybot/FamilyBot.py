# In src/familybot/FamilyBot.py

# Import necessary libraries
import os
import asyncio
import signal
import sys
import argparse
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
from familybot.lib.database import init_db, get_db_connection # <<< Import init_db and get_db_connection
from familybot.lib.types import FamilyBotClient, DISCORD_MESSAGE_LIMIT # Import the protocol type and message limit
from familybot.lib.utils import truncate_message_list, split_message # Import message utilities


# Import our centralized logging configuration
from familybot.lib.logging_config import setup_bot_logging, get_logger

# Setup comprehensive logging for the bot
logger = setup_bot_logging("INFO")  # Can be changed to DEBUG for more verbose logging

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
    """
    Send a message to a Discord channel, automatically splitting if it exceeds length limits.
    
    Args:
        channel_id: The Discord channel ID
        message: The message content to send
    """
    try:
        channel = await client.fetch_channel(channel_id)
        
        # Type guard to check if channel supports sending messages
        if not channel:
            logger.warning(f"Could not find channel with ID: {channel_id}")
            return
        
        if not (isinstance(channel, GuildText) or hasattr(channel, 'send')):
            logger.warning(f"Channel {channel_id} doesn't support sending messages")
            return
        
        # Split message if it's too long
        message_parts = split_message(message)
        
        if len(message_parts) > 1:
            logger.info(f"Message too long for channel {channel_id}, splitting into {len(message_parts)} parts")
        
        # Send each part
        for i, part in enumerate(message_parts):
            try:
                if isinstance(channel, GuildText):
                    await channel.send(part)
                else:
                    await channel.send(part)  # type: ignore
                
                # Add small delay between parts to avoid rate limiting
                if i < len(message_parts) - 1:
                    await asyncio.sleep(0.5)
                    
            except Exception as part_error:
                logger.error(f"Error sending message part {i+1}/{len(message_parts)} to channel {channel_id}: {part_error}")
                # Continue trying to send remaining parts
                
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
    """
    Send a DM to a Discord user, automatically splitting if it exceeds length limits.
    
    Args:
        discord_id: The Discord user ID
        message: The message content to send
    """
    try:
        user = await client.fetch_user(discord_id)
        if user:
            # Split message if it's too long
            message_parts = split_message(message)
            
            if len(message_parts) > 1:
                logger.info(f"DM too long for user {discord_id}, splitting into {len(message_parts)} parts")
            
            # Send each part
            for i, part in enumerate(message_parts):
                try:
                    await user.send(part)
                    
                    # Add small delay between parts to avoid rate limiting
                    if i < len(message_parts) - 1:
                        await asyncio.sleep(0.5)
                        
                except Exception as part_error:
                    logger.error(f"Error sending DM part {i+1}/{len(message_parts)} to user {discord_id}: {part_error}")
                    # Continue trying to send remaining parts
        else:
            logger.warning(f"Could not find user with ID: {discord_id}")
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


# --- Command Line Utilities ---
def purge_game_cache() -> None:
    """Purge the game details cache from command line."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get count before deletion
        cursor.execute("SELECT COUNT(*) FROM game_details_cache")
        cache_count = cursor.fetchone()[0]
        
        if cache_count == 0:
            print("✅ Game details cache is already empty.")
            return
        
        # Confirm deletion
        print(f"⚠️  Found {cache_count} cached game entries.")
        confirm = input("Are you sure you want to purge all game details cache? (y/N): ").strip().lower()
        
        if confirm in ['y', 'yes']:
            # Clear the game details cache
            cursor.execute("DELETE FROM game_details_cache")
            conn.commit()
            conn.close()
            
            print(f"✅ Cache purge complete! Deleted {cache_count} cached game entries.")
            print("\n🔄 Next steps:")
            print("- Start the bot and run !full_wishlist_scan to rebuild cache with USD pricing")
            print("- Run !coop 2 to cache multiplayer games")
            print("- All future API calls will use USD pricing and new boolean fields")
        else:
            print("❌ Cache purge cancelled.")
            
    except Exception as e:
        print(f"❌ Error purging cache: {e}")
        logger.error(f"Error purging cache from command line: {e}", exc_info=True)


def purge_wishlist_cache() -> None:
    """Purge the wishlist cache from command line."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get count before deletion
        cursor.execute("SELECT COUNT(DISTINCT steam_id) FROM wishlist_cache")
        user_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM wishlist_cache")
        total_count = cursor.fetchone()[0]
        
        if total_count == 0:
            print("✅ Wishlist cache is already empty.")
            return
        
        # Confirm deletion
        print(f"⚠️  Found {total_count} cached wishlist entries from {user_count} users.")
        confirm = input("Are you sure you want to purge all wishlist cache? (y/N): ").strip().lower()
        
        if confirm in ['y', 'yes']:
            # Clear the wishlist cache
            cursor.execute("DELETE FROM wishlist_cache")
            conn.commit()
            conn.close()
            
            print(f"✅ Wishlist cache purge complete! Deleted {total_count} entries from {user_count} users.")
            print("\n🔄 Next steps:")
            print("- Start the bot and run !force_wishlist to rebuild wishlist cache")
            print("- Or wait for the next automatic wishlist refresh (runs every 24 hours)")
        else:
            print("❌ Wishlist cache purge cancelled.")
            
    except Exception as e:
        print(f"❌ Error purging wishlist cache: {e}")
        logger.error(f"Error purging wishlist cache from command line: {e}", exc_info=True)


def purge_family_library_cache() -> None:
    """Purge the family library cache from command line."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get count before deletion
        cursor.execute("SELECT COUNT(*) FROM family_library_cache")
        cache_count = cursor.fetchone()[0]
        
        if cache_count == 0:
            print("✅ Family library cache is already empty.")
            return
        
        # Confirm deletion
        print(f"⚠️  Found {cache_count} cached family library entries.")
        confirm = input("Are you sure you want to purge family library cache? (y/N): ").strip().lower()
        
        if confirm in ['y', 'yes']:
            # Clear the family library cache
            cursor.execute("DELETE FROM family_library_cache")
            conn.commit()
            conn.close()
            
            print(f"✅ Family library cache purge complete! Deleted {cache_count} entries.")
            print("\n🔄 Next steps:")
            print("- Start the bot and run !force to rebuild family library cache")
            print("- Or wait for the next automatic refresh (runs every hour)")
        else:
            print("❌ Family library cache purge cancelled.")
            
    except Exception as e:
        print(f"❌ Error purging family library cache: {e}")
        logger.error(f"Error purging family library cache from command line: {e}", exc_info=True)


def purge_all_cache() -> None:
    """Purge all cache data from command line."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get counts before deletion
        cursor.execute("SELECT COUNT(*) FROM game_details_cache")
        game_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM wishlist_cache")
        wishlist_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM family_library_cache")
        family_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM user_games_cache")
        user_games_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM itad_price_cache")
        itad_count = cursor.fetchone()[0]
        
        total_count = game_count + wishlist_count + family_count + user_games_count + itad_count
        
        if total_count == 0:
            print("✅ All caches are already empty.")
            return
        
        # Show breakdown
        print(f"⚠️  Found cached data:")
        print(f"   - Game details: {game_count} entries")
        print(f"   - Wishlist: {wishlist_count} entries")
        print(f"   - Family library: {family_count} entries")
        print(f"   - User games: {user_games_count} entries")
        print(f"   - ITAD prices: {itad_count} entries")
        print(f"   - Total: {total_count} entries")
        
        confirm = input("Are you sure you want to purge ALL cache data? (y/N): ").strip().lower()
        
        if confirm in ['y', 'yes']:
            # Clear all caches
            cursor.execute("DELETE FROM game_details_cache")
            cursor.execute("DELETE FROM wishlist_cache")
            cursor.execute("DELETE FROM family_library_cache")
            cursor.execute("DELETE FROM user_games_cache")
            cursor.execute("DELETE FROM itad_price_cache")
            conn.commit()
            conn.close()
            
            print(f"✅ All cache purge complete! Deleted {total_count} total entries.")
            print("\n🔄 Next steps:")
            print("- Start the bot to begin rebuilding caches automatically")
            print("- Run !full_wishlist_scan for comprehensive wishlist rebuild")
            print("- Run !coop 2 to cache multiplayer games")
        else:
            print("❌ Cache purge cancelled.")
            
    except Exception as e:
        print(f"❌ Error purging all cache: {e}")
        logger.error(f"Error purging all cache from command line: {e}", exc_info=True)


# --- Main Bot Execution ---
if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='FamilyBot - Discord bot for Steam family management')
    parser.add_argument('--purge-cache', action='store_true', 
                       help='Purge game details cache to force fresh USD pricing and new boolean fields')
    parser.add_argument('--purge-wishlist', action='store_true',
                       help='Purge wishlist cache to force fresh wishlist data')
    parser.add_argument('--purge-family-library', action='store_true',
                       help='Purge family library cache to force fresh family game data')
    parser.add_argument('--purge-all', action='store_true',
                       help='Purge all cache data (game details, wishlist, family library, etc.)')
    parser.add_argument('--full-library-scan', action='store_true',
                       help='Scan all family members\' complete game libraries and cache game details')
    parser.add_argument('--full-wishlist-scan', action='store_true',
                       help='Perform comprehensive scan of ALL common wishlist games')
    
    args = parser.parse_args()
    
    # Handle command line operations
    if args.purge_cache:
        print("🗑️ Purging game details cache...")
        purge_game_cache()
        sys.exit(0)
    elif args.purge_wishlist:
        print("🗑️ Purging wishlist cache...")
        purge_wishlist_cache()
        sys.exit(0)
    elif args.purge_family_library:
        print("🗑️ Purging family library cache...")
        purge_family_library_cache()
        sys.exit(0)
    elif args.purge_all:
        print("🗑️ Purging all cache data...")
        purge_all_cache()
        sys.exit(0)
    elif args.full_library_scan:
        print("❌ Full library scan requires the bot to be running.")
        print("Please start the bot and use the Discord command: !full_library_scan")
        print("This command requires Discord interaction for progress updates and admin verification.")
        sys.exit(1)
    
    # Normal bot startup
    # interactions.py's client.start() is a blocking call that runs the event loop
    # and usually handles SIGINT (Ctrl+C) by stopping the bot and triggering on_disconnect.
    # No explicit signal handlers are typically needed here for Windows.
    logger.info("Starting FamilyBot client...")
    client.start()
