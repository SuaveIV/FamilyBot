import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

# Add src to path so we can import familybot
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from familybot.lib.free_game_sources import (
    PLATFORM_AMAZON,
    PLATFORM_EPIC,
    PLATFORM_GOG,
    PLATFORM_ITCH,
    PLATFORM_STEAM,
    FreeGame,
    FreeGameSource,
)
from familybot.lib.types import FamilyBotClient
from familybot.plugins.free_games import FreeGames

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("TestFreeGames")

# --- Mock Data ---


def make_game(
    source: str,
    source_id: str,
    title: str,
    url: str,
    platforms: list[str],
    text: str | None = None,
) -> FreeGame:
    """Build a normalized FreeGame for tests."""
    return FreeGame(
        source=source,
        source_id=source_id,
        title=title,
        url=url,
        platforms=set(platforms),
        text=title if text is None else text,
    )


MOCK_GAMES = [
    # --- Expected to be announced (6) ---
    make_game(
        "epic",
        "epic-1",
        "BURIED STARS",
        "https://store.epicgames.com/en-US/p/buried-stars-d7c88c",
        [PLATFORM_EPIC],
        "BURIED STARS\nA mystery game.",
    ),
    make_game(
        "gamerpower",
        "gp-1",
        "Some Steam Game",
        "https://www.gamerpower.com/open/some-steam-game",
        [PLATFORM_STEAM],
        "Some Steam Game\nGrab it while it lasts.",
    ),
    make_game(
        "bluesky",
        "bsky-1",
        "Great Free Game",
        "https://store.steampowered.com/app/12345",
        [PLATFORM_STEAM],
        "[Steam] (Game) Great Free Game is free!",
    ),
    make_game(
        "bluesky",
        "bsky-2",
        "Prime Free Game",
        "https://gaming.amazon.com/prime-game",
        [PLATFORM_AMAZON],
        "[Amazon] (Game) Prime Free Game is free!",
    ),
    make_game(
        "bluesky",
        "bsky-3",
        "A GOG Game",
        "https://www.gog.com/game/some_game",
        [PLATFORM_GOG],
        "[GOG] (Game) A GOG Game is free!",
    ),
    make_game(
        "bluesky",
        "bsky-4",
        "Cool Indie Game",
        "https://some-dev.itch.io/cool-indie-game",
        [PLATFORM_ITCH],
        "[Itch.io] (Game) Cool Indie Game is free!",
    ),
    make_game(
        "gamerpower",
        "gp-3",
        "Fanatical Spooky Cats Key Giveaway",
        "https://www.gamerpower.com/open/fanatical-spooky-cats",
        [PLATFORM_STEAM],
        "Fanatical Spooky Cats Key Giveaway\nFanatical is giving away keys. "
        "Subscribe to their newsletter and link your Steam account.",
    ),
    make_game(
        "gamerpower",
        "gp-4",
        "GOG Newsletter Giveaway",
        "https://www.gog.com/giveaway/newsletter-game",
        [PLATFORM_GOG],
        "GOG Newsletter Giveaway\nSubscribe to the GOG.com newsletter to claim it.",
    ),
    make_game(
        "gamerpower",
        "gp-6",
        "Fanatical Mega Key Giveaway",
        "https://www.gamerpower.com/open/fanatical-mega-key",
        [PLATFORM_STEAM],
        "Fanatical Mega Key Giveaway\nFanatical is giving away keys! "
        "Subscribe to the newsletter and follow us on X.",
    ),
    make_game(
        "bluesky",
        "bsky-6",
        "Some Skin Pack",
        "https://store.steampowered.com/app/888",
        [PLATFORM_STEAM],
        "[Steam] (DLC) Some Skin Pack is free!\nRequires the base game.",
    ),
    make_game(
        "bluesky",
        "bsky-9",
        "Cool Avatar Pack",
        "https://store.steampowered.com/app/777",
        [PLATFORM_STEAM],
        "[Steam] (Other) Cool Avatar Pack is free!",
    ),
    # --- Expected to be filtered out (5) ---
    make_game(
        "gamerpower",
        "gp-2",
        "Tasky Steam Key Giveaway",
        "https://www.gamerpower.com/open/tasky-steam-key-giveaway",
        [PLATFORM_STEAM],
        "Tasky Steam Key Giveaway\n1. Subscribe to our newsletter and follow us on X.",
    ),
    make_game(
        "bluesky",
        "bsky-5",
        "Expired Game",
        "https://store.steampowered.com/app/999",
        [PLATFORM_STEAM],
        "[Steam] (Game) Expired Game is free!\nThis offer has expired.",
    ),
    make_game(
        "bluesky",
        "bsky-7",
        "Sketchy Steam Game",
        "https://example.com/claim",
        [PLATFORM_STEAM],
        "[Steam] (Game) Sketchy Steam Game is free!",
    ),
    make_game(
        "bluesky",
        "bsky-8",
        "Gleam Game",
        "https://gleam.io/xyz/gleam-game",
        [PLATFORM_STEAM],
        "[Steam] (Game) Gleam Game is free!",
    ),
    make_game(
        "gamerpower",
        "gp-5",
        "Alienware Key Drop",
        "https://www.gamerpower.com/open/alienware-key-drop",
        [PLATFORM_STEAM],
        "Alienware Key Drop\nSubscribe to our newsletter to receive a key.",
    ),
]

