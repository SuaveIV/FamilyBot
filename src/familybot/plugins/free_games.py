"""Free games plugin monitoring GamerPower API."""

import asyncio
from datetime import UTC, datetime
from urllib.parse import urlparse

import aiohttp
from interactions import (
    Extension,
    IntervalTrigger,
    Task,
    listen,
)
from interactions.ext.prefixed_commands import PrefixedContext, prefixed_command

from familybot.config import ADMIN_DISCORD_ID, EPIC_CHANNEL_ID
from familybot.lib.logging_config import get_logger
from familybot.lib.types import FamilyBotClient

# Setup enhanced logging
logger = get_logger(__name__)


class FreeGames(Extension):
    """Extension to track and announce free games."""

    def __init__(self, bot: FamilyBotClient):
        """Initialize the FreeGames extension."""
        self.bot: FamilyBotClient = bot
        logger.info("Free Games Plugin loaded")

        # GamerPower state
        self._seen_giveaways: set[int] = set()
        self._first_run = True

    async def _send_admin_dm(self, message: str) -> None:
        """Send error/warning messages to the bot admin via DM."""
        try:
            admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
            if admin_user:
                now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                await admin_user.send(f"Free Games Plugin Error ({now_str}): {message}")
        except Exception as e:
            logger.error(f"Failed to send DM to admin {ADMIN_DISCORD_ID}: {e}")

    # -------------------------
    # GamerPower Free Games Logic
    # -------------------------

    @Task.create(IntervalTrigger(minutes=30))
    async def scheduled_free_games_check(self) -> None:
        """Check GamerPower for new free games via the GamerPower API."""
        await self._process_feed(manual=False, ctx=None)

    # [help]|force_free|Manually triggers a check for new free games.|!force_free|Admin-only.
    @prefixed_command(name="force_free")
    async def force_free_command(self, ctx: PrefixedContext):
        """Manually triggers the Free Games check."""
        if str(ctx.author_id) == str(ADMIN_DISCORD_ID):
            await ctx.send("Checking for free games...")
            original_first_run_state = self._first_run
            self._first_run = False
            await self._process_feed(manual=True, ctx=ctx, force_check=True)
            self._first_run = original_first_run_state  # Restore state
            logger.info("Force Free Games update initiated by admin.")
        else:
            await ctx.send("Unauthorized. This command can only be used by the admin.")

    # [help]|show_last_free_games|Show 10 free games on GamerPower.|!show_last_free_games|Public.
    @prefixed_command(name="show_last_free_games")
    async def show_last_free_games_command(self, ctx: PrefixedContext):
        """Display the last 10 free games found on GamerPower."""
        await ctx.send("Fetching last 10 free games...")
        async with aiohttp.ClientSession() as session:
            giveaways = await self._fetch_gamerpower_giveaways(session)

        if not giveaways:
            await ctx.send("Could not fetch free games at this time.")
            return

        valid_giveaways = []
        for g in giveaways:
            # Minimal filtering for display
            platforms_lower = g.get("platforms", "").lower()
            type_lower = g.get("type", "").lower()

            is_game = type_lower in ["game", "early access"]
            is_steam = "steam" in platforms_lower
            is_epic = "epic" in platforms_lower
            is_gog = "gog" in platforms_lower
            is_itch = "itch" in platforms_lower
            is_amazon = "amazon" in platforms_lower or "prime" in platforms_lower

            if (is_steam or is_epic or is_gog or is_itch or is_amazon) and is_game:
                valid_giveaways.append(g)
                if len(valid_giveaways) >= 10:
                    break

        if not valid_giveaways:
            await ctx.send("No recent free games found that meet display criteria.")
            return

        game_messages = []
        for g in valid_giveaways:
            msg = (
                f"**Platform:** {g.get('platforms')}\n"
                f"**Game:** {g.get('title')}\n"
                f"**Link:** {g.get('gamerpower_url')}\n"
                f"----------"
            )
            game_messages.append(msg)

        full_message = "🎮 🌌 **Last Free Games Found (GamerPower):**\n" + "\n".join(game_messages)
        await ctx.send(full_message)

    async def _fetch_gamerpower_giveaways(self, session: aiohttp.ClientSession) -> list:
        """Fetch active giveaways from GamerPower API."""
        url = "https://www.gamerpower.com/api/giveaways"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        max_retries = 3
        retry_delay = 5
        timeout_seconds = 30

        for attempt in range(max_retries):
            try:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds),
                ) as response:
                    if response.status != 200:
                        logger.warning("GamerPower API returned status %s", response.status)
                        if 500 <= response.status < 600:
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay)
                            continue
                        return []
                    return await response.json()
            except (TimeoutError, aiohttp.ClientError) as e:
                logger.warning(
                    "Attempt %s/%s failed to fetch GamerPower giveaways: %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        "Error fetching GamerPower giveaways after %s attempts: %s",
                        max_retries,
                        e,
                        exc_info=True,
                    )
            except Exception as e:
                logger.error("Unexpected error fetching GamerPower giveaways: %s", e, exc_info=True)
                return []

        return []

    async def _resolve_redirect_url(self, url: str, session: aiohttp.ClientSession) -> str | None:
        """Resolve a redirect URL to the destination store page."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        try:
            async with session.get(
                url,
                headers=headers,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    return str(response.url)
                logger.warning(
                    "Redirect resolved with status %s for %s",
                    response.status,
                    url,
                )
        except Exception as e:
            logger.error("Error resolving redirect for %s: %s", url, e)
        return None

    def _is_valid_store_domain(
        self,
        domain: str,
        is_steam: bool,
        is_epic: bool,
        is_gog: bool,
        is_itch: bool,
    ) -> bool:
        """Check if the resolved domain matches the whitelisted platform domain."""
        if is_steam and "store.steampowered.com" not in domain:
            return False
        if is_epic and "epicgames.com" not in domain:
            return False
        if is_gog and "gog.com" not in domain:
            return False
        return not (is_itch and "itch.io" not in domain)

    async def _process_single_giveaway(
        self,
        giveaway: dict,
        manual: bool,
        ctx: PrefixedContext | None,
        session: aiohttp.ClientSession,
    ) -> bool:
        """Process a single GamerPower giveaway.

        Filter, resolve direct links, and send notification.
        Returns True if a notification was sent, False otherwise.
        """
        giveaway_id = giveaway.get("id")
        if not giveaway_id or giveaway_id in self._seen_giveaways:
            return False

        # --- Basic Filtering ---
        if giveaway.get("status") != "Active":
            return False

        type_lower = giveaway.get("type", "").lower()
        if type_lower not in ["game", "early access"]:
            return False

        platforms_lower = giveaway.get("platforms", "").lower()
        is_steam = "steam" in platforms_lower
        is_epic = "epic" in platforms_lower
        is_gog = "gog" in platforms_lower
        is_itch = "itch" in platforms_lower
        is_amazon = "amazon" in platforms_lower or "prime" in platforms_lower

        if not (is_steam or is_epic or is_gog or is_itch or is_amazon):
            return False

        # --- Resolve Redirect Link ---
        open_url = giveaway.get("open_giveaway_url") or giveaway.get("open_giveaway")
        if not open_url:
            return False

        final_url = await self._resolve_redirect_url(open_url, session)
        if not final_url:
            logger.warning(
                "Could not resolve destination URL for giveaway %d, skipping.",
                giveaway_id,
            )
            return False

        parsed_url = urlparse(final_url)
        domain = parsed_url.netloc.lower()

        # --- Verify domain match (to filter out raffles/third-party sites) ---
        if not self._is_valid_store_domain(domain, is_steam, is_epic, is_gog, is_itch):
            logger.info(
                "Skipping giveaway %d: redirected to non-matching domain %s",
                giveaway_id,
                domain,
            )
            return False

        self._seen_giveaways.add(giveaway_id)

        logger.info(
            "Found new free game on GamerPower: %s",
            giveaway.get("title"),
        )

        channel = ctx.channel if manual and ctx else await self.bot.fetch_channel(EPIC_CHANNEL_ID)

        if not channel:
            return False

        # Post clean plain text message and let Discord generate the preview
        msg = (
            f"🎮 🌌 **New Free Game Alert!**\n"
            f"**Platform:** {giveaway.get('platforms', 'PC')}\n"
            f"**Game:** {giveaway.get('title')}\n"
            f"**Link:** {final_url}\n"
            f"*Source: <https://www.gamerpower.com/>*"
        )
        await channel.send(msg)  # type: ignore[union-attr]

        return True

    def _initialize_tracker(self, giveaways: list) -> None:
        """Initialize the giveaway tracker with current active giveaways."""
        for g in giveaways:
            g_id = g.get("id")
            if g_id:
                self._seen_giveaways.add(g_id)
        self._first_run = False
        logger.info(
            "Initialized GamerPower tracker with %d giveaways.",
            len(self._seen_giveaways),
        )

    async def _process_feed(
        self,
        manual: bool = False,
        ctx: PrefixedContext | None = None,
        force_check: bool = False,
    ) -> None:
        """Check GamerPower for new free games."""
        logger.info("Checking GamerPower...")

        try:
            async with aiohttp.ClientSession() as session:
                giveaways = await self._fetch_gamerpower_giveaways(session)

                if not giveaways:
                    if manual and ctx:
                        await ctx.send("No giveaways found or error fetching feed.")
                    return

                # On first run, mark everything as seen to prevent spamming old news
                if self._first_run and not force_check:
                    self._initialize_tracker(giveaways)
                    if manual and ctx:
                        msg = (
                            f"Initialized tracker with {len(self._seen_giveaways)} "
                            "existing giveaways. No new notifications sent."
                        )
                        await ctx.send(msg)
                    return

                games_found = 0
                # GamerPower API returns items ordered by publish date (newest first).
                # We process them in reverse (oldest first) to post them in chronological order.
                giveaways_to_process = reversed(giveaways) if force_check else giveaways

                for g in giveaways_to_process:
                    if await self._process_single_giveaway(g, manual, ctx, session):
                        games_found += 1
                        await asyncio.sleep(2)

                if manual and ctx and games_found == 0:
                    await ctx.send("Check complete. No new free games found.")

        except Exception as e:
            logger.error("Error checking GamerPower: %s", e, exc_info=True)
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
