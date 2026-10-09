"""Free games plugin: aggregate free-game listings from multiple sources.

Listings are collected from independent sources (see
:mod:`familybot.lib.free_game_sources`) and normalized into ``FreeGame`` objects,
so a single source going away does not silence the alerts.
"""

import asyncio
from datetime import UTC, datetime

import aiohttp
from interactions import (
    Color,
    Embed,
    Extension,
    IntervalTrigger,
    Task,
    listen,
)
from interactions.ext.prefixed_commands import PrefixedContext, prefixed_command

from familybot.config import ADMIN_DISCORD_ID, EPIC_CHANNEL_ID
from familybot.lib.free_game_sources import (
    CONTENT_BETA,
    CONTENT_DLC,
    CONTENT_GAME,
    CONTENT_ITEM,
    PLATFORM_AMAZON,
    PLATFORM_EPIC,
    PLATFORM_GOG,
    PLATFORM_ITCH,
    PLATFORM_STEAM,
    BlueskySource,
    FreeGame,
    FreeGameSource,
    build_default_sources,
    extract_steam_id,
    url_domain,
)
from familybot.lib.logging_config import get_logger
from familybot.lib.steam_api_manager import SteamAPIManager
from familybot.lib.steam_helpers import fetch_game_details
from familybot.lib.types import FamilyBotClient

# Setup enhanced logging
logger = get_logger(__name__)

# --- Filtering configuration ---
_EXCLUSION_KEYWORDS = (
    "expired",
    "raffle",
    "sweepstake",
)
_EXCLUDED_DOMAINS = (
    "gleam.io",
    "givee.club",
    "woovit",
    "keymailer",
    # Additional "complete tasks to claim" hosts, surfaced now that Bluesky
    # redd.it links are resolved to their real destination (see
    # BlueskySource._fetch_destinations).
    "alienwarearena.com",
    "key-hub.eu",
    "igames.gg",
    "steelseries.com",
    "crucial.com",
)
_PLATFORMS_IN_PRIORITY = (
    PLATFORM_STEAM,
    PLATFORM_EPIC,
    PLATFORM_AMAZON,
    PLATFORM_GOG,
    PLATFORM_ITCH,
)
# Unstructured Bluesky posts must point at one of these before we trust a Steam tag.
_ALLOWED_STEAM_HOSTS = ("store.steampowered.com", "redd.it", "reddit.com")

# --- Display metadata ---
_SOURCE_LABELS = {
    "bluesky": "FreeGameFindings (Bluesky)",
    "gamerpower": "GamerPower (gamerpower.com)",
    "epic": "Epic Games Store",
}

# DLC and in-game items are announced rather than dropped, but clearly labelled
# so users know they are not a full game.
_CONTENT_LABELS = {
    CONTENT_GAME: None,
    CONTENT_DLC: "DLC",
    CONTENT_ITEM: "In-game item",
    CONTENT_BETA: "Beta / playtest",
}
_CONTENT_TITLE_PREFIX = {
    CONTENT_GAME: "FREE: ",
    CONTENT_DLC: "FREE DLC: ",
    CONTENT_ITEM: "FREE ITEM: ",
    CONTENT_BETA: "FREE BETA: ",
}
_CONTENT_ALERTS = {
    CONTENT_GAME: "New Free Game Alert!",
    CONTENT_DLC: "New Free DLC Alert!",
    CONTENT_ITEM: "New Free Item Alert!",
    CONTENT_BETA: "New Free Beta Alert!",
}
_BASE_GAME_MARKERS = (
    "requires paid base game",
    "requires the base game",
    "requires base game",
    "base game required",
)
_PLATFORM_EMBEDS = {
    PLATFORM_EPIC: {
        "store": "Epic Games Store",
        "color": "0078F2",
        "thumbnail": "https://cdn.icon-icons.com/icons2/2699/PNG/128/epic_games_logo_icon_169084.png",
        "description": "Claim this game for free on the Epic Games Store!",
    },
    PLATFORM_AMAZON: {
        "store": "Amazon Prime Gaming",
        "color": "00A8E1",
        "thumbnail": "https://cdn.icon-icons.com/icons2/2699/PNG/128/amazon_prime_gaming_logo_icon_169083.png",
        "description": "Claim this game for free with Amazon Prime Gaming!",
    },
    PLATFORM_GOG: {
        "store": "GOG.com",
        "color": "8A4399",
        "thumbnail": "https://cdn.icon-icons.com/icons2/2428/PNG/512/gog_logo_icon_147232.png",
        "description": "Claim this game for free on GOG.com!",
    },
    PLATFORM_ITCH: {
        "store": "Itch.io",
        "color": "FA5C5C",
        "thumbnail": "https://cdn.icon-icons.com/icons2/2428/PNG/512/itch_io_logo_icon_147227.png",
        "description": "Claim this game for free on Itch.io!",
    },
}


