# In src/familybot/FamilyBot.py

# Import necessary libraries
import argparse
import asyncio
import os
import sys
from datetime import datetime
from typing import TYPE_CHECKING, cast
import sqlite3  # Standard library import should come before third-party imports

import uvicorn
from interactions import Client, GuildText, Intents, listen
from interactions.ext import prefixed_commands
from interactions.client.errors import (
    LibraryException,
)  # Corrected import for Discord API error handling

from familybot.config import (
    ADMIN_DISCORD_ID,
    DISCORD_API_KEY,
    WEB_UI_ENABLED,
    WEB_UI_HOST,
    WEB_UI_PORT,
)
from familybot.lib.database import (
    get_db_connection,
    init_db,
    sync_family_members_from_config,
)
from familybot.lib.logging_config import setup_bot_logging
from familybot.lib.types import FamilyBotClient
from familybot.lib.utils import split_message
from familybot.web.api import app as web_app
from familybot.web.api import set_bot_client

if TYPE_CHECKING:
    pass

# Setup comprehensive logging for the bot
logger = setup_bot_logging("INFO")

# --- Client Setup ---
client: FamilyBotClient = cast(
    FamilyBotClient, Client(token=DISCORD_API_KEY, intents=Intents.ALL)
)
prefixed_commands.setup(cast(Client, client), default_prefix="!")

# List to keep track of background tasks for graceful shutdown
_running_tasks = []


# --- Plugin Loading ---
def get_plugins(directory: str) -> list:
    plugin_list = []
    try:
        for file_name in os.listdir(directory):
            if file_name.endswith(".py") and not file_name.startswith("__"):
                plugin_name = f"familybot.plugins.{file_name[:-3]}"
                plugin_list.append(plugin_name)
        return plugin_list
    except FileNotFoundError:
        logger.error("Plugin directory not found: %s", directory)
        return []
    except OSError as e:
        logger.error("Error listing plugin directory: %s", e)
        return []


plugins_to_load = get_plugins(os.path.join(os.path.dirname(__file__), "plugins"))
if plugins_to_load:
    for plugin in plugins_to_load:
        try:
            client.load_extension(plugin)
            logger.info("Loaded plugin: %s", plugin)
        except Exception as e:  # pylint: disable=broad-except
            # General catch is justified here to avoid crashing on plugin load
            logger.error("Failed to load plugin %s: %s", plugin, e, exc_info=True)
else:
    logger.warning("No plugins found to load.")


# --- Global Utility Functions for Bot Instance ---
async def send_to_channel(channel_id: int, message: str) -> None:
    """Send a message to a Discord channel, automatically splitting if it exceeds length limits."""
    try:
        channel = await client.fetch_channel(channel_id)
        # Ensure channel is a GuildText channel before sending messages
        if isinstance(channel, GuildText):
            message_parts = split_message(message)
            if len(message_parts) > 1:
                logger.info(
                    "Message too long for channel %s, splitting into %s parts",
                    channel_id,
                    len(message_parts),
                )
            for i, part in enumerate(message_parts):
                try:
                    await channel.send(part)
                    if i < len(message_parts) - 1:
                        await asyncio.sleep(0.5)
                except LibraryException as part_error:
                    logger.error(
                        "Error sending message part %s/%s to channel %s: %s",
                        i + 1,
                        len(message_parts),
                        channel_id,
                        part_error,
                    )
        else:
            logger.warning(
                "Could not find channel with ID: %s or channel doesn't support sending messages.",
                channel_id,
            )
    except LibraryException as e:
        logger.error("Error sending message to channel %s: %s", channel_id, e)


async def send_log_dm(message: str) -> None:
    try:
        user = await client.fetch_user(int(ADMIN_DISCORD_ID))
        if user:
            now = datetime.now().strftime("%d/%m/%y %H:%M:%S")
            await user.send(f"{now} -> {message}")
    except LibraryException as e:
        logger.error("Error sending log DM to admin %s: %s", ADMIN_DISCORD_ID, e)


async def send_dm(discord_id: int, message: str) -> None:
    """Send a DM to a Discord user, automatically splitting if it exceeds length limits."""
    try:
        user = await client.fetch_user(discord_id)
        if user:
            message_parts = split_message(message)
            if len(message_parts) > 1:
                logger.info(
                    "DM too long for user %s, splitting into %s parts",
                    discord_id,
                    len(message_parts),
                )
            for i, part in enumerate(message_parts):
                try:
                    await user.send(part)
                    if i < len(message_parts) - 1:
                        await asyncio.sleep(0.5)
                except LibraryException as part_error:
                    logger.error(
                        "Error sending DM part %s/%s to user %s: %s",
                        i + 1,
                        len(message_parts),
                        discord_id,
                        part_error,
                    )
        else:
            logger.warning("Could not find user with ID: %s", discord_id)
    except LibraryException as e:
        logger.error("Error sending DM to user %s: %s", discord_id, e)


