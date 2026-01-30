import asyncio
import json
import logging
import os
import random
import sys
import time
from typing import Dict, Optional

import httpx

# Add the src directory to the Python path
# This is usually handled by the main application's entry point,
# but included here for potential standalone testing or clarity.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from familybot.config import FAMILY_USER_DICT, STEAMWORKS_API_KEY
from familybot.lib.database import (
    cache_family_library,
    cache_game_details,
    cache_user_games,
    cache_wishlist,
    get_cached_game_details,
    get_cached_wishlist,
    get_db_connection,
)
from familybot.lib.family_utils import find_in_2d_list, get_family_game_list_url
from familybot.lib.logging_config import setup_script_logging

# Setup enhanced logging for this script
logger = setup_script_logging("admin_commands", "INFO")

# Suppress verbose HTTP request logging from httpx
logging.getLogger("httpx").setLevel(logging.WARNING)


class TokenBucket:
    """Token bucket rate limiter for controlling API request rates."""

    def __init__(self, rate: float, capacity: Optional[int] = None):
        """
        Initialize token bucket.

        Args:
            rate: Tokens per second (e.g., 1/1.5 = 0.67 for one request every 1.5 seconds)
            capacity: Maximum tokens in bucket (defaults to rate * 10)
        """
        self.rate = rate
        self.capacity: int = (
            capacity if capacity is not None else max(1, int(rate * 10.0))
        )
        self.tokens: float = float(self.capacity)
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> None:
        """Acquire tokens from the bucket, waiting if necessary."""
        async with self._lock:
            now = time.time()
            # Add tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            # If we don't have enough tokens, wait
            if self.tokens < tokens:
                wait_time = (tokens - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= tokens


class DatabasePopulator:
    """Handles database population with token bucket rate limiting and async processing."""

    def __init__(self, rate_limit_mode: str = "normal"):
        """Initialize the populator with specified rate limiting."""
        self.rate_limits = {
            "fast": {"steam_api": 1.0, "store_api": 1.2},
            "normal": {"steam_api": 1.2, "store_api": 1.5},
            "slow": {"steam_api": 1.8, "store_api": 2.2},
        }

        self.current_limits = self.rate_limits.get(
            rate_limit_mode, self.rate_limits["normal"]
        )

        # Create token bucket rate limiters
        self.steam_bucket = TokenBucket(1.0 / self.current_limits["steam_api"])
        self.store_bucket = TokenBucket(1.0 / self.current_limits["store_api"])

        # Add retry configuration for 429 errors
        self.max_retries = 3
        self.base_backoff = 1.0

        self.client = httpx.AsyncClient(timeout=15.0)

        logger.info(f"Rate limiting mode: {rate_limit_mode}")
        logger.info(f"Steam API: {self.current_limits['steam_api']}s (token bucket)")
        logger.info(f"Store API: {self.current_limits['store_api']}s (token bucket)")
        logger.info(
            f"Retry policy: {self.max_retries} retries with exponential backoff"
        )

    async def close(self):
        """Closes the httpx client session."""
        await self.client.aclose()

    async def make_request_with_retry(
        self, url: str, api_type: str = "steam"
    ) -> Optional[httpx.Response]:
        """Make HTTP request with retry logic for 429 errors."""
        bucket = self.steam_bucket if api_type == "steam" else self.store_bucket

        for attempt in range(self.max_retries + 1):
            try:
                # Acquire token from bucket
                await bucket.acquire()

                # Add jitter to prevent synchronized requests
                jitter = random.uniform(0, 0.1)
                await asyncio.sleep(jitter)

                # Make the request
                response = await self.client.get(url)

                # Check for rate limiting
                if response.status_code == 429:
                    if attempt < self.max_retries:
                        backoff_time = self.base_backoff * (
                            2**attempt
                        ) + random.uniform(0, 1)
                        logger.warning(
                            f"Rate limited (429), retrying in {backoff_time:.1f}s (attempt {attempt + 1}/{self.max_retries + 1})"
                        )
                        await asyncio.sleep(backoff_time)
                        continue
                    else:
                        logger.error(f"Max retries exceeded for {url}")
                        return None

                return response

            except Exception as e:
                if attempt < self.max_retries:
                    backoff_time = self.base_backoff * (2**attempt)
                    logger.warning(
                        f"Request failed: {e}, retrying in {backoff_time:.1f}s"
                    )
                    await asyncio.sleep(backoff_time)
                    continue
                else:
                    logger.error(
                        f"Request failed after {self.max_retries} retries: {e}"
                    )
                    return None

        return None

    def handle_api_response(
        self, api_name: str, response: httpx.Response
    ) -> Optional[dict]:
        """Handle API responses with error checking and enhanced logging."""
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning(f"Rate limited for {api_name}")
            else:
                logger.error(f"HTTP error for {api_name}: {e}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request error for {api_name}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {api_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for {api_name}: {e}")
            return None

    def load_family_members(self) -> Dict[str, str]:
        """Load family members from database or config."""
        members = {}

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Check if we have family members in database
            cursor.execute("SELECT COUNT(*) FROM family_members")
            if cursor.fetchone()[0] == 0 and FAMILY_USER_DICT:
                logger.info("Migrating family members from config to database...")
                for steam_id, name in FAMILY_USER_DICT.items():
                    cursor.execute(
                        "INSERT OR IGNORE INTO family_members (steam_id, friendly_name, discord_id) VALUES (?, ?, ?)",
                        (steam_id, name, None),
                    )
                conn.commit()
                logger.info(f"Migrated {len(FAMILY_USER_DICT)} family members")

            # Load family members
            cursor.execute("SELECT steam_id, friendly_name FROM family_members")
            for row in cursor.fetchall():
                members[row["steam_id"]] = row["friendly_name"]

            conn.close()
            logger.info(f"Loaded {len(members)} family members")

        except Exception as e:
            logger.error(f"Error loading family members: {e}")
            return {}

        return members

    async def populate_family_library(self, dry_run: bool = False) -> int:
        """Populate the shared family library cache."""
        logger.info("Starting family shared library population...")

        if dry_run:
            logger.info("Would fetch shared family library")
            return 0

        try:
            # We need to use requests here because get_family_game_list_url
            # is typically used with requests in this codebase, but we could
            # use our async client if we wanted. For consistency with
            # plugin_admin_actions, we'll fetch then cache.
            url = get_family_game_list_url()
            response = await self.client.get(url)
            games_json = self.handle_api_response("GetSharedLibraryApps", response)

            if not games_json:
                logger.error("Failed to fetch family shared library apps")
                return 0

            game_list = games_json.get("response", {}).get("apps", [])
            if not game_list:
                logger.warning("No apps found in family shared library")
                return 0

            # Cache the library using our new 24h default
            cache_family_library(game_list)
            logger.info(f"Cached {len(game_list)} family library apps")
            return len(game_list)

        except Exception as e:
            logger.error(f"Error populating family shared library: {e}")
            return 0

    async def populate_family_libraries(
        self, family_members: Dict[str, str], dry_run: bool = False
    ) -> int:
        """Populate database with all family member game libraries."""
        logger.info("Starting family library population...")

        if (
            not STEAMWORKS_API_KEY
            or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE"
        ):
            logger.error("Steam API key not configured. Cannot fetch family libraries.")
            return 0

        total_cached = 0
        total_processed = 0

        for steam_id, name in family_members.items():
            logger.info(f"Processing {name}'s library...")

            try:
                owned_games_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAMWORKS_API_KEY}&steamid={steam_id}&include_appinfo=1&include_played_free_games=1"

                if dry_run:
                    logger.info(f"Would fetch owned games for {name}")
                    continue

                response = await self.make_request_with_retry(
                    owned_games_url, api_type="steam"
                )
                if response is None:
                    logger.warning(f"Failed to get games for {name}")
                    continue

                games_data = self.handle_api_response(
                    f"GetOwnedGames ({name})", response
                )

                if not games_data:
                    logger.warning(f"Failed to get games for {name}")
                    continue

                games = games_data.get("response", {}).get("games", [])
                if not games:
                    logger.info(f"No games found for {name} (private profile?)")
                    continue

                logger.info(f"Found {len(games)} games for {name}")

                # Cache the user's game list for !common_games support
                user_appids = [str(g.get("appid")) for g in games if g.get("appid")]
                if user_appids:
                    cache_user_games(steam_id, user_appids)

                user_cached = 0
                user_skipped = 0

                games_to_fetch = []
                for game in games:
                    app_id = str(game.get("appid"))
                    if not app_id:
                        continue

                    total_processed += 1

                    if get_cached_game_details(app_id):
                        user_skipped += 1
                    else:
                        games_to_fetch.append(app_id)

                if games_to_fetch:
                    logger.info(
                        f"Processing {len(games_to_fetch)} new games for {name}..."
                    )

                    async def fetch_game_simple(app_id: str) -> bool:
                        nonlocal user_cached, total_cached

                        game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"

                        try:
                            game_response = await self.make_request_with_retry(
                                game_url, api_type="store"
                            )
                            if game_response is None:
                                return False

                            game_info = self.handle_api_response(
                                f"AppDetails ({app_id})", game_response
                            )

                            if not game_info:
                                return False

                            game_data = game_info.get(str(app_id), {}).get("data")
                            if not game_data:
                                return False

                            cache_game_details(app_id, game_data, permanent=True)
                            user_cached += 1
                            total_cached += 1
                            return True

                        except Exception as e:
                            logger.warning(f"Error processing game {app_id}: {e}")
                            return False

                    batch_size = 5
                    for i in range(0, len(games_to_fetch), batch_size):
                        batch = games_to_fetch[i : i + batch_size]
                        tasks = [fetch_game_simple(app_id) for app_id in batch]
                        await asyncio.gather(*tasks, return_exceptions=True)

                        processed = min(i + batch_size, len(games_to_fetch))
                        logger.debug(
                            f"Progress for {name}: {processed}/{len(games_to_fetch)} | Cached: {user_cached}"
                        )

                logger.info(
                    f"{name}'s library complete: {user_cached} cached, {user_skipped} skipped"
                )

            except Exception as e:
                logger.error(f"Error processing {name}'s library: {e}")
                continue

        logger.info(
            f"Family library population complete! Total games processed: {total_processed}, New games cached: {total_cached}"
        )

        return total_cached

    async def populate_wishlists(
        self, family_members: Dict[str, str], dry_run: bool = False
    ) -> int:
        """Populate database with family member wishlists."""
        logger.info("Starting wishlist population...")

        if (
            not STEAMWORKS_API_KEY
            or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE"
        ):
            logger.error("Steam API key not configured. Cannot fetch wishlists.")
            return 0

        global_wishlist: list[list] = []
        total_cached = 0

        for i, (steam_id, name) in enumerate(family_members.items(), 1):
            logger.info(f"Processing {name}'s wishlist ({i}/{len(family_members)})...")

            try:
                cached_wishlist = get_cached_wishlist(steam_id)
                if cached_wishlist:
                    logger.info(
                        f"Using cached wishlist for {name} ({len(cached_wishlist)} items)"
                    )
                    for app_id in cached_wishlist:
                        idx = find_in_2d_list(app_id, global_wishlist)
                        if idx is not None:
                            global_wishlist[idx][1].append(steam_id)
                        else:
                            global_wishlist.append([app_id, [steam_id]])
                    continue

                if dry_run:
                    logger.info(f"Would fetch wishlist for {name}")
                    continue

                wishlist_url = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?key={STEAMWORKS_API_KEY}&steamid={steam_id}"

                response = await self.make_request_with_retry(
                    wishlist_url, api_type="steam"
                )
                if response is None:
                    logger.warning(f"Failed to get wishlist for {name}")
                    continue

                if response.text == '{"success":2}':
                    logger.info(f"{name}'s wishlist is private or empty")
                    continue

                wishlist_data = self.handle_api_response(
                    f"GetWishlist ({name})", response
                )
                if not wishlist_data:
                    continue

                wishlist_items = wishlist_data.get("response", {}).get("items", [])
                if not wishlist_items:
                    logger.info(f"No items in {name}'s wishlist")
                    continue

                logger.info(f"Found {len(wishlist_items)} wishlist items for {name}")

                user_wishlist_appids = []
                for item in wishlist_items:
                    app_id = str(item.get("appid"))
                    if not app_id:
                        continue

                    user_wishlist_appids.append(app_id)
                    idx = find_in_2d_list(app_id, global_wishlist)
                    if idx is not None:
                        global_wishlist[idx][1].append(steam_id)
                    else:
                        global_wishlist.append([app_id, [steam_id]])

                # Cache the wishlist
                cache_wishlist(steam_id, user_wishlist_appids)
                logger.info(f"{name}'s wishlist cached")

            except Exception as e:
                logger.error(f"Error processing {name}'s wishlist: {e}")
                continue

        common_games = [item for item in global_wishlist if len(item[1]) > 1]
        if not common_games:
            logger.info("No common wishlist games found")
            return 0

        logger.info(f"Processing {len(common_games)} common wishlist games...")

        if dry_run:
            logger.info("Would process common wishlist games for caching")
            return 0

        for i, item in enumerate(common_games):
            app_id = item[0]

            if get_cached_game_details(app_id):
                continue

            try:
                game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"

                response = await self.make_request_with_retry(
                    game_url, api_type="store"
                )
                if response is None:
                    continue

                game_info = self.handle_api_response(f"AppDetails ({app_id})", response)

                if not game_info:
                    continue

                game_data = game_info.get(str(app_id), {}).get("data")
                if not game_data:
                    continue

                cache_game_details(app_id, game_data, permanent=True)
                total_cached += 1

                if (i + 1) % 10 == 0:
                    logger.debug(
                        f"Progress: {i + 1}/{len(common_games)} games processed"
                    )

            except Exception as e:
                logger.warning(f"Error processing game {app_id}: {e}")
                continue

        logger.info(
            f"Wishlist population complete! Common games cached: {total_cached}"
        )

        return total_cached
