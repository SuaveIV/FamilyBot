import asyncio
import re
from datetime import datetime
from typing import Set
from urllib.parse import urlparse

import aiohttp
from interactions import Extension, IntervalTrigger, Task, listen
from interactions.ext.prefixed_commands import PrefixedContext, prefixed_command

from familybot.config import ADMIN_DISCORD_ID, EPIC_CHANNEL_ID
from familybot.lib.logging_config import get_logger
from familybot.lib.types import FamilyBotClient

# Setup enhanced logging
logger = get_logger(__name__)


class FreeGames(Extension):
    def __init__(self, bot: FamilyBotClient):
        self.bot: FamilyBotClient = bot
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

    @prefixed_command(name="force_free")
    async def force_free_command(self, ctx: PrefixedContext):
        """Manually triggers the Free Games check."""
        if str(ctx.author_id) == str(ADMIN_DISCORD_ID) and ctx.guild is None:
            await ctx.send("Queued Free Games check for next minute interval (or immediate if logic allows).")
            # We can't easily "force" the task to run immediately if it's sleeping, 
            # but we can call the logic directly or just wait for the interval.
            # For simplicity, let's just run the logic method directly as a task
            asyncio.create_task(self.check_bsky_free_games())
            logger.info("Force Free Games update initiated by admin.")
        else:
            await ctx.send("Unauthorized or not in DM.")

    # -------------------------
    # Bluesky Free Games Logic
    # -------------------------

    @Task.create(IntervalTrigger(minutes=30))
    async def check_bsky_free_games(self) -> None:
        """Checks freegamefindings.bsky.social for new free games via Bluesky API."""
        logger.info("Checking freegamefindings.bsky.social...")
        
        bsky_url = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=freegamefindings.bsky.social&limit=10"
        headers = {
            "User-Agent": "FamilyBot/1.0 (by /u/YourDiscordBotName)" 
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(bsky_url, headers=headers, timeout=15) as response:
                    if response.status != 200:
                        logger.warning(f"Bluesky API returned status {response.status}")
                        return
                    
                    data = await response.json()
                    posts = data.get("feed", [])

            if not posts:
                return

            # On first run, just mark everything as seen to prevent spamming old news
            if self._first_bsky_run:
                for post_item in posts:
                    post_uri = post_item.get("post", {}).get("uri")
                    if post_uri:
                        self._seen_bsky_posts.add(post_uri)
                self._first_bsky_run = False
                logger.info(f"Initialized Bluesky tracker with {len(self._seen_bsky_posts)} posts.")
                return

            # Process posts (newest first in API response, so process in reverse to get oldest new ones first)
            for post_item in reversed(posts):
                post_record = post_item.get("post", {}).get("record", {})
                post_uri = post_item.get("post", {}).get("uri")
                full_text = post_record.get("text", "")

                if not post_uri or post_uri in self._seen_bsky_posts:
                    continue
                
                # Skip reply posts
                if post_record.get("reply"):
                    continue

                # The post.record.text often contains the full title and a direct link, sometimes also the redd.it link.
                # We need to extract the title and the primary URL.
                title_match = re.search(r"\[(.*?)\]\s*(.*?)is free", full_text, re.IGNORECASE)
                if title_match:
                    platform = title_match.group(1).strip()
                    game_title = title_match.group(2).strip()
                else:
                    # Fallback for posts that don't match the specific "[Platform] (Game) is free" format
                    platform_match = re.search(r"\[(.*?)\]", full_text)
                    platform = platform_match.group(1).strip() if platform_match else "Game"
                    game_title = full_text.split('\n')[0].replace(f"[{platform}]", "").strip()

                # Extract URL - prioritize direct game links, fall back to redd.it if only option.
                # URLs are in facets or simply in the text.
                extracted_url = None
                for facet in post_record.get("facets", []):
                    for feature in facet.get("features", []):
                        if feature.get("$type") == "app.bsky.richtext.facet#link":
                            link_uri = feature.get("uri")
                            if link_uri and "redd.it" not in link_uri: # Prioritize non-Reddit links
                                extracted_url = link_uri
                                break
                    if extracted_url:
                        break

                if not extracted_url: # If no direct link from facets, try regex in text
                    url_pattern = r"(https?://[^\s]+)"
                    urls_in_text = re.findall(url_pattern, full_text)
                    for u in urls_in_text:
                        if "redd.it" not in u: # Prioritize non-Reddit links from text
                            extracted_url = u
                            break
                    if not extracted_url and urls_in_text: # If only reddit links are found and no other, take the first one
                        extracted_url = urls_in_text[0]
                
                # If still no URL, skip
                if not extracted_url:
                    logger.debug(f"Skipping post due to no discernible URL: {full_text[:50]}")
                    continue

                # --- Filtering Logic (re-applied to Bluesky content) ---
                title_lower = full_text.lower()
                # Bluesky posts don't have a direct 'domain' field like Reddit's .json, 
                # so we derive it from the extracted URL for filtering.
                parsed_url = urlparse(extracted_url)
                domain = parsed_url.netloc.lower()
                
                # Check for "Expired" (link_flair_text not directly available in bsky record like reddit json)
                # We rely on text parsing for "expired"
                if "expired" in title_lower: # FGF posts often update title with [EXPIRED]
                    continue

                if "gleam.io" in domain:
                    continue
                
                if "raffle" in title_lower or "sweepstake" in title_lower:
                    continue

                # --- Inclusions (Platform Whitelist) ---
                is_steam = "[steam]" in title_lower
                is_epic = "[epic" in title_lower or "[egs]" in title_lower  # Matches [Epic Games], [Epic], [EGS]
                is_amazon = "[amazon]" in title_lower or "[luna]" in title_lower or "[prime gaming]" in title_lower

                if not (is_steam or is_epic or is_amazon):
                    continue

                # --- Specific Logic for "Directly Free" Steam Games ---
                # Exclude key giveaways on other sites, strictly allow store.steampowered.com
                if is_steam and "store.steampowered.com" not in domain:
                    continue

                self._seen_bsky_posts.add(post_uri) # Use post_uri for deduplication

                logger.info(f"Found new free game on Bluesky: {full_text.split('\n')[0]}")
                
                channel = await self.bot.fetch_channel(EPIC_CHANNEL_ID)
                if channel:
                    msg = (
                        f"\ud83c\udfae \ud83c\udf0c **New Free Game Alert (Bluesky)!**\n"
                        f"**Platform:** {platform}\n"
                        f"**Game:** {game_title}\n"
                        f"**Link:** {extracted_url}\n"
                        f"*Source: {bsky_url.split('?')[0].replace('public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed', 'bsky.app/profile')}"
                    )
                    await self.bot.send_to_channel(EPIC_CHANNEL_ID, msg)
                    
                    await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"Error checking Bluesky: {e}", exc_info=True)

    @listen()
    async def on_startup(self):
        self.check_bsky_free_games.start()
        logger.info("Free Games tasks started.")


def setup(bot):
    FreeGames(bot)