async def edit_msg(chan_id: int, msg_id: int, message: str) -> None:
    try:
        channel = client.get_channel(chan_id)
        # Ensure channel is a GuildText channel before fetching/editing messages
        if isinstance(channel, GuildText):
            msg = await channel.fetch_message(msg_id)
            if msg:
                await msg.edit(content=message)
            else:
                logger.warning(
                    "Message %s not found in channel %s for editing.", msg_id, chan_id
                )
        else:
            logger.warning(
                "Channel %s is not a text channel and does not support message editing.",
                chan_id,
            )
    except LibraryException as e:
        logger.error("Error editing message %s in channel %s: %s", msg_id, chan_id, e)


async def get_pinned_message(chan_id: int) -> list:
    try:
        channel = client.get_channel(chan_id)
        # Ensure channel is a GuildText channel before fetching pinned messages
        if isinstance(channel, GuildText):
            pinned_messages = await channel.fetch_pinned_messages()
            return pinned_messages
        else:
            logger.warning(
                "Channel %s is not a text channel and does not support fetching pinned messages.",
                chan_id,
            )
            return []
    except LibraryException as e:
        logger.error("Error fetching pinned messages from channel %s: %s", chan_id, e)
        return []


# --- Main application startup and shutdown logic ---
async def start_discord_bot():
    """Starts the Discord bot client."""
    logger.info("Starting FamilyBot Discord client...")
    # Use client.astart() which is designed to be awaited and manages its own loop connection.
    await client.astart()