MOCK_STEAM_DETAILS = {
    "12345": {"name": "Great Free Game", "short_description": "A truly great game."},
}


class StubSource(FreeGameSource):
    """A source that returns a fixed list of games, for offline testing."""

    def __init__(self, name: str, games: list[FreeGame]):
        self.name = name
        self._games = games

    async def fetch(self, session) -> list[FreeGame]:  # noqa: ARG002
        return list(self._games)


async def mock_fetch_game_details(
    steam_id: str, _steam_api_manager: Any, session: Any = None  # noqa: ARG001
) -> dict[str, Any] | None:
    logger.info(f"[MOCK] fetch_game_details called for Steam ID: {steam_id}")
    return MOCK_STEAM_DETAILS.get(steam_id)


def _build_plugin() -> tuple[FreeGames, MagicMock, MagicMock]:
    """Create a FreeGames plugin wired to a stub source and mock bot."""
    mock_bot = MagicMock(spec=FamilyBotClient)
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()
    mock_bot.fetch_channel = AsyncMock(return_value=mock_channel)
    mock_bot.fetch_user = AsyncMock(return_value=True)
    mock_bot.ext = {}
    mock_bot.add_command = MagicMock()
    mock_bot.add_listener = MagicMock()
    mock_bot.dispatch = MagicMock()

    # SteamAPIManager() performs a network call on construction; stub it out.
    with patch("familybot.plugins.free_games.SteamAPIManager", MagicMock()):
        plugin = cast(FreeGames, FreeGames(mock_bot))
    plugin._sources = [StubSource("stub", MOCK_GAMES)]
    return plugin, mock_bot, mock_channel


