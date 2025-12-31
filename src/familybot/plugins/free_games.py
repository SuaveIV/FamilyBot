import asyncio
import re
from datetime import datetime
from typing import Set
from urllib.parse import urlparse

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

    # -------------------------
    # Bluesky Free Games Logic
    # -------------------------

    @Task.create(IntervalTrigger(minutes=30))
    async def scheduled_bsky_free_games_check(self) -> None:
        """Checks freegamefindings.bsky.social for new free games via Bluesky API."""
        await self._process_feed(manual=False, ctx=None)

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

                excluded_domains = ["gleam.io", "givee.club"]
                if (
                    "expired" in title_lower
                    or "(dlc)" in title_lower
                    or any(
                        excluded_domain in domain
                        for excluded_domain in excluded_domains
                    )
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

    async def _fetch_bluesky_posts(self) -> list:
        """Fetches posts from freegamefindings.bsky.social."""
        bsky_url = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=freegamefindings.bsky.social&limit=10"
        # Use a common browser user-agent to avoid looking like a bot
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        max_retries = 3
        retry_delay = 5
        timeout_seconds = 30

        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        bsky_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=timeout_seconds),
                    ) as response:
                        if response.status != 200:
                            logger.warning(
                                "Bluesky API returned status %s", response.status
                            )
                            # If it's a 5xx error, maybe retry. If 4xx, probably don't.
                            if 500 <= response.status < 600:
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(retry_delay)
                                continue
                            return []
                        data = await response.json()
                        return data.get("feed", [])
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                logger.warning(
                    "Attempt %s/%s failed to fetch Bluesky posts: %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        "Error fetching Bluesky posts after %s attempts: %s",
                        max_retries,
                        e,
                        exc_info=True,
                    )
            except Exception as e:
                logger.error(
                    "Unexpected error fetching Bluesky posts: %s", e, exc_info=True
                )
                return []

        return []

    async def _get_reddit_post_details(self, reddit_url: str) -> dict | None:
        """Fetches details from a Reddit post's JSON endpoint."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        final_url = reddit_url

        try:
            async with aiohttp.ClientSession() as session:
                # If it's a short URL (redd.it), resolve it to the full URL first.
                if "redd.it" in urlparse(final_url).netloc:
                    async with session.head(
                        final_url,
                        headers=headers,
                        allow_redirects=True,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        if response.status == 200:
                            final_url = str(response.url)
                        else:
                            logger.warning(
                                "Failed to resolve redd.it URL %s, status: %s",
                                reddit_url,
                                response.status,
                            )
                            # Continue with original URL as a fallback

                # Now append .json to the (potentially resolved) URL
                if not final_url.endswith(".json"):
                    final_url += ".json"

                async with session.get(
                    final_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "Reddit API returned status %s for %s",
                            response.status,
                            final_url,
                        )
                        return None
                    post_data = await response.json()
                    # The actual post is usually the first item in the first list
                    post = post_data[0]["data"]["children"][0]["data"]
                    return {
                        "link_flair_text": post.get("link_flair_text", ""),
                        "url": post.get("url"),  # The URL the post links to
                    }
        except Exception as e:
            logger.error("Error fetching Reddit post details for %s: %s", final_url, e)
            return None

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

        # Clean URL for deduplication (remove query params)
        if "?" in extracted_url:
            extracted_url = extracted_url.split("?")[0]

        return {
            "platform": platform,
            "title": game_title,
            "url": extracted_url,
            "full_text": full_text,  # Include full text for filtering later if needed
        }

    async def _process_single_post(
        self, post_item: dict, manual: bool, ctx: PrefixedContext | None
    ) -> bool:
        """
        Process a single Bluesky post: filter, extract details, and send notification.
        Returns True if a notification was sent, False otherwise.
        """
        post_record = post_item.get("post", {}).get("record", {})
        post_uri = post_item.get("post", {}).get("uri")

        if not post_uri or post_uri in self._seen_bsky_posts:
            return False

        game_details = self._extract_game_details_from_post(post_item)
        if not game_details:
            logger.debug(
                "Could not extract details for post: %s",
                post_record.get("text", "")[:50],
            )
            return False

        # --- Filtering Logic (re-applied to Bluesky content) ---
        title_lower = game_details["full_text"].lower()
        parsed_url = urlparse(game_details["url"])
        domain = parsed_url.netloc.lower()

        # --- Exclusion Filters ---
        exclusion_keywords = [
            "expired",
            "(dlc)",
            "requires paid base game",
            "raffle",
            "sweepstake",
        ]
        if any(keyword in title_lower for keyword in exclusion_keywords):
            return False

        # Check for domains we want to exclude (e.g., giveaway sites)
        excluded_domains = ["gleam.io", "givee.club"]
        if any(excluded_domain in domain for excluded_domain in excluded_domains):
            return False

        # --- Inclusions (Platform Whitelist) ---
        is_steam = "[steam]" in title_lower
        is_epic = "[epic" in title_lower or "[egs]" in title_lower
        is_amazon = (
            "[amazon]" in title_lower
            or "[luna]" in title_lower
            or "[prime gaming]" in title_lower
        )
        is_gog = "[gog]" in title_lower
        is_itch = "[itch" in title_lower

        if not (is_steam or is_epic or is_amazon or is_gog or is_itch):
            return False

        # --- Specific Logic for "Directly Free" Steam Games ---
        if is_steam:
            is_reddit_link = any(
                d in domain for d in ["redd.it", "reddit.com", "www.reddit.com"]
            )
            is_steam_store_link = "store.steampowered.com" in domain

            if not is_steam_store_link and not is_reddit_link:
                return False

            if is_reddit_link:
                reddit_details = await self._get_reddit_post_details(
                    game_details["url"]
                )
                if not reddit_details:
                    logger.warning(
                        "Could not fetch details from Reddit for %s, skipping.",
                        game_details["url"],
                    )
                    return False

                # Filter based on Reddit flair
                flair_lower = (reddit_details.get("link_flair_text") or "").lower()
                if any(keyword in flair_lower for keyword in exclusion_keywords):
                    logger.info("Skipping Reddit post due to flair: '%s'", flair_lower)
                    return False

                # Update the game URL to the one from the Reddit post for accuracy
                if reddit_details.get("url"):
                    game_details["url"] = reddit_details["url"]
                    # Re-parse domain for Steam store check
                    domain = urlparse(game_details["url"]).netloc.lower()

                    # Re-check the new domain from Reddit against exclusions
                    if any(
                        excluded_domain in domain
                        for excluded_domain in excluded_domains
                    ):
                        logger.info(
                            "Skipping Reddit post linking to excluded domain: %s",
                            domain,
                        )
                        return False

        self._seen_bsky_posts.add(post_uri)  # Use post_uri for deduplication

        logger.info(
            "Found new free game on Bluesky: %s",
            game_details["full_text"].splitlines()[0],
        )

        # If manual, post to context channel, otherwise post to default channel
        channel = (
            ctx.channel
            if manual and ctx
            else await self.bot.fetch_channel(EPIC_CHANNEL_ID)
        )

        if not channel:
            return False

        embed_sent = False
        # Try to fetch rich details for Steam games
        if is_steam:
            steam_id = self._extract_steam_id(game_details["url"])
            if steam_id:
                steam_data = await fetch_game_details(steam_id, self.steam_api_manager)

                if steam_data:
                    # Steam Embed
                    embed = Embed()
                    embed.title = (
                        f"FREE: {steam_data.get('name', game_details['title'])}"
                    )
                    embed.url = game_details["url"]
                    embed.description = steam_data.get(
                        "short_description", "No description available."
                    )
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

                    # --- Add more details inspired by RedditSteamGameInfo ---
                    # Add Reviews
                    if steam_data.get("review_summary"):
                        embed.add_field(
                            name="Reviews",
                            value=steam_data["review_summary"],
                            inline=True,
                        )

                    # Add Release Date
                    release_date_data = steam_data.get("release_date")
                    if release_date_data and release_date_data.get("date"):
                        embed.add_field(
                            name="Release Date",
                            value=release_date_data["date"],
                            inline=True,
                        )

                    # Add Developer/Publisher
                    developers = steam_data.get("developers", [])
                    publishers = steam_data.get("publishers", [])
                    if developers or publishers:
                        dev_str = ", ".join(developers) if developers else "N/A"
                        pub_str = ", ".join(publishers) if publishers else "N/A"
                        dev_pub = f"**Dev:** {dev_str}\n**Pub:** {pub_str}"
                        embed.add_field(name="Creator(s)", value=dev_pub, inline=True)

                    embed.set_footer(
                        text="Source: bsky.app/profile/freegamefindings.bsky.social"
                    )

                    await channel.send(embeds=embed)  # type: ignore
                    embed_sent = True
        elif is_epic:
            # Epic Games Store Embed
            embed = Embed()
            embed.title = f"FREE: {game_details['title']}"
            embed.url = game_details["url"]
            embed.color = Color.from_hex("0078F2")  # Epic Games blue

            embed.description = "Claim this game for free on the Epic Games Store!"
            # Using a generic Epic Games logo thumbnail
            embed.set_thumbnail(
                url="https://cdn.icon-icons.com/icons2/2699/PNG/128/epic_games_logo_icon_169084.png"
            )

            embed.add_field(name="Platform", value="Epic Games Store", inline=True)
            embed.set_footer(
                text="Source: bsky.app/profile/freegamefindings.bsky.social"
            )

            await channel.send(embeds=embed)  # type: ignore
            embed_sent = True
        elif is_amazon:
            # Amazon Prime Gaming Embed
            embed = Embed()
            embed.title = f"FREE: {game_details['title']}"
            embed.url = game_details["url"]
            embed.color = Color.from_hex("00A8E1")  # Amazon Prime blue

            embed.description = "Claim this game for free with Amazon Prime Gaming!"
            # Using a generic Amazon Prime Gaming logo thumbnail
            embed.set_thumbnail(
                url="https://cdn.icon-icons.com/icons2/2699/PNG/128/amazon_prime_gaming_logo_icon_169083.png"
            )

            embed.add_field(name="Platform", value="Amazon Prime Gaming", inline=True)
            embed.set_footer(
                text="Source: bsky.app/profile/freegamefindings.bsky.social"
            )

            await channel.send(embeds=embed)  # type: ignore
            embed_sent = True
        elif is_gog:
            # GOG.com Embed
            embed = Embed()
            embed.title = f"FREE: {game_details['title']}"
            embed.url = game_details["url"]
            embed.color = Color.from_hex("8A4399")  # GOG purple

            embed.description = "Claim this game for free on GOG.com!"
            # Using a generic GOG logo thumbnail
            embed.set_thumbnail(
                url="https://cdn.icon-icons.com/icons2/2428/PNG/512/gog_logo_icon_147232.png"
            )

            embed.add_field(name="Platform", value="GOG.com", inline=True)
            embed.set_footer(
                text="Source: bsky.app/profile/freegamefindings.bsky.social"
            )

            await channel.send(embeds=embed)  # type: ignore
            embed_sent = True
        elif is_itch:
            # Itch.io Embed
            embed = Embed()
            embed.title = f"FREE: {game_details['title']}"
            embed.url = game_details["url"]
            embed.color = Color.from_hex("FA5C5C")  # Itch.io pink

            embed.description = "Claim this game for free on Itch.io!"
            # Using a generic Itch.io logo thumbnail
            embed.set_thumbnail(
                url="https://cdn.icon-icons.com/icons2/2428/PNG/512/itch_io_logo_icon_147227.png"
            )

            embed.add_field(name="Platform", value="Itch.io", inline=True)
            embed.set_footer(
                text="Source: bsky.app/profile/freegamefindings.bsky.social"
            )

            await channel.send(embeds=embed)  # type: ignore
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
            await channel.send(msg)  # type: ignore

        return True

    async def _process_feed(
        self,
        manual: bool = False,
        ctx: PrefixedContext | None = None,
        force_check: bool = False,
    ) -> None:
        """Checks freegamefindings.bsky.social for new free games via Bluesky API."""
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
                    "Initialized Bluesky tracker with %d posts.",
                    len(self._seen_bsky_posts),
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
                if await self._process_single_post(post_item, manual, ctx):
                    games_found += 1
                    await asyncio.sleep(2)

            if manual and ctx and games_found == 0:
                await ctx.send("Check complete. No new free games found.")

        except Exception as e:
            logger.error("Error checking Bluesky: %s", e, exc_info=True)
            if manual and ctx:
                await ctx.send(f"Error occurred during check: {str(e)}")

    @listen()
    async def on_startup(self):
        self.scheduled_bsky_free_games_check.start()
        logger.info("Free Games tasks started.")


def setup(bot):
    FreeGames(bot)
