import asyncio
import logging
import argparse
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch
from typing import List, Dict, Any, cast

# Add src to path so we can import familybot
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from familybot.plugins.free_games import FreeGames
from familybot.lib.types import FamilyBotClient

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("TestFreeGames")

# --- Mock Data ---


def create_bsky_post(uri: str, text: str, url: str) -> Dict[str, Any]:
    """Helper to create a mock Bluesky post."""
    return {
        "post": {
            "uri": uri,
            "record": {
                "text": text,
                "facets": [
                    {
                        "features": [
                            {"$type": "app.bsky.richtext.facet#link", "uri": url}
                        ]
                    }
                ],
            },
        }
    }


MOCK_BLUESKY_POSTS = [
    create_bsky_post(
        "bsky_post_1",
        "[Steam] Great Free Game is free on Steam",
        "https://store.steampowered.com/app/12345",
    ),
    create_bsky_post(
        "bsky_post_2",
        "[Epic Games] Awesome Free Game is free on EGS",
        "https://www.epicgames.com/store/p/awesome-game",
    ),
    create_bsky_post(
        "bsky_post_3",
        "[Amazon] Prime Free Game is free on Prime Gaming",
        "https://gaming.amazon.com/prime-game",
    ),
    create_bsky_post(
        "bsky_post_4",
        "[Steam] Expired Game is free on Steam",
        "https://store.steampowered.com/app/expired",
    ),
    create_bsky_post(
        "bsky_post_5",
        "[Steam] DLC that requires paid base game",
        "https://store.steampowered.com/app/dlc",
    ),
    create_bsky_post(
        "bsky_post_6",
        "[Steam] Game from Reddit is free",
        "https://www.reddit.com/r/GameDeals/comments/valid_post",
    ),
    create_bsky_post(
        "bsky_post_7",
        "[Steam] Expired game from Reddit",
        "https://www.reddit.com/r/GameDeals/comments/expired_post",
    ),
    create_bsky_post(
        "bsky_post_8",
        "[Steam] Reddit post linking to excluded domain",
        "https://www.reddit.com/r/GameDeals/comments/excluded_domain_post",
    ),
    create_bsky_post(
        "bsky_post_9",
        "[GOG] A great game from GOG",
        "https://www.gog.com/game/some_game",
    ),
    create_bsky_post(
        "bsky_post_10",
        "[Itch.io] A cool indie game is free",
        "https://some-dev.itch.io/cool-indie-game",
    ),
    create_bsky_post(
        "bsky_post_11",
        "[Steam] (DLC) Some Cool Skin Pack",
        "https://store.steampowered.com/app/dlc_pack",
    ),
]

MOCK_REDDIT_RESPONSES = {
    "https://www.reddit.com/r/GameDeals/comments/valid_post.json": {
        "link_flair_text": "100% OFF",
        "url": "https://store.steampowered.com/app/reddit_game",
    },
    "https://www.reddit.com/r/GameDeals/comments/expired_post.json": {
        "link_flair_text": "Expired",
        "url": "https://store.steampowered.com/app/reddit_expired",
    },
    "https://www.reddit.com/r/GameDeals/comments/excluded_domain_post.json": {
        "link_flair_text": "100% OFF",
        "url": "https://givee.club/game/123",
    },
}

MOCK_STEAM_DETAILS = {
    "12345": {"name": "Great Free Game", "short_description": "A truly great game."},
    "reddit_game": {
        "name": "Game from Reddit",
        "short_description": "A game linked from Reddit.",
    },
}

# --- Mocks for Network Calls ---


async def mock_fetch_bluesky_posts(*args, **kwargs) -> List[Dict[str, Any]]:
    logger.info("[MOCK] _fetch_bluesky_posts called, returning mock data.")
    return MOCK_BLUESKY_POSTS


async def mock_get_reddit_post_details(self, reddit_url: str) -> Dict[str, Any] | None:
    logger.info(f"[MOCK] _get_reddit_post_details called for {reddit_url}")
    # Append .json if it's not there for matching the key
    if not reddit_url.endswith(".json"):
        reddit_url += ".json"
    return MOCK_REDDIT_RESPONSES.get(reddit_url)


async def mock_fetch_game_details(
    steam_id: str, steam_api_manager: Any
) -> Dict[str, Any] | None:
    logger.info(f"[MOCK] fetch_game_details called for Steam ID: {steam_id}")
    return MOCK_STEAM_DETAILS.get(steam_id)