class FreeGames(Extension):
    """Extension to track and announce free games from multiple sources."""

    def __init__(self, bot: FamilyBotClient):
        """Initialize the FreeGames extension."""
        self.bot: FamilyBotClient = bot
        self.steam_api_manager = SteamAPIManager()
        self._sources: list[FreeGameSource] = build_default_sources()
        self._seen_keys: set[str] = set()
        self._seen_titles: set[str] = set()
        self._first_run = True
        logger.info("Free Games Plugin loaded")

    async def _send_admin_dm(self, message: str) -> None:
        """Send error/warning messages to the bot admin via DM."""
        try:
            admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
            if admin_user:
                now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                await admin_user.send(f"Free Games Plugin Error ({now_str}): {message}")
        except Exception as e:
            logger.error(f"Failed to send DM to admin {ADMIN_DISCORD_ID}: {e}")

    @Task.create(IntervalTrigger(minutes=30))
    async def scheduled_free_games_check(self) -> None:
        """Periodically check every free-game source for new listings."""
        await self._process_feed(manual=False, ctx=None)

    # [help]|force_free|Manually triggers a check for new free games across all sources. For Steam games, provides rich embeds.|!force_free|Admin-only. Responds in the invoked channel.  # noqa: E501
    @prefixed_command(name="force_free")
    async def force_free_command(self, ctx: PrefixedContext):
        """Manually trigger the free games check."""
        if str(ctx.author_id) == str(ADMIN_DISCORD_ID):
            await ctx.send("Checking for free games...")
            original_first_run_state = self._first_run
            self._first_run = False
            await self._process_feed(manual=True, ctx=ctx, force_check=True)
            self._first_run = original_first_run_state
            logger.info("Force Free Games update initiated by admin.")
        else:
            await ctx.send("Unauthorized. This command can only be used by the admin.")

    # [help]|show_last_free_games|Displays the last 10 free games found across all sources, with minimal filtering.|!show_last_free_games|Publicly available. Does not affect tracking.  # noqa: E501
    @prefixed_command(name="show_last_free_games")
    async def show_last_free_games_command(self, ctx: PrefixedContext):
        """Display the last 10 free games found across every source."""
        await ctx.send("Fetching last 10 free games...")
        async with aiohttp.ClientSession() as session:
            games = await self._gather_free_games(session)

        if not games:
            await ctx.send("Could not fetch free games at this time.")
            return

        messages = []
        seen_titles: set[str] = set()
        for game in games:
            if not self._passes_filters(game) or game.title_key in seen_titles:
                continue
            seen_titles.add(game.title_key)
            label = _CONTENT_LABELS.get(game.content_type)
            type_line = f"**Type:** {label}\n" if label else ""
            messages.append(
                f"**Platform:** {self._platform_label(game)}\n"
                f"{type_line}"
                f"**Title:** {game.title}\n"
                f"**Link:** {game.url}\n"
                f"**Source:** {_SOURCE_LABELS.get(game.source, game.source)}\n"
                f"----------"
            )
            if len(messages) >= 10:
                break

        if messages:
            await ctx.send("🎮 🌌 **Last Free Games Found:**\n" + "\n".join(messages))
        else:
            await ctx.send("No recent free games found that meet display criteria.")

    async def _gather_free_games(self, session: aiohttp.ClientSession) -> list[FreeGame]:
        """Fetch every source concurrently, tolerating individual failures."""
        results = await asyncio.gather(
            *(source.fetch(session) for source in self._sources),
            return_exceptions=True,
        )
        games: list[FreeGame] = []
        for source, result in zip(self._sources, results, strict=True):
            if isinstance(result, BaseException):
                logger.error("Free-game source %s failed: %s", source.name, result)
                continue
            games.extend(result)
        return games

    @staticmethod
    def _passes_filters(game: FreeGame) -> bool:
        """Apply exclusion keywords, blocked domains, and the platform whitelist."""
        text = game.text.lower()
        if any(keyword in text for keyword in _EXCLUSION_KEYWORDS):
            return False
        # Skip giveaways that require tasks (newsletter/follow/survey/points...),
        # except GOG / Fanatical newsletter sign-ups, which still yield a free game.
        if game.requires_tasks and not game.is_allowed_task_giveaway:
            return False
        domain = url_domain(game.url)
        if any(excluded in domain for excluded in _EXCLUDED_DOMAINS):
            return False
        if not game.platforms.intersection(_PLATFORMS_IN_PRIORITY):
            return False
        # Bluesky posts are unstructured: only trust a Steam tag when it links to
        # an authoritative Steam page or the FGF Reddit thread. Structured sources
        # already carry clean provider links.
        return not (
            game.source == BlueskySource.name
            and PLATFORM_STEAM in game.platforms
            and not any(host in domain for host in _ALLOWED_STEAM_HOSTS)
        )

    @staticmethod
    def _primary_platform(game: FreeGame) -> str | None:
        """Return the highest-priority supported platform for a game, if any."""
        for platform in _PLATFORMS_IN_PRIORITY:
            if platform in game.platforms:
                return platform
        return None

    @staticmethod
    def _platform_label(game: FreeGame) -> str:
        """Human-readable platform list for messages."""
        if not game.platforms:
            return "Game"
        return ", ".join(sorted(game.platforms))

    @staticmethod
    def _source_footer(game: FreeGame) -> str:
        """Footer text naming where a listing came from."""
        return f"Source: {_SOURCE_LABELS.get(game.source, game.source)}"

    @staticmethod
    def _title_prefix(game: FreeGame) -> str:
        """Title prefix that flags DLC / items / betas."""
        return _CONTENT_TITLE_PREFIX.get(game.content_type, _CONTENT_TITLE_PREFIX[CONTENT_GAME])

    @staticmethod
    def _content_note(game: FreeGame) -> str | None:
        """Extra note for DLC / items, e.g. a base-game requirement."""
        if game.content_type not in (CONTENT_DLC, CONTENT_ITEM):
            return None
        text = game.text.lower()
        if any(marker in text for marker in _BASE_GAME_MARKERS):
            return "Requires the base game"
        return None

    def _add_content_fields(self, embed: Embed, game: FreeGame) -> None:
        """Add Type/Note fields so DLC and items are clearly labelled."""
        label = _CONTENT_LABELS.get(game.content_type)
        if label:
            embed.add_field(name="Type", value=label, inline=True)
        note = self._content_note(game)
        if note:
            embed.add_field(name="Note", value=note, inline=True)

    def _steam_embed(self, game: FreeGame, steam_data: dict) -> Embed:
        """Build a rich embed for a Steam giveaway."""
        embed = Embed()
        embed.title = f"{self._title_prefix(game)}{steam_data.get('name', game.title)}"
        embed.url = game.url
        embed.description = steam_data.get("short_description", "No description available.")
        embed.color = Color.from_hex("00FF00")  # Green

        if steam_data.get("header_image"):
            embed.set_image(url=steam_data["header_image"])

        price_overview = steam_data.get("price_overview", {})
        if price_overview:
            original_price = price_overview.get("initial_formatted", "N/A")
            discount = price_overview.get("discount_percent", 0)
            embed.add_field(
                name="Price",
                value=f"~~{original_price}~~ -> FREE ({discount}% off)",
                inline=True,
            )

        if steam_data.get("review_summary"):
            embed.add_field(name="Reviews", value=steam_data["review_summary"], inline=True)

        release_date_data = steam_data.get("release_date")
        if release_date_data and release_date_data.get("date"):
            embed.add_field(name="Release Date", value=release_date_data["date"], inline=True)

        developers = steam_data.get("developers", [])
        publishers = steam_data.get("publishers", [])
        if developers or publishers:
            dev_str = ", ".join(developers) if developers else "N/A"
            pub_str = ", ".join(publishers) if publishers else "N/A"
            embed.add_field(
                name="Creator(s)",
                value=f"**Dev:** {dev_str}\n**Pub:** {pub_str}",
                inline=True,
            )

        self._add_content_fields(embed, game)
        embed.set_footer(text=self._source_footer(game))
        return embed

    def _platform_embed(self, game: FreeGame, platform: str) -> Embed:
        """Build the store-branded embed for a non-Steam platform."""
        meta = _PLATFORM_EMBEDS[platform]
        embed = Embed()
        embed.title = f"{self._title_prefix(game)}{game.title}"
        embed.url = game.url
        embed.color = Color.from_hex(meta["color"])
        embed.description = meta["description"]
        embed.set_thumbnail(url=meta["thumbnail"])
        embed.add_field(name="Platform", value=meta["store"], inline=True)
        self._add_content_fields(embed, game)
        embed.set_footer(text=self._source_footer(game))
        return embed

    def _fallback_message(self, game: FreeGame) -> str:
        """Plain message used when no store-specific embed applies."""
        alert = _CONTENT_ALERTS.get(game.content_type, _CONTENT_ALERTS[CONTENT_GAME])
        details = [f"**Platform:** {self._platform_label(game)}"]
        label = _CONTENT_LABELS.get(game.content_type)
        if label:
            details.append(f"**Type:** {label}")
        note = self._content_note(game)
        if note:
            details.append(f"**Note:** {note}")
        details.extend(
            [
                f"**Title:** {game.title}",
                f"**Link:** {game.url}",
                f"*{self._source_footer(game)}*",
            ]
        )
        return "\n".join([f"🎮 🌌 **{alert}**", *details])

    async def _send_notification(
        self,
        channel,
        game: FreeGame,
        platform: str | None,
        session: aiohttp.ClientSession,
    ) -> bool:
        """Send the best-fitting embed/message for a game. Returns True if sent."""
        if platform == PLATFORM_STEAM:
            steam_id = extract_steam_id(game.url)
            if steam_id:
                steam_data = await fetch_game_details(
                    steam_id, self.steam_api_manager, session=session
                )
                if steam_data:
                    await channel.send(embeds=self._steam_embed(game, steam_data))
                    return True
        elif platform in _PLATFORM_EMBEDS:
            await channel.send(embeds=self._platform_embed(game, platform))
            return True

        # Fallback for non-Steam platforms or a failed Steam detail fetch.
        await channel.send(self._fallback_message(game))
        return True

    async def _process_free_game(
        self,
        game: FreeGame,
        manual: bool,
        ctx: PrefixedContext | None,
        session: aiohttp.ClientSession,
    ) -> bool:
        """Filter, dedupe, and announce a single free game."""
        if game.dedupe_key in self._seen_keys or game.title_key in self._seen_titles:
            return False
        if not self._passes_filters(game):
            return False

        self._seen_keys.add(game.dedupe_key)
        self._seen_titles.add(game.title_key)

        logger.info("Found new free game via %s: %s", game.source, game.title)
        channel = ctx.channel if manual and ctx else await self.bot.fetch_channel(EPIC_CHANNEL_ID)
        if not channel:
            return False
        return await self._send_notification(
            channel, game, self._primary_platform(game), session
        )

    async def _process_feed(  # noqa: C901
        self,
        manual: bool = False,
        ctx: PrefixedContext | None = None,
        force_check: bool = False,
    ) -> None:
        """Gather listings from all sources and announce the new ones."""
        logger.info("Checking free-game sources...")
        try:
            async with aiohttp.ClientSession() as session:
                games = await self._gather_free_games(session)
                if not games:
                    if manual and ctx:
                        await ctx.send("No free games found or error fetching sources.")
                    return

                # On first run, mark everything as seen to avoid spamming old news.
                if self._first_run and not force_check:
                    for game in games:
                        self._seen_keys.add(game.dedupe_key)
                        self._seen_titles.add(game.title_key)
                    self._first_run = False
                    logger.info(
                        "Initialized free-game tracker with %d listings.",
                        len(self._seen_keys),
                    )
                    if manual and ctx:
                        await ctx.send(
                            f"Initialized tracker with {len(self._seen_keys)} existing "
                            "listings. No new notifications sent."
                        )
                    return

                found = 0
                for game in games:
                    if await self._process_free_game(game, manual, ctx, session):
                        found += 1
                        await asyncio.sleep(2)

                if manual and ctx and found == 0:
                    await ctx.send("Check complete. No new free games found.")
        except Exception as e:
            logger.error("Error checking free-game sources: %s", e, exc_info=True)
            if manual and ctx:
                await ctx.send(f"Error occurred during check: {e!s}")

    @listen()
    async def on_startup(self):
        """Start the scheduled free games check task on bot startup."""
        self.scheduled_free_games_check.start()
        logger.info("Free Games tasks started.")


def setup(bot):
    """Set up the FreeGames extension."""
    FreeGames(bot)