async def start_web_server_main():
    """Starts the FastAPI web server using uvicorn Server."""
    # Set the bot client reference in the web API
    set_bot_client(client)

    logger.info("Starting Web UI server on http://%s:%s", WEB_UI_HOST, WEB_UI_PORT)

    # Use uvicorn.Server for async operation instead of uvicorn.run
    config = uvicorn.Config(
        web_app,
        host=WEB_UI_HOST,
        port=WEB_UI_PORT,
        log_config=None,
        access_log=False,  # Disable access logs to reduce noise
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_application():
    """Runs the Discord bot and optionally the Web UI."""
    # Initialize the database
    try:
        init_db()
        logger.info("Database initialized successfully.")

        # Synchronize family members from config.yml to the database
        sync_family_members_from_config()
        logger.info("Family members synchronized from config.yml.")
    except sqlite3.Error as e:
        logger.critical(
            "Failed to initialize database or sync family members: %s", e, exc_info=True
        )
        await send_log_dm(
            f"CRITICAL ERROR: Database failed to initialize or sync family members: {e}"
        )
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-except
        # General catch for unexpected errors
        logger.critical(
            "Unexpected error during DB init or family sync: %s", e, exc_info=True
        )
        await send_log_dm(
            f"CRITICAL ERROR: Unexpected error during DB init or family sync: {e}"
        )
        sys.exit(1)

    try:
        if WEB_UI_ENABLED:
            # If Web UI is enabled, uvicorn.run will be the blocking call.
            # We start the Discord bot as a background task.
            discord_bot_task = asyncio.create_task(start_discord_bot())
            _running_tasks.append(discord_bot_task)
            logger.info("Discord bot task scheduled as background.")

            # Start the Web UI server (blocking call)
            await start_web_server_main()  # This will block the event loop
        else:
            # If Web UI is not enabled, the Discord bot is the main blocking call.
            await start_discord_bot()  # This will block the event loop

        logger.info("Application tasks started.")
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received, initiating graceful shutdown...")
        await shutdown_application_tasks()
    except Exception as e:
        logger.error("Unexpected error in run_application: %s", e, exc_info=True)
        await shutdown_application_tasks()
        raise


async def shutdown_application_tasks():
    """Unified graceful shutdown for all application tasks."""
    logger.info("Initiating graceful shutdown of all background tasks.")
    for task in _running_tasks:
        if not task.done():
            task.cancel()
            logger.info(
                "Task %s cancelled.", task.get_name() if task.get_name() else task
            )
    try:
        await asyncio.gather(*_running_tasks, return_exceptions=True)
        logger.info("All background tasks confirmed cancelled.")
    except asyncio.CancelledError:
        logger.info("Some tasks were already cancelled during shutdown.")
    except Exception as e:  # pylint: disable=broad-except
        logger.error(
            "Error during background task cleanup on shutdown: %s", e, exc_info=True
        )
    logger.info("FamilyBot graceful shutdown complete.")


# --- Event Listeners and Background Tasks ---
@listen()
async def on_startup():
    # This event listener will now only be called once the bot is connected.
    # Most startup logic has moved to run_application()
    pass  # Keep it empty for now or for future Discord-specific startup logic


@listen()
async def on_disconnect():
    # This will be called when the Discord client disconnects.
    # If the Web UI is running, its shutdown event will handle the overall application shutdown.
    # If only Discord bot is running, this will trigger the shutdown.
    if not WEB_UI_ENABLED:
        await shutdown_application_tasks()


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
        confirm = (
            input("Are you sure you want to purge all game details cache? (y/N): ")
            .strip()
            .lower()
        )

        if confirm in ["y", "yes"]:
            # Clear the game details cache
            cursor.execute("DELETE FROM game_details_cache")
            conn.commit()
            conn.close()

            print(
                f"✅ Cache purge complete! Deleted {cache_count} cached game entries."
            )
            print("\n🔄 Next steps:")
            print(
                "- Start the bot and run !full_wishlist_scan to rebuild cache with USD pricing"
            )
            print("- Run !coop 2 to cache multiplayer games")
            print("- All future API calls will use USD pricing and new boolean fields")
        else:
            print("❌ Cache purge cancelled.")
    except sqlite3.Error as e:
        print(f"❌ Error purging cache: {e}")
        logger.error("Error purging cache from command line: %s", e, exc_info=True)
    except Exception as e:  # pylint: disable=broad-except
        # General catch for unexpected errors
        print(f"❌ Unexpected error purging cache: {e}")
        logger.error(
            "Unexpected error purging cache from command line: %s", e, exc_info=True
        )


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
        print(
            f"⚠️  Found {total_count} cached wishlist entries from {user_count} users."
        )
        confirm = (
            input("Are you sure you want to purge all wishlist cache? (y/N): ")
            .strip()
            .lower()
        )

        if confirm in ["y", "yes"]:
            # Clear the wishlist cache
            cursor.execute("DELETE FROM wishlist_cache")
            conn.commit()
            conn.close()

            print(
                f"✅ Wishlist cache purge complete! Deleted {total_count} entries from {user_count} users."
            )
            print("\n🔄 Next steps:")
            print("- Start the bot and run !force_wishlist to rebuild wishlist cache")
            print(
                "- Or wait for the next automatic wishlist refresh (runs every 24 hours)"
            )
        else:
            print("❌ Wishlist cache cancelled.")
    except sqlite3.Error as e:
        print(f"❌ Error purging wishlist cache: {e}")
        logger.error(
            "Error purging wishlist cache from command line: %s", e, exc_info=True
        )
    except Exception as e:  # pylint: disable=broad-except
        # General catch for unexpected errors
        print(f"❌ Unexpected error purging wishlist cache: {e}")
        logger.error(
            "Unexpected error purging wishlist cache from command line: %s",
            e,
            exc_info=True,
        )


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
        confirm = (
            input("Are you sure you want to purge family library cache? (y/N): ")
            .strip()
            .lower()
        )

        if confirm in ["y", "yes"]:
            # Clear the family library cache
            cursor.execute("DELETE FROM family_library_cache")
            conn.commit()
            conn.close()

            print(
                f"✅ Family library cache purge complete! Deleted {cache_count} entries."
            )
            print("\n🔄 Next steps:")
            print("- Start the bot and run !force to rebuild family library cache")
            print("- Or wait for the next automatic refresh (runs every hour)")
        else:
            print("❌ Family library cache cancelled.")
    except sqlite3.Error as e:
        print(f"❌ Error purging family library cache: {e}")
        logger.error(
            "Error purging family library cache from command line: %s", e, exc_info=True
        )
    except Exception as e:  # pylint: disable=broad-except
        # General catch for unexpected errors
        print(f"❌ Unexpected error purging family library cache: {e}")
        logger.error(
            "Unexpected error purging family library cache from command line: %s",
            e,
            exc_info=True,
        )


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

        total_count = (
            game_count + wishlist_count + family_count + user_games_count + itad_count
        )

        if total_count == 0:
            print("✅ All caches are already empty.")
            return

        # Show breakdown
        print("⚠️  Found cached data:")
        print(f"   - Game details: {game_count} entries")
        print(f"   - Wishlist: {wishlist_count} entries")
        print(f"   - Family library: {family_count} entries")
        print(f"   - User games: {user_games_count} entries")
        print(f"   - ITAD prices: {itad_count} entries")
        print(f"   - Total: {total_count} entries")

        confirm = (
            input("Are you sure you want to purge ALL cache data? (y/N): ")
            .strip()
            .lower()
        )

        if confirm in ["y", "yes"]:
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
    except sqlite3.Error as e:
        print(f"❌ Error purging all cache: {e}")
        logger.error("Error purging all cache from command line: %s", e, exc_info=True)
    except Exception as e:  # pylint: disable=broad-except
        # General catch for unexpected errors in cache purging utility.
        # This is justified because this is a command-line tool and we want to ensure any unexpected error is reported to the user
        # without crashing the script, as this is a top-level utility function.
        print(f"❌ Unexpected error purging all cache: {e}")
        logger.error(
            "Unexpected error purging all cache from command line: %s", e, exc_info=True
        )


# --- Main Bot Execution ---
if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="FamilyBot - Discord bot for Steam family management"
    )
    parser.add_argument(
        "--purge-cache",
        action="store_true",
        help="Purge game details cache to force fresh USD pricing and new boolean fields",
    )
    parser.add_argument(
        "--purge-wishlist",
        action="store_true",
        help="Purge wishlist cache to force fresh wishlist data",
    )
    parser.add_argument(
        "--purge-family-library",
        action="store_true",
        help="Purge family library cache to force fresh family game data",
    )
    parser.add_argument(
        "--purge-all",
        action="store_true",
        help="Purge all cache data (game details, wishlist, family library, etc.)",
    )
    parser.add_argument(
        "--full-library-scan",
        action="store_true",
        help="Scan all family members' complete game libraries and cache game details",
    )
    parser.add_argument(
        "--full-wishlist-scan",
        action="store_true",
        help="Perform comprehensive scan of ALL common wishlist games",
    )

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
        print(
            "This command requires Discord interaction for progress updates and admin verification."
        )
        sys.exit(1)

    # Normal bot startup with proper signal handling
    logger.info("Starting FamilyBot client...")
    try:
        asyncio.run(run_application())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down gracefully...")
    except Exception as e:  # pylint: disable=broad-except
        # General catch is justified here to ensure any unexpected errors during startup are logged and the process exits cleanly.
        logger.error("Unexpected error during startup: %s", e, exc_info=True)
        sys.exit(1)

