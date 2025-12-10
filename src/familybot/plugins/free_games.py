import asyncio
import re
from datetime import datetime
from typing import Set
from urllib.parse import urlparse

import aiohttp
from interactions import Extension, IntervalTrigger, Task, listen, Embed
from interactions.ext.prefixed_commands import PrefixedContext, prefixed_command

from familybot.config import ADMIN_DISCORD_ID, EPIC_CHANNEL_ID
from familybot.lib.logging_config import get_logger
from familybot.lib.types import FamilyBotClient
from familybot.lib.steam_api_manager import SteamAPIManager
from familybot.lib.steam_helpers import fetch_game_details

# Setup enhanced logging
logger = get_logger(__name__)


class FreeGames(Extension):
    def __init__(self, bot: FamilyBotClient):
        self.bot: FamilyBotClient = bot
        self.steam_api_manager = SteamAPIManager()
        logger.info("Free Games Plugin loaded")

        # Bluesky state
        self._seen_bsky_posts: Set[str] = set()
        self._first_bsky_run = True

    async def _send_admin_dm(self, message: str) -> None:
        """Helper to send error/warning messages to the bot admin via DM."""
        try:
            admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
            if admin_user:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await admin_user.send(f"Free Games Plugin Error ({now_str}): {message}")
        except Exception as e:
            logger.error(f"Failed to send DM to admin {ADMIN_DISCORD_ID}: {e}")

    def _extract_steam_id(self, url: str) -> str | None:
        """Extracts the Steam App ID from a store URL."""
        match = re.search(r"store\.steampowered\.com/app/(\d+)", url)
        if match:
            return match.group(1)
        return None

        # [help]|force_free|Manually triggers a check for new free games. For Steam games, provides rich embeds.|!force_free|Admin-only. Responds in the invoked channel.
        @prefixed_command(name="force_free")
        async def force_free_command(self, ctx: PrefixedContext):
            """Manually triggers the Free Games check."""
            # Allow admin to trigger in any channel; responses will go to that channel.
            if str(ctx.author_id) == str(ADMIN_DISCORD_ID):
                await ctx.send("Checking for free games...")
                # For a manual check, we want to see results immediately,
                # so we bypass the _first_bsky_run check by temporarily setting it to False.
                original_first_run_state = self._first_bsky_run
                self._first_bsky_run = False
                await self._process_feed(manual=True, ctx=ctx, force_check=True)
                self._first_bsky_run = original_first_run_state  # Restore state
                logger.info("Force Free Games update initiated by admin.")
            else:
                await ctx.send("Unauthorized. This command can only be used by the admin.")
    
        async def _fetch_bluesky_posts(self) -> list:
            """Fetches posts from freegamefindings.bsky.social."""
            bsky_url = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=freegamefindings.bsky.social&limit=10"
            # Use a common browser user-agent to avoid looking like a bot
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        bsky_url, headers=headers, timeout=15
                    ) as response:
                        if response.status != 200:
                            logger.warning(f"Bluesky API returned status {response.status}")
                            return []
                        data = await response.json()
                        return data.get("feed", [])
            except Exception as e:
                logger.error(f"Error fetching Bluesky posts: {e}", exc_info=True)
                return []
    
        def _extract_game_details_from_post(self, post_item: dict) -> dict | None:
            """Extracts game details (platform, title, URL) from a raw Bluesky post item."""
            post_record = post_item.get("post", {}).get("record", {})
            full_text = post_record.get("text", "")
            post_uri = post_item.get("post", {}).get("uri")
    
            if not post_uri:
                return None
    
            # Skip reply posts
            if post_record.get("reply"):
                return None
    
            platform = "Game"
            game_title = full_text.split("\n")[0].strip()  # Default to first line
    
            title_match = re.search(r"\[(.*?)\]\s*(.*?)is free", full_text, re.IGNORECASE)
            if title_match:
                platform = title_match.group(1).strip()
                game_title = title_match.group(2).strip()
            else:
                platform_match = re.search(r"\[(.*?)\]", full_text)
                if platform_match:
                    platform = platform_match.group(1).strip()
                    game_title = (
                        full_text.replace(f"[{platform}]", "").strip().split("\n")[0]
                    )
    
            extracted_url = None
            for facet in post_record.get("facets", []):
                for feature in facet.get("features", []):
                    if feature.get("$type") == "app.bsky.richtext.facet#link":
                        extracted_url = feature.get("uri")
                        break
                if extracted_url:
                    break
    
            if not extracted_url:
                url_pattern = r"(https?://[^\s]+)"
                urls_in_text = re.findall(url_pattern, full_text)
                if urls_in_text:
                    extracted_url = urls_in_text[0]
    
            if not extracted_url:
                return None
    
            return {
                "platform": platform,
                "title": game_title,
                "url": extracted_url,
                "full_text": full_text,  # Include full text for filtering later if needed
            }
        
        # [help]|show_last_free_games|Displays the last 10 free games found on freegamefindings.bsky.social, with minimal filtering.|!show_last_free_games|Publicly available. Does not affect tracking.
        @prefixed_command(name="show_last_free_games")
        async def show_last_free_games_command(self, ctx: PrefixedContext):
            """Displays the last 10 free games found on freegamefindings.bsky.social."""
            await ctx.send("Fetching last 10 free games...")
            posts = await self._fetch_bluesky_posts()
            
            if not posts:
                await ctx.send("Could not fetch free games at this time.")
                return
        game_messages = []
        for post_item in posts:
            game_details = self._extract_game_details_from_post(post_item)
            if game_details:
                # Apply minimal filtering for display: no expired, no gleam.io, no raffles
                title_lower = game_details["full_text"].lower()
                parsed_url = urlparse(game_details["url"])
                domain = parsed_url.netloc.lower()

                if (
                    "expired" in title_lower
                    or "gleam.io" in domain
                    or "raffle" in title_lower
                    or "sweepstake" in title_lower
                ):
                    continue  # Skip these for cleaner display

                msg = (
                    f"**Platform:** {game_details['platform']}\n"
                    f"**Game:** {game_details['title']}\n"
                    f"**Link:** {game_details['url']}\n"
                    f"----------"
                )
                game_messages.append(msg)

            if len(game_messages) >= 10:  # Only show up to 10
                break

        if game_messages:
            full_message = (
                "\ud83c\udfae \ud83c\udf0c **Last Free Games Found (Bluesky):**\n"
                + "\n".join(game_messages)
            )
            await ctx.send(full_message)
        else:
            await ctx.send("No recent free games found that meet display criteria.")

    # -------------------------
    # Bluesky Free Games Logic
    # -------------------------

    @Task.create(IntervalTrigger(minutes=30))
    async def scheduled_bsky_free_games_check(self) -> None:
        """Checks freegamefindings.bsky.social for new free games via Bluesky API."""
        await self._process_feed(manual=False)

    async def _process_feed(
        self,
        manual: bool = False,
        ctx: PrefixedContext = None,
        force_check: bool = False,
    ) -> None:
        """Core logic to check Bluesky feed."""
        logger.info("Checking freegamefindings.bsky.social...")

        try:
            posts = await self._fetch_bluesky_posts()

            if not posts:
                if manual and ctx:
                    await ctx.send("No posts found in feed or error fetching feed.")
                return

            # On first run, just mark everything as seen to prevent spamming old news
            if self._first_bsky_run and not force_check:
                for post_item in posts:
                    post_uri = post_item.get("post", {}).get("uri")
                    if post_uri:
                        self._seen_bsky_posts.add(post_uri)
                self._first_bsky_run = False
                logger.info(
                    f"Initialized Bluesky tracker with {len(self._seen_bsky_posts)} posts."
                )
                if manual and ctx:
                    await ctx.send(
                        f"Initialized tracker with {len(self._seen_bsky_posts)} existing posts. No new notifications sent."
                    )
                return

            games_found = 0
            # Process posts (newest first in API response, so process in reverse to get oldest new ones first)
            # If it's a forced check, process all posts. Otherwise, only process new ones.
            posts_to_process = reversed(posts) if force_check else posts

            for post_item in posts_to_process:
                post_record = post_item.get("post", {}).get("record", {})
                post_uri = post_item.get("post", {}).get("uri")

                if not post_uri or post_uri in self._seen_bsky_posts:
                    continue

                game_details = self._extract_game_details_from_post(post_item)
                if not game_details:
                    logger.debug(
                        f"Could not extract details for post: {post_record.get('text', '')[:50]}"
                    )
                    continue

                # --- Filtering Logic (re-applied to Bluesky content) ---
                title_lower = game_details["full_text"].lower()
                parsed_url = urlparse(game_details["url"])
                domain = parsed_url.netloc.lower()

                # Check for "Expired" (link_flair_text not directly available in bsky record like reddit json)
                # We rely on text parsing for "expired"
                if (
                    "expired" in title_lower
                ):  # FGF posts often update title with [EXPIRED]
                    continue

                if "gleam.io" in domain:
                    continue

                if "raffle" in title_lower or "sweepstake" in title_lower:
                    continue

                # --- Inclusions (Platform Whitelist) ---
                is_steam = "[steam]" in title_lower
                is_epic = (
                    "[epic" in title_lower or "[egs]" in title_lower
                )  # Matches [Epic Games], [Epic], [EGS]
                is_amazon = (
                    "[amazon]" in title_lower
                    or "[luna]" in title_lower
                    or "[prime gaming]" in title_lower
                )

                if not (is_steam or is_epic or is_amazon):
                    continue

                # --- Specific Logic for "Directly Free" Steam Games ---
                # Exclude key giveaways on other sites, strictly allow store.steampowered.com OR reddit links (which we assume link to the store)
                if is_steam:
                    allowed_steam_domains = [
                        "store.steampowered.com",
                        "redd.it",
                        "reddit.com",
                        "www.reddit.com",
                    ]
                    if not any(d in domain for d in allowed_steam_domains):
                        continue

                self._seen_bsky_posts.add(post_uri)  # Use post_uri for deduplication

                logger.info(
                    f"Found new free game on Bluesky: {game_details['full_text'].splitlines()[0]}"
                )

                # If manual, post to context channel, otherwise post to default channel
                channel = (
                    ctx.channel
                    if manual and ctx
                    else await self.bot.fetch_channel(EPIC_CHANNEL_ID)
                )

                if channel:
                    embed_sent = False
                    # Try to fetch rich details for Steam games
                    if is_steam:
                        steam_id = self._extract_steam_id(game_details["url"])
                        if steam_id:
                            steam_data = await fetch_game_details(
                                steam_id, self.steam_api_manager
                            )
                            if steam_data:
                                embed = Embed(
                                    title=f"FREE: {steam_data.get('name', game_details['title'])}",
                                    url=game_details["url"],
                                    description=steam_data.get(
                                        "short_description", "No description available."
                                    ),
                                    color=0x00FF00,  # Green
                                )
                                if steam_data.get("header_image"):
                                    embed.set_image(url=steam_data["header_image"])

                                price_overview = steam_data.get("price_overview", {})
                                if price_overview:
                                    original_price = price_overview.get(
                                        "initial_formatted", "N/A"
                                    )
                                    discount = price_overview.get("discount_percent", 0)
                                    embed.add_field(
                                        name="Price",
                                        value=f"~~{original_price}~~ -> FREE ({discount}% off)",
                                        inline=True,
                                    )

                                embed.set_footer(
                                    text=f"Source: bsky.app/profile/freegamefindings.bsky.social"
                                )

                                await channel.send(embeds=embed)
                                embed_sent = True

                    # Fallback for non-Steam or failed Steam fetch
                    if not embed_sent:
                        msg = (
                            f"🎮 🌌 **New Free Game Alert (Bluesky)!**\n"
                            f"**Platform:** {game_details['platform']}\n"
                            f"**Game:** {game_details['title']}\n"
                            f"**Link:** {game_details['url']}\n"
                            f"*Source: <https://bsky.app/profile/freegamefindings.bsky.social>*"
                        )
                        await channel.send(msg)

                    games_found += 1
                    await asyncio.sleep(2)

            if manual and ctx and games_found == 0:
                await ctx.send("Check complete. No new free games found.")

        except Exception as e:
            logger.error(f"Error checking Bluesky: {e}", exc_info=True)
            if manual and ctx:
                await ctx.send(f"Error occurred during check: {str(e)}")

    @listen()
    async def on_startup(self):
        self.scheduled_bsky_free_games_check.start()
        logger.info("Free Games tasks started.")


def setup(bot):
    FreeGames(bot)
