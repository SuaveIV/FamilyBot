import asyncio
import logging
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add src to path so we can import familybot
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from familybot.plugins.free_games import FreeGames
from familybot.lib.types import FamilyBotClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TestFreeGames")

async def mock_send_to_channel(channel_id, message):
    try:
        # Safe print for Windows consoles
        safe_message = message.encode('utf-8', errors='ignore').decode('utf-8')
        print(f"\n[MOCK SEND] Channel: {channel_id}\nMessage:\n{safe_message}\n")
    except Exception:
        # Fallback if encoding fails completely
        print(f"\n[MOCK SEND] Channel: {channel_id}\nMessage: <content hidden due to encoding error>\n")

async def main():
    logger.info("Starting Free Games Plugin Test...")

    # Mock the bot
    mock_bot = MagicMock(spec=FamilyBotClient)
    mock_bot.fetch_channel = AsyncMock(return_value=True)
    mock_bot.fetch_user = AsyncMock(return_value=True)
    mock_bot.send_to_channel = AsyncMock(side_effect=mock_send_to_channel)
    mock_bot.ext = {}
    mock_bot.add_command = MagicMock()
    mock_bot.add_listener = MagicMock()
    mock_bot.dispatch = MagicMock() # Mock the 'dispatch' method # Mock the 'add_listener' method # Mock the 'add_command' method # Mock the 'ext' attribute for Extension initialization

    # Initialize plugin
    plugin = FreeGames(mock_bot)
    
    logger.info("--- Run 1: Initialization (Marking existing posts as seen) ---")
    await plugin.check_bsky_free_games()
    
    logger.info(f"Initialized with {len(plugin._seen_bsky_posts)} posts.")
    
    logger.info("--- Run 2: Simulation (Clearing seen list to force parsing of 'new' posts) ---")
    plugin._seen_bsky_posts.clear()
    
    # We also need to be careful not to trigger the "first run" block again.
    # plugin._first_bsky_run is already False after Run 1.
    
    await plugin.check_bsky_free_games()
    
    logger.info("Test Complete.")

if __name__ == "__main__":
    asyncio.run(main())