# Assign utility functions directly to the client instance after run_application
# to ensure the client is properly cast before assignment.
client.send_to_channel = send_to_channel  # type: ignore
client.send_log_dm = send_log_dm  # type: ignore
client.send_dm = send_dm  # type: ignore
client.edit_msg = edit_msg  # type: ignore
client.get_pinned_message = get_pinned_message  # type: ignore


def main():
    """Entry point for the familybot script alias."""
    # This function allows the bot to be run via 'uv run familybot'
    # Parse command line arguments
    main_parser = argparse.ArgumentParser(
        description="FamilyBot - Discord bot for Steam family management"
    )
    main_parser.add_argument(
        "--purge-cache",
        action="store_true",
        help="Purge game details cache to force fresh USD pricing and new boolean fields",
    )
    main_parser.add_argument(
        "--purge-wishlist",
        action="store_true",
        help="Purge wishlist cache to force fresh wishlist data",
    )
    main_parser.add_argument(
        "--purge-family-library",
        action="store_true",
        help="Purge family library cache to force fresh family game data",
    )
    main_parser.add_argument(
        "--purge-all",
        action="store_true",
        help="Purge all cache data (game details, wishlist, family library, etc.)",
    )
    main_parser.add_argument(
        "--full-library-scan",
        action="store_true",
        help="Scan all family members' complete game libraries and cache game details",
    )
    main_parser.add_argument(
        "--full-wishlist-scan",
        action="store_true",
        help="Perform comprehensive scan of ALL common wishlist games",
    )

    main_args = main_parser.parse_args()

    # Handle command line operations
    if main_args.purge_cache:
        print("🗑️ Purging game details cache...")
        purge_game_cache()
        sys.exit(0)
    elif main_args.purge_wishlist:
        print("🗑️ Purging wishlist cache...")
        purge_wishlist_cache()
        sys.exit(0)
    elif main_args.purge_family_library:
        print("🗑️ Purging family library cache...")
        purge_family_library_cache()
        sys.exit(0)
    elif main_args.purge_all:
        print("🗑️ Purging all cache data...")
        purge_all_cache()
        sys.exit(0)
    elif main_args.full_library_scan:
        print("❌ Full library scan requires the bot to be running.")
        print("Please start the bot and use the Discord command: !full_library_scan")
        print(
            "This command requires Discord interaction for progress updates and admin verification."
        )
        sys.exit(1)

    # Normal bot startup with proper signal handling
    logger.info("Starting FamilyBot client...")
    try:
        asyncio.run(run_application())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down gracefully...")
    except Exception as e:  # pylint: disable=broad-except
        # General catch is justified here to ensure any unexpected errors during startup are logged and the process exits cleanly.
        logger.error("Unexpected error during startup: %s", e, exc_info=True)
        sys.exit(1)