async def main():
    logger.info("Starting Free Games Plugin Test...")
    plugin, _mock_bot, mock_channel = _build_plugin()

    with patch(
        "familybot.plugins.free_games.fetch_game_details",
        new=mock_fetch_game_details,
    ):
        # --- Test 1: initialization marks everything as seen ---
        logger.info("--- Test 1: Initialization (mark existing listings as seen) ---")
        await plugin.scheduled_free_games_check()
        mock_channel.send.assert_not_called()
        logger.info("OK: No notifications on first run.")

        # --- Test 2: nothing new ---
        logger.info("--- Test 2: Scheduled run with no new games ---")
        mock_channel.send.reset_mock()
        await plugin.scheduled_free_games_check()
        mock_channel.send.assert_not_called()
        logger.info("OK: No new games, no notifications.")

        # --- Test 3: manual trigger, seen state cleared ---
        logger.info("--- Test 3: Manual trigger with filtering ---")
        mock_channel.send.reset_mock()
        plugin._seen_keys.clear()
        plugin._seen_titles.clear()

        mock_ctx = MagicMock()
        mock_ctx.channel = mock_channel
        mock_ctx.author_id = "12345"
        mock_ctx.send = AsyncMock()

        with patch("familybot.plugins.free_games.ADMIN_DISCORD_ID", "12345"):
            await plugin.force_free_command(mock_ctx)

        mock_ctx.send.assert_any_call("Checking for free games...")
        call_count = mock_channel.send.call_count
        logger.info(f"Found {call_count} channel send calls.")
        assert call_count == 11, f"Expected 11 announcements, but got {call_count}"  # noqa: S101

        logger.info("OK: 11 valid games announced, 5 filtered out.")
        logger.info("Announced with a DLC/item label:")
        logger.info(" - 'Some Skin Pack' (DLC, notes the base-game requirement)")
        logger.info(" - 'Cool Avatar Pack' (In-game item)")
        logger.info("Allowed by the GOG/Fanatical newsletter exception:")
        logger.info(" - 'Fanatical Spooky Cats Key Giveaway' (Fanatical newsletter only)")
        logger.info(" - 'GOG Newsletter Giveaway' (GOG newsletter only)")
        logger.info(" - 'Fanatical Mega Key Giveaway' (Fanatical newsletter + follow)")
        logger.info("Filtered out:")
        logger.info(" - 'Tasky Steam Key Giveaway' (newsletter + follow tasks)")
        logger.info(" - 'Alienware Key Drop' (newsletter, but non-exempt provider)")
        logger.info(" - 'Expired Game' (text filter on 'expired')")
        logger.info(" - 'Sketchy Steam Game' (Steam tag without an allowed host)")
        logger.info(" - 'Gleam Game' (excluded domain gleam.io)")

        # --- Test 4: manual trigger, nothing new ---
        logger.info("--- Test 4: Manual trigger with no new games ---")
        mock_channel.send.reset_mock()
        mock_ctx.send.reset_mock()
        with patch("familybot.plugins.free_games.ADMIN_DISCORD_ID", "12345"):
            await plugin.force_free_command(mock_ctx)

        mock_channel.send.assert_not_called()
        mock_ctx.send.assert_any_call("Check complete. No new free games found.")
        logger.info("OK: Correctly reported no new games found.")

    logger.info("Test Complete.")


async def run_live_test():
    """Runs a live test against the real free-game sources."""
    logger.info("--- Starting LIVE Free Games Plugin Test ---")
    logger.warning("This test makes REAL network requests to all free-game sources.")

    mock_bot = MagicMock(spec=FamilyBotClient)
    mock_channel = MagicMock()

    async def print_to_channel(*args, **kwargs):
        payload = kwargs.get("embeds")
        if payload is None and args:
            payload = args[0]
        if isinstance(payload, list):
            payload = payload[0] if payload else None
        if isinstance(payload, str):
            logger.info(f"[LIVE TEST-CHANNEL SEND] Message: {payload.splitlines()[0]}")
            return
        title = getattr(payload, "title", None)
        if title:
            logger.info(f"[LIVE TEST-CHANNEL SEND] Embed Title: {title}")

    mock_channel.send = AsyncMock(side_effect=print_to_channel)
    mock_bot.fetch_channel = AsyncMock(return_value=mock_channel)
    mock_bot.fetch_user = AsyncMock(return_value=True)
    mock_bot.ext = {}
    mock_bot.add_command = MagicMock()
    mock_bot.add_listener = MagicMock()
    mock_bot.dispatch = MagicMock()

    # SteamAPIManager() performs a network call on construction; stub it out.
    with patch("familybot.plugins.free_games.SteamAPIManager", MagicMock()):
        plugin = cast(FreeGames, FreeGames(mock_bot))

    mock_ctx = MagicMock()
    mock_ctx.channel = mock_channel
    mock_ctx.author_id = "12345"

    async def print_to_ctx(message):
        logger.info(f"[LIVE TEST-CTX SEND] {message}")

    mock_ctx.send = AsyncMock(side_effect=print_to_ctx)

    with patch("familybot.plugins.free_games.ADMIN_DISCORD_ID", "12345"):
        await plugin.force_free_command(mock_ctx)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test script for the Free Games plugin.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run a live test against real APIs instead of using mock data.",
    )
    args = parser.parse_args()

    asyncio.run(run_live_test() if args.live else main())
