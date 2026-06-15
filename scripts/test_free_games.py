import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

# Add src to path so we can import familybot
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from familybot.lib.types import FamilyBotClient
from familybot.plugins.free_games import FreeGames

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("TestFreeGames")

# --- Mock Data ---

MOCK_GIVEAWAYS = [
    {
        "id": 1,
        "title": "Great Free Game",
        "worth": "$19.99",
        "type": "Game",
        "platforms": "PC, Steam",
        "status": "Active",
        "description": "A truly great game.",
        "open_giveaway_url": "https://www.gamerpower.com/open/great-free-game",
    },
    {
        "id": 2,
        "title": "Awesome Free Game",
        "worth": "N/A",
        "type": "Game",
        "platforms": "PC, Epic Games Store",
        "status": "Active",
        "description": "Claim this game for free on EGS!",
        "open_giveaway_url": "https://www.gamerpower.com/open/awesome-free-game",
    },
    {
        "id": 3,
        "title": "Prime Free Game",
        "worth": "N/A",
        "type": "Game",
        "platforms": "PC, Amazon Prime Gaming",
        "status": "Active",
        "description": "Claim this game for free with Prime!",
        "open_giveaway_url": "https://www.gamerpower.com/open/prime-free-game",
    },
    {
        "id": 4,
        "title": "Expired Game",
        "worth": "N/A",
        "type": "Game",
        "platforms": "PC, Steam",
        "status": "Expired",
        "description": "No longer free.",
        "open_giveaway_url": "https://www.gamerpower.com/open/expired-game",
    },
    {
        "id": 5,
        "title": "DLC Pack",
        "worth": "N/A",
        "type": "DLC",
        "platforms": "PC, Steam",
        "status": "Active",
        "description": "Requires paid base game.",
        "open_giveaway_url": "https://www.gamerpower.com/open/dlc-pack",
    },
    {
        "id": 6,
        "title": "Third-Party Steam Key",
        "worth": "N/A",
        "type": "Game",
        "platforms": "PC, Steam",
        "status": "Active",
        "description": "Free key giveaway on Alienware.",
        "open_giveaway_url": "https://www.gamerpower.com/open/third-party-steam",
    },
    {
        "id": 7,
        "title": "GOG Game",
        "worth": "$9.99",
        "type": "Game",
        "platforms": "PC, GOG",
        "status": "Active",
        "description": "A great game from GOG",
        "open_giveaway_url": "https://www.gamerpower.com/open/gog-game",
    },
    {
        "id": 8,
        "title": "Itch.io Game",
        "worth": "N/A",
        "type": "Game",
        "platforms": "PC, Itch.io",
        "status": "Active",
        "description": "A cool indie game",
        "open_giveaway_url": "https://www.gamerpower.com/open/itch-game",
    },
]

MOCK_RESOLVED_URLS = {
    "https://www.gamerpower.com/open/great-free-game": "https://store.steampowered.com/app/12345",
    "https://www.gamerpower.com/open/awesome-free-game": "https://store.epicgames.com/p/awesome-game",
    "https://www.gamerpower.com/open/prime-free-game": "https://gaming.amazon.com/prime-game",
    "https://www.gamerpower.com/open/expired-game": "https://store.steampowered.com/app/expired",
    "https://www.gamerpower.com/open/dlc-pack": "https://store.steampowered.com/app/dlc",
    "https://www.gamerpower.com/open/third-party-steam": "https://na.alienwarearena.com/giveaway/loot",
    "https://www.gamerpower.com/open/gog-game": "https://www.gog.com/game/gog_game",
    "https://www.gamerpower.com/open/itch-game": "https://some-dev.itch.io/cool-game",
}

# --- Mocks for Network Calls ---


async def mock_fetch_gamerpower_giveaways(_self: Any, _session: Any) -> list[dict[str, Any]]:
    logger.info("[MOCK] _fetch_gamerpower_giveaways called, returning mock data.")
    return MOCK_GIVEAWAYS


async def mock_resolve_redirect_url(_self: Any, url: str, _session: Any) -> str | None:
    logger.info(f"[MOCK] _resolve_redirect_url called for {url}")
    return MOCK_RESOLVED_URLS.get(url)


async def run_live_test():
    """Runs a live test against the actual GamerPower API."""
    logger.info("--- Starting LIVE Free Games Plugin Test ---")
    logger.warning("This test makes REAL network requests to GamerPower.")
    logger.warning("Output will be printed to the console.")

    # Mock the bot
    mock_bot = MagicMock(spec=FamilyBotClient)

    # Mock the channel to print output instead of sending to Discord
    mock_channel = MagicMock()

    async def print_to_channel(content=None, _embeds=None):
        if content:
            logger.info(f"[LIVE TEST-CHANNEL SEND] Message: {content}")

    mock_channel.send = AsyncMock(side_effect=print_to_channel)

    mock_bot.fetch_channel = AsyncMock(return_value=mock_channel)
    mock_bot.fetch_user = AsyncMock(return_value=True)
    mock_bot.ext = {}
    mock_bot.add_command = MagicMock()
    mock_bot.add_listener = MagicMock()
    mock_bot.dispatch = MagicMock()

    # Initialize the real plugin
    plugin = cast(FreeGames, FreeGames(mock_bot))

    # Mock context for the manual command
    mock_ctx = MagicMock()
    mock_ctx.channel = mock_channel
    mock_ctx.author_id = "12345"

    async def print_to_ctx(message):
        logger.info(f"[LIVE TEST-CTX SEND] {message}")

    mock_ctx.send = AsyncMock(side_effect=print_to_ctx)

    # Use patch to temporarily set the admin ID for the command to run
    with patch("familybot.plugins.free_games.ADMIN_DISCORD_ID", "12345"):
        await plugin.force_free_command(mock_ctx)