async def run_live_test():
    """Runs a live test against the actual Bluesky, Reddit, and Steam APIs."""
    logger.info("--- Starting LIVE Free Games Plugin Test ---")
    logger.warning(
        "This test makes REAL network requests to Bluesky, Reddit, and Steam."
    )
    logger.warning("Output will be printed to the console.")

    # Mock the bot
    mock_bot = MagicMock(spec=FamilyBotClient)

    # Mock the channel to print output instead of sending to Discord
    mock_channel = MagicMock()

    async def print_to_channel(embeds=None, content=None):
        # The 'embeds' parameter is a list of Embed objects
        if embeds and isinstance(embeds, list) and len(embeds) > 0:
            # Log the title of the first embed in the list
            first_embed = embeds[0]
            logger.info(f"[LIVE TEST-CHANNEL SEND] Embed Title: {first_embed.title}")
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
    mock_ctx.author_id = "12345"  # Needs to be a string for comparison

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
            "familybot.plugins.free_games.FreeGames._fetch_bluesky_posts",
            new=mock_fetch_bluesky_posts,
        ),
        patch(
            "familybot.plugins.free_games.FreeGames._get_reddit_post_details",
            new=mock_get_reddit_post_details,
        ),
        patch(
            "familybot.plugins.free_games.fetch_game_details",
            new=mock_fetch_game_details,
        ),
    ):
        # --- Test 1: Initial run to populate seen posts ---
        logger.info("--- Test 1: Initialization (Marking existing posts as seen) ---")
        await plugin.scheduled_bsky_free_games_check()
        # On the first run, it should see all posts but not send notifications
        assert len(plugin._seen_bsky_posts) == len(MOCK_BLUESKY_POSTS), (
            f"Expected {len(MOCK_BLUESKY_POSTS)} seen posts, got {len(plugin._seen_bsky_posts)}"
        )
        mock_channel.send.assert_not_called()
        logger.info(
            f"OK: Initialized with {len(plugin._seen_bsky_posts)} posts. No notifications sent."
        )

        # --- Test 2: Second run, no new posts ---
        logger.info("\n--- Test 2: No new posts ---")
        mock_channel.send.reset_mock()
        await plugin.scheduled_bsky_free_games_check()
        mock_channel.send.assert_not_called()
        logger.info("OK: No new posts found, no notifications sent.")

        # --- Test 3: Manual trigger with filtering ---
        logger.info("\n--- Test 3: Manual trigger with filtering logic ---")
        mock_channel.send.reset_mock()
        # Clear seen posts to simulate a fresh manual check where we expect to see all valid items
        plugin._seen_bsky_posts.clear()
        logger.info("Cleared seen posts for manual trigger test.")

        # Mock context for the manual command
        mock_ctx = MagicMock()
        mock_ctx.channel = mock_channel
        mock_ctx.author_id = "12345"  # Needs to be a string for comparison
        mock_ctx.send = AsyncMock()

        # We need to set the ADMIN_DISCORD_ID for the check to pass
        with patch("familybot.plugins.free_games.ADMIN_DISCORD_ID", "12345"):
            await plugin.force_free_command(mock_ctx)

        # Expected calls:
        # 1. "Checking for free games..." from the command itself.
        # 2. Four game announcements (Steam, Epic, Amazon, valid Reddit link).
        # 3. "Check complete..." message is NOT sent because games were found.

        # Check the initial "Checking..." message
        mock_ctx.send.assert_any_call("Checking for free games...")

        # We expect 4 valid games to be posted:
        # - Great Free Game (Steam)
        # - Awesome Free Game (Epic)
        # - Prime Free Game (Amazon)
        # - Game from Reddit (Steam)
        # - A great game from GOG
        # - A great game from GOG (GOG)
        # - A cool indie game from Itch.io
        # The other 4 posts should be filtered out.
        # The other 5 posts should be filtered out.
        call_count = mock_channel.send.call_count
        logger.info(f"Found {call_count} channel send calls.")
        assert call_count == 6, f"Expected 6 game announcements, but got {call_count}"

        logger.info("OK: Correct number of games (6) were announced.")
        logger.info("Filtered out:")
        logger.info(" - 'Expired Game' (text filter)")
        logger.info(" - 'DLC that requires paid base game' (text filter)")
        logger.info(" - '(DLC) Some Cool Skin Pack' (text filter)")
        logger.info(" - 'Expired game from Reddit' (Reddit flair scraping filter)")
        logger.info(
            " - 'Reddit post linking to excluded domain' (domain filter after Reddit scrape)"
        )

        # --- Test 4: Manual trigger with no new games ---
        logger.info("\n--- Test 4: Manual trigger with no new games ---")
        mock_channel.send.reset_mock()
        mock_ctx.send.reset_mock()

        # Run the check again. Since the posts are now "seen", it should find nothing.
        with patch("familybot.plugins.free_games.ADMIN_DISCORD_ID", "12345"):
            await plugin.force_free_command(mock_ctx)

        # It should not send any game announcements
        mock_channel.send.assert_not_called()
        # It should send the "Check complete" message
        mock_ctx.send.assert_any_call("Check complete. No new free games found.")
        logger.info("OK: Correctly reported no new games found.")

    logger.info("Test Complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test script for the Free Games plugin."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run a live test against real APIs instead of using mock data.",
    )
    args = parser.parse_args()

    asyncio.run(run_live_test() if args.live else main())