async def main():
    logger.info("Starting Free Games Plugin Test...")

    # Mock the bot
    mock_bot = MagicMock(spec=FamilyBotClient)
    # Make the mock channel have a send method
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()
    mock_bot.fetch_channel = AsyncMock(return_value=mock_channel)
    mock_bot.fetch_user = AsyncMock(return_value=True)
    mock_bot.ext = {}
    mock_bot.add_command = MagicMock()
    mock_bot.add_listener = MagicMock()
    mock_bot.dispatch = MagicMock()

    # Initialize plugin
    plugin = cast(FreeGames, FreeGames(mock_bot))

    # Patch the network-calling methods
    with (
        patch(
            "familybot.plugins.free_games.FreeGames._fetch_gamerpower_giveaways",
            new=mock_fetch_gamerpower_giveaways,
        ),
        patch(
            "familybot.plugins.free_games.FreeGames._resolve_redirect_url",
            new=mock_resolve_redirect_url,
        ),
    ):
        # --- Test 1: Initial run to populate seen giveaways ---
        logger.info("--- Test 1: Initialization (Marking existing giveaways as seen) ---")
        await plugin.scheduled_free_games_check()
        # On the first run, it should see all giveaways but not send notifications
        assert len(plugin._seen_giveaways) == len(MOCK_GIVEAWAYS), (  # noqa: S101
            f"Expected {len(MOCK_GIVEAWAYS)} seen giveaways, got {len(plugin._seen_giveaways)}"
        )
        mock_channel.send.assert_not_called()
        logger.info(
            f"OK: Initialized with {len(plugin._seen_giveaways)} giveaways. No notifications sent."
        )

        # --- Test 2: Second run, no new giveaways ---
        logger.info("\n--- Test 2: No new giveaways ---")
        mock_channel.send.reset_mock()
        await plugin.scheduled_free_games_check()
        mock_channel.send.assert_not_called()
        logger.info("OK: No new giveaways found, no notifications sent.")

        # --- Test 3: Manual trigger with filtering ---
        logger.info("\n--- Test 3: Manual trigger with filtering logic ---")
        mock_channel.send.reset_mock()
        # Clear seen giveaways to simulate a fresh manual check where
        # we expect to see all valid items
        plugin._seen_giveaways.clear()
        logger.info("Cleared seen giveaways for manual trigger test.")

        # Mock context for the manual command
        mock_ctx = MagicMock()
        mock_ctx.channel = mock_channel
        mock_ctx.author_id = "12345"
        mock_ctx.send = AsyncMock()

        # We need to set the ADMIN_DISCORD_ID for the check to pass
        with patch("familybot.plugins.free_games.ADMIN_DISCORD_ID", "12345"):
            await plugin.force_free_command(mock_ctx)

        # Check the initial "Checking..." message
        mock_ctx.send.assert_any_call("Checking for free games...")

        # We expect 5 valid games to be posted:
        # - Great Free Game (Steam)
        # - Awesome Free Game (Epic)
        # - Prime Free Game (Amazon)
        # - GOG Game (GOG)
        # - Itch.io Game (Itch)
        # The other 3 giveaways should be filtered out:
        # - Expired Game (status filter)
        # - DLC Pack (type filter)
        # - Third-Party Steam Key (domain verification filter)
        call_count = mock_channel.send.call_count
        logger.info(f"Found {call_count} channel send calls.")
        assert call_count == 5, f"Expected 5 game announcements, but got {call_count}"  # noqa: S101

        logger.info("OK: Correct number of games (5) were announced.")
        logger.info("Filtered out:")
        logger.info(" - 'Expired Game' (status filter)")
        logger.info(" - 'DLC Pack' (type filter)")
        logger.info(" - 'Third-Party Steam Key' (domain verification filter)")

        # --- Test 4: Manual trigger with no new games ---
        logger.info("\n--- Test 4: Manual trigger with no new games ---")
        mock_channel.send.reset_mock()
        mock_ctx.send.reset_mock()

        # Run the check again. Since the giveaways are now "seen", it should find nothing.
        with patch("familybot.plugins.free_games.ADMIN_DISCORD_ID", "12345"):
            await plugin.force_free_command(mock_ctx)

        # It should not send any game announcements
        mock_channel.send.assert_not_called()
        # It should send the "Check complete" message
        mock_ctx.send.assert_any_call("Check complete. No new free games found.")
        logger.info("OK: Correctly reported no new games found.")

    logger.info("Test Complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test script for the Free Games plugin.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run a live test against real APIs instead of using mock data.",
    )
    args = parser.parse_args()

    asyncio.run(run_live_test() if args.live else main())
