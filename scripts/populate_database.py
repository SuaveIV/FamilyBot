import os
import sys
import time
import random
import json
import argparse
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional
import httpx

from steam.webapi import WebAPI
from typing import Tuple

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from familybot.config import FAMILY_USER_DICT, STEAMWORKS_API_KEY  # pylint: disable=wrong-import-position
from familybot.lib.database import (
    cache_family_library,
    cache_game_details,  # pylint: disable=wrong-import-position
    cache_user_games,
    cache_wishlist,
    get_cached_game_details,
    get_cached_wishlist,
    get_db_connection,
    init_db,
)
from familybot.lib.family_utils import find_in_2d_list, get_family_game_list_url  # pylint: disable=wrong-import-position
from familybot.lib.logging_config import setup_script_logging  # pylint: disable=wrong-import-position

try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    print("⚠️  tqdm not available. Install with: uv pip install tqdm")
    print("   Falling back to basic progress indicators...")
    TQDM_AVAILABLE = False

# Setup enhanced logging for this script
logger = setup_script_logging("populate_database", "INFO")

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

        # Initialize Steam WebAPI if available
        self.steam_api = None
        if STEAMWORKS_API_KEY and STEAMWORKS_API_KEY != "YOUR_STEAMWORKS_API_KEY_HERE":
            try:
                self.steam_api = WebAPI(key=STEAMWORKS_API_KEY)
                print("🔧 Steam WebAPI initialized successfully")
            except (ValueError, TypeError, OSError, ImportError) as e:
                logger.warning("Failed to initialize Steam WebAPI: %s", e)
                self.steam_api = None

        print(f"🔧 Rate limiting mode: {rate_limit_mode}")
        print(f"   Steam API: {self.current_limits['steam_api']}s (token bucket)")
        print(f"   Store API: {self.current_limits['store_api']}s (token bucket)")
        print(f"   Retry policy: {self.max_retries} retries with exponential backoff")

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
                            "Rate limited (429), retrying in %.1fs (attempt %d/%d)",
                            backoff_time,
                            attempt + 1,
                            self.max_retries + 1,
                        )
                        await asyncio.sleep(backoff_time)
                        continue
                    logger.error("Max retries exceeded for %s", url)
                    return None

                return response

            except (httpx.RequestError, httpx.TimeoutException, OSError) as e:
                if attempt < self.max_retries:
                    backoff_time = self.base_backoff * (2**attempt)
                    logger.warning(
                        "Request failed: %s, retrying in %.1f s", e, backoff_time
                    )
                    await asyncio.sleep(backoff_time)
                    continue
                logger.error("Request failed after %d retries: %s", self.max_retries, e)
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
                logger.warning("Rate limited for %s", api_name)
            else:
                logger.error("HTTP error for %s: %s", api_name, e)
            return None
        except httpx.RequestError as e:
            logger.error("Request error for %s: %s", api_name, e)
            return None
        except json.JSONDecodeError as e:
            logger.error("JSON decode error for %s: %s", api_name, e)
            return None
        except (ValueError, TypeError, KeyError) as e:
            logger.error("Unexpected error for %s: %s", api_name, e)
            return None

    def batch_write_games(self, games_data: Dict[str, Dict]) -> int:
        """Write a batch of game details to the database in a single transaction."""
        if not games_data:
            return 0

        conn = get_db_connection()
        written = 0
        try:
            conn.execute("BEGIN TRANSACTION")
            for app_id, data in games_data.items():
                cache_game_details(app_id, data, permanent=True, conn=conn)
                written += 1
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Batch write failed: {e}")
            # Fallback to individual writes to save what we can
            for app_id, data in games_data.items():
                try:
                    cache_game_details(app_id, data, permanent=True)
                    written += 1
                except Exception:
                    pass
        finally:
            conn.close()
        return written

    async def get_fallback_game_info(self, app_id: str) -> Optional[dict]:
        """Get basic game info using multiple fallback strategies for games without store pages."""
        try:
            # Strategy 1: Try using the steam library for more comprehensive data
            fallback_data = await self._try_steam_library_fallback(app_id)
            if fallback_data:
                return fallback_data

            # Strategy 2: Last resort - create minimal entry with app ID
            logger.debug(
                "No fallback info found for app %s, using minimal entry", app_id
            )
            return {
                "name": f"App {app_id}",
                "type": "unknown",
                "is_free": False,
                "categories": [],
                "price_overview": None,
            }

        except (
            httpx.RequestError,
            httpx.TimeoutException,
            ValueError,
            TypeError,
            KeyError,
        ) as e:
            logger.error("Error in fallback lookup for app %s: %s", app_id, e)
            # Return minimal entry as last resort
            return {
                "name": f"App {app_id}",
                "type": "unknown",
                "is_free": False,
                "categories": [],
                "price_overview": None,
            }

    async def _try_steam_library_fallback(self, app_id: str) -> Optional[dict]:
        """Try using the steam library for fallback data, running in a separate thread."""
        if not self.steam_api:
            return None

        def get_app_info():
            try:
                if not self.steam_api:
                    return None
                # Get app list and search for our app using the correct interface
                app_list = self.steam_api.call("ISteamApps.GetAppList")
                if not (
                    app_list and "applist" in app_list and "apps" in app_list["applist"]
                ):
                    return None

                for app in app_list["applist"]["apps"]:
                    if str(app.get("appid")) == app_id:
                        logger.debug(
                            "Found fallback name via steam library for app %s: %s",
                            app_id,
                            app["name"],
                        )
                        return {
                            "name": app["name"],
                            "type": "game",
                            "is_free": False,
                            "categories": [],
                            "price_overview": None,
                        }
            except (ValueError, TypeError, KeyError, OSError) as e:
                logger.debug(
                    "Steam library app list lookup failed for %s: %s", app_id, e
                )
            return None

        return await asyncio.to_thread(get_app_info)

    def load_family_members(self) -> Dict[str, str]:
        """Load family members from database or config."""
        members = {}

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Check if we have family members in database
            cursor.execute("SELECT COUNT(*) FROM family_members")
            if cursor.fetchone()[0] == 0 and FAMILY_USER_DICT:
                print("📥 Migrating family members from config to database...")
                for steam_id, name in FAMILY_USER_DICT.items():
                    cursor.execute(
                        "INSERT OR IGNORE INTO family_members (steam_id, friendly_name, discord_id) VALUES (?, ?, ?)",
                        (steam_id, name, None),
                    )
                conn.commit()
                print(f"✅ Migrated {len(FAMILY_USER_DICT)} family members")

            # Load family members
            cursor.execute("SELECT steam_id, friendly_name FROM family_members")
            for row in cursor.fetchall():
                members[row["steam_id"]] = row["friendly_name"]

            conn.close()
            print(f"👥 Loaded {len(members)} family members")

        except (ValueError, TypeError, OSError) as e:
            print(f"❌ Error loading family members: {e}")
            return {}

        return members

    async def populate_family_library(self, dry_run: bool = False) -> int:
        """Populate the shared family library cache."""
        print("\n🏰 Starting family shared library population...")

        if dry_run:
            print("   🔍 Would fetch shared family library")
            return 0

        try:
            url = get_family_game_list_url()
            response = await self.client.get(url)
            games_json = self.handle_api_response("GetSharedLibraryApps", response)

            if not games_json:
                print("   ❌ Failed to fetch family shared library apps")
                return 0

            game_list = games_json.get("response", {}).get("apps", [])
            if not game_list:
                print("   ⚠️  No apps found in family shared library")
                return 0

            # Cache the library using our new 24h default
            cache_family_library(game_list)
            print(f"   ✅ Cached {len(game_list)} family library apps")
            return len(game_list)

        except Exception as e:
            print(f"   ❌ Error populating family shared library: {e}")
            return 0

    async def get_owned_games(self, steam_id: str) -> Optional[dict]:
        """Get owned games for a user using the steam library."""
        if not self.steam_api:
            return None

        def get_games():
            try:
                if not self.steam_api:
                    return None
                # The appids_filter parameter is required by the steam library,
                # even if we want all games. Passing an empty list should work.
                return self.steam_api.call(
                    "IPlayerService.GetOwnedGames",
                    steamid=steam_id,
                    include_appinfo=1,
                    include_played_free_games=1,
                    appids_filter=[],
                    include_free_sub=1,
                    language="english",
                    include_extended_appinfo=1,
                )
            except (ValueError, TypeError, KeyError, OSError) as e:
                logger.warning(
                    "Steam library GetOwnedGames call failed for %s: %s", steam_id, e
                )
                return None

        return await asyncio.to_thread(get_games)

    async def get_wishlist(self, steam_id: str) -> Optional[dict]:
        """Get wishlist for a user using the steam library."""
        if not self.steam_api:
            return None

        def get_wishlist_data():
            try:
                if not self.steam_api:
                    return None
                return self.steam_api.call(
                    "IWishlistService.GetWishlist", steamid=steam_id
                )
            except (ValueError, TypeError, KeyError, OSError) as e:
                logger.warning(
                    "Steam library GetWishlist call failed for %s: %s", steam_id, e
                )
                return None

        wishlist_data = await asyncio.to_thread(get_wishlist_data)

        # Handle private/empty wishlists
        if wishlist_data and wishlist_data.get("success") == 2:
            logger.warning("Wishlist for %s is private or empty.", steam_id)
            return None

        return wishlist_data

    async def populate_family_libraries(
        self, family_members: Dict[str, str], dry_run: bool = False
    ) -> int:
        """Populate database with all family member game libraries."""
        print("\n🎮 Starting family library population...")

        if (
            not STEAMWORKS_API_KEY
            or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE"
        ):
            print("❌ Steam API key not configured. Cannot fetch family libraries.")
            return 0

        total_cached = 0
        total_processed = 0

        if TQDM_AVAILABLE:
            total_cached = await self._populate_libraries_with_tqdm(
                family_members, dry_run, total_processed, total_cached
            )
        else:
            total_cached = await self._populate_libraries_without_tqdm(
                family_members, dry_run, total_processed, total_cached
            )

        print("\n🎮 Family library population complete!")
        print(f"   📊 Total games processed: {total_processed}")
        print(f"   💾 New games cached: {total_cached}")

        return total_cached

    async def _populate_libraries_with_tqdm(
        self,
        family_members: Dict[str, str],
        dry_run: bool,
        total_processed: int,
        total_cached: int,
    ) -> int:
        """Populate libraries using tqdm progress bars."""
        member_iterator_tqdm = tqdm(
            family_members.items(), desc="👥 Family Members", unit="member", leave=True
        )
        progress_lock = asyncio.Lock()

        for steam_id, name in member_iterator_tqdm:
            member_iterator_tqdm.set_postfix_str(f"Processing {name}")

            try:
                if dry_run:
                    continue

                games_data = await self.get_owned_games(steam_id)
                if not games_data:
                    continue

                games = games_data.get("response", {}).get("games", [])
                if not games:
                    continue

                # Cache the user's game list for !common_games support
                user_appids = [str(g.get("appid")) for g in games if g.get("appid")]
                if user_appids:
                    cache_user_games(steam_id, user_appids)

                user_cached, user_skipped, games_to_fetch = self._process_user_games(
                    games, total_processed
                )

                if games_to_fetch:
                    total_cached += await self._fetch_games_with_progress(
                        games_to_fetch,
                        name,
                        user_cached=user_cached,
                        user_skipped=user_skipped,
                        progress_lock=progress_lock,
                    )
                else:
                    self._show_empty_progress(name, user_cached, user_skipped)

            except (
                httpx.RequestError,
                httpx.TimeoutException,
                httpx.HTTPStatusError,
                ValueError,
                TypeError,
                KeyError,
                asyncio.TimeoutError,
            ) as e:
                logger.warning("Error processing %s: %s", name, e)
                continue

        return total_cached

    async def _populate_libraries_without_tqdm(
        self,
        family_members: Dict[str, str],
        dry_run: bool,
        total_processed: int,
        total_cached: int,
    ) -> int:
        """Populate libraries without tqdm progress bars."""
        for steam_id, name in family_members.items():
            print(f"\n📊 Processing {name}...")

            try:
                if dry_run:
                    print(f"   🔍 Would fetch owned games for {name}")
                    continue

                games_data = await self.get_owned_games(steam_id)
                if not games_data:
                    print(f"   ❌ Failed to get games for {name}")
                    continue

                games = games_data.get("response", {}).get("games", [])
                if not games:
                    print(f"   ⚠️  No games found for {name} (private profile?)")
                    continue

                print(f"   🎯 Found {len(games)} games")

                # Cache the user's game list for !common_games support
                user_appids = [str(g.get("appid")) for g in games if g.get("appid")]
                if user_appids:
                    cache_user_games(steam_id, user_appids)

                user_cached, user_skipped, games_to_fetch = self._process_user_games(
                    games, total_processed
                )

                if games_to_fetch:
                    print(f"   🎯 Processing {len(games_to_fetch)} new games...")
                    total_cached += await self._fetch_games_simple(
                        games_to_fetch, user_cached
                    )

                print(
                    f"   ✅ {name} complete: {user_cached} cached, {user_skipped} skipped"
                )

            except (
                httpx.RequestError,
                httpx.TimeoutException,
                httpx.HTTPStatusError,
                ValueError,
                TypeError,
                KeyError,
                asyncio.TimeoutError,
            ) as e:
                print(f"   ❌ Error processing {name}: {e}")
                continue

        return total_cached

    def _process_user_games(self, games, total_processed):
        """Process user games and return cached, skipped counts and games to fetch."""
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

        return user_cached, user_skipped, games_to_fetch

    async def _fetch_games_with_progress(
        self, games_to_fetch, name, *, user_cached, user_skipped, progress_lock
    ):
        """Fetch games with tqdm progress tracking."""
        games_progress_iterator_tqdm = tqdm(
            total=len(games_to_fetch), desc=f"🎮 {name[:15]}", unit="game", leave=False
        )
        total_cached = 0

        async def fetch_game_with_progress(app_id: str) -> Optional[Tuple[str, Dict]]:
            nonlocal user_cached, user_skipped, total_cached
            game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
            try:
                game_response = await self.make_request_with_retry(
                    game_url, api_type="store"
                )
                if game_response is None:
                    async with progress_lock:
                        user_skipped += 1
                        games_progress_iterator_tqdm.update(1)
                        games_progress_iterator_tqdm.set_postfix_str(
                            f"Cached: {user_cached}, Skipped: {user_skipped}"
                        )
                    return None

                game_info = self.handle_api_response(
                    f"AppDetails ({app_id})", game_response
                )
                if not game_info:
                    async with progress_lock:
                        user_skipped += 1
                        games_progress_iterator_tqdm.update(1)
                        games_progress_iterator_tqdm.set_postfix_str(
                            f"Cached: {user_cached}, Skipped: {user_skipped}"
                        )
                    return None

                game_data = game_info.get(str(app_id), {}).get("data")
                if not game_data:
                    async with progress_lock:
                        user_skipped += 1
                        games_progress_iterator_tqdm.update(1)
                        games_progress_iterator_tqdm.set_postfix_str(
                            f"Cached: {user_cached}, Skipped: {user_skipped}"
                        )
                    return None

                async with progress_lock:
                    user_cached += 1
                    total_cached += 1
                    games_progress_iterator_tqdm.update(1)
                    games_progress_iterator_tqdm.set_postfix_str(
                        f"Cached: {user_cached}, Skipped: {user_skipped}"
                    )
                return (app_id, game_data)
            except (
                httpx.RequestError,
                httpx.TimeoutException,
                httpx.HTTPStatusError,
                ValueError,
                TypeError,
                KeyError,
                asyncio.TimeoutError,
            ):
                async with progress_lock:
                    user_skipped += 1
                    games_progress_iterator_tqdm.update(1)
                    games_progress_iterator_tqdm.set_postfix_str(
                        f"Cached: {user_cached}, Skipped: {user_skipped}"
                    )
                return None

        batch_size = 10
        for i in range(0, len(games_to_fetch), batch_size):
            batch = games_to_fetch[i : i + batch_size]
            tasks = [fetch_game_with_progress(app_id) for app_id in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect successful results
            batch_data = {}
            for res in results:
                if isinstance(res, tuple):
                    batch_data[res[0]] = res[1]

            # Write batch to DB
            self.batch_write_games(batch_data)

        games_progress_iterator_tqdm.close()
        return total_cached

    def _show_empty_progress(self, name, user_cached, user_skipped):
        """Show progress for users with no games to fetch."""
        if TQDM_AVAILABLE:
            games_progress_iterator_tqdm = tqdm(
                total=1, desc=f"🎮 {name[:15]}", unit="game", leave=False
            )
            games_progress_iterator_tqdm.update(1)
            games_progress_iterator_tqdm.set_postfix_str(
                f"Cached: {user_cached}, Skipped: {user_skipped}"
            )
            games_progress_iterator_tqdm.close()

    async def _fetch_games_simple(self, games_to_fetch, user_cached):
        """Fetch games without tqdm progress tracking."""
        total_cached = 0

        async def fetch_game_simple(app_id: str) -> bool:
            """Fetch game details for non-tqdm mode."""
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

            except (
                httpx.RequestError,
                httpx.TimeoutException,
                httpx.HTTPStatusError,
                ValueError,
                TypeError,
                KeyError,
                asyncio.TimeoutError,
            ) as e:
                print(f"   ⚠️  Error processing game {app_id}: {e}")
                return False

        # Process games in small batches with progress updates
        batch_size = 10
        for i in range(0, len(games_to_fetch), batch_size):
            batch = games_to_fetch[i : i + batch_size]
            tasks = [fetch_game_simple(app_id) for app_id in batch]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Progress update every batch
            processed = min(i + batch_size, len(games_to_fetch))
            print(
                f"   📈 Progress: {processed}/{len(games_to_fetch)} | Cached: {user_cached}"
            )

        return total_cached

    async def populate_wishlists(
        self, family_members: Dict[str, str], dry_run: bool = False
    ) -> int:
        """Populate database with family member wishlists."""
        print("\n🎯 Starting wishlist population...")

        if (
            not STEAMWORKS_API_KEY
            or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE"
        ):
            print("❌ Steam API key not configured. Cannot fetch wishlists.")
            return 0

        global_wishlist: list[list] = []
        total_cached: int = 0

        # Collect wishlists from all family members
        for i, (steam_id, name) in enumerate(family_members.items(), 1):
            print(f"\n📊 Processing {name}'s wishlist ({i}/{len(family_members)})...")

            try:
                # Check for cached wishlist first
                cached_wishlist = get_cached_wishlist(steam_id)
                if cached_wishlist:
                    print(f"   💾 Using cached wishlist ({len(cached_wishlist)} items)")
                    for app_id in cached_wishlist:
                        idx = find_in_2d_list(app_id, global_wishlist)
                        if idx is not None:
                            global_wishlist[idx][1].append(steam_id)
                        else:
                            global_wishlist.append([app_id, [steam_id]])
                    continue

                if dry_run:
                    print(f"   🔍 Would fetch wishlist for {name}")
                    continue

                # Fetch wishlist from API
                wishlist_data = await self.get_wishlist(steam_id)
                if not wishlist_data:
                    print(f"   ❌ Failed to get wishlist for {name}")
                    continue

                wishlist_items = wishlist_data.get("response", {}).get("items", [])
                if not wishlist_items:
                    print(f"   ⚠️  No items in {name}'s wishlist")
                    continue

                print(f"   🎯 Found {len(wishlist_items)} wishlist items")

                # Process wishlist items
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
                print(f"   ✅ {name}'s wishlist cached")

            except (
                httpx.RequestError,
                httpx.TimeoutException,
                httpx.HTTPStatusError,
                ValueError,
                TypeError,
                KeyError,
                asyncio.TimeoutError,
            ) as e:
                print(f"   ❌ Error processing {name}'s wishlist: {e}")
                continue

        # Process ALL wishlist games (not just common ones)
        all_unique_games = {
            item[0] for item in global_wishlist
        }  # Use set comprehension
        if not all_unique_games:
            print("\n🎯 No wishlist games found")
            return 0

        print(f"\n🎯 Processing {len(all_unique_games)} unique wishlist games...")

        if dry_run:
            print("   🔍 Would process all wishlist games for caching")
            return 0

        # Filter out games that are already cached
        games_to_fetch = []
        for app_id in all_unique_games:
            if not get_cached_game_details(app_id):
                games_to_fetch.append(app_id)

        if not games_to_fetch:
            print("   ✅ All wishlist games already cached")
            return 0

        print(f"   🎯 Found {len(games_to_fetch)} new games to cache")

        # Setup progress bar if available
        pbar = None
        if TQDM_AVAILABLE:
            pbar = tqdm(
                total=len(games_to_fetch),
                desc="🎯 Wishlist Games",
                unit="game",
                leave=True,
            )

        # Process in batches for concurrency
        batch_size = 10

        for i in range(0, len(games_to_fetch), batch_size):
            batch = games_to_fetch[i : i + batch_size]
            batch_data = {}

            async def fetch_wishlist_item(app_id):
                try:
                    game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                    response = await self.make_request_with_retry(
                        game_url, api_type="store"
                    )

                    if response:
                        game_info = self.handle_api_response(
                            f"AppDetails ({app_id})", response
                        )
                        if game_info:
                            game_data = game_info.get(str(app_id), {}).get("data")
                            if game_data:
                                return (app_id, game_data)

                            # Fallback
                            fallback_data = await self.get_fallback_game_info(app_id)
                            if fallback_data:
                                return (app_id, fallback_data)
                    return None
                except Exception as e:
                    if not TQDM_AVAILABLE:
                        print(f"   ⚠️  Error processing game {app_id}: {e}")
                    return None

            # Run batch concurrently
            tasks = [fetch_wishlist_item(app_id) for app_id in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in results:
                if isinstance(res, tuple):
                    batch_data[res[0]] = res[1]
                    total_cached += 1

            # Write batch
            self.batch_write_games(batch_data)

            # Update progress
            if pbar:
                pbar.update(len(batch))
            elif not TQDM_AVAILABLE:
                print(
                    f"   📈 Progress: {min(i + batch_size, len(games_to_fetch))}/{len(games_to_fetch)} games processed"
                )

        if pbar:
            pbar.close()

        print("\n🎯 Wishlist population complete!")
        print(f"   💾 All wishlist games cached: {total_cached}")

        return total_cached


async def main():
    """Main function to run the database population."""
    parser = argparse.ArgumentParser(
        description="Populate FamilyBot database with comprehensive game data"
    )
    parser.add_argument(
        "--library-only", action="store_true", help="Only scan family member libraries"
    )
    parser.add_argument(
        "--wishlist-only", action="store_true", help="Only scan wishlists"
    )
    parser.add_argument("--fast", action="store_true", help="Use faster rate limiting")
    parser.add_argument("--slow", action="store_true", help="Use slower rate limiting")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    # Determine rate limiting mode
    rate_mode = "normal"
    if args.fast:
        rate_mode = "fast"
    elif args.slow:
        rate_mode = "slow"

    print("🚀 FamilyBot Database Population Script")
    print("=" * 50)

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")

    # Initialize database
    try:
        init_db()
        print("✅ Database initialized")
    except (ValueError, TypeError, OSError) as e:
        print(f"❌ Failed to initialize database: {e}")
        return 1

    # Initialize populator
    populator = DatabasePopulator(rate_mode)

    try:
        # Load family members
        family_members = populator.load_family_members()
        if not family_members:
            print("❌ No family members found. Check your configuration.")
            return 1

        start_time = datetime.now()
        total_library_cached = 0
        total_wishlist_cached = 0

        # Populate family libraries
        if not args.wishlist_only:
            total_library_cached += await populator.populate_family_library(
                args.dry_run
            )
            total_library_cached += await populator.populate_family_libraries(
                family_members, args.dry_run
            )

        # Populate wishlists
        if not args.library_only:
            total_wishlist_cached = await populator.populate_wishlists(
                family_members, args.dry_run
            )

        # Final summary
        end_time = datetime.now()
        duration = end_time - start_time
    finally:
        await populator.close()

    print("\n" + "=" * 50)
    print("🎉 Database Population Complete!")
    print(f"⏱️  Duration: {duration.total_seconds():.1f} seconds")
    print(f"👥 Family members: {len(family_members)}")
    print(f"🎮 Library games cached: {total_library_cached}")
    print(f"🎯 Wishlist games cached: {total_wishlist_cached}")
    print(f"💾 Total games cached: {total_library_cached + total_wishlist_cached}")

    if not args.dry_run:
        print("\n🚀 Your FamilyBot database is now fully populated!")
        print("   All commands will run at maximum speed with USD pricing.")

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except (
        ValueError,
        TypeError,
        OSError,
        httpx.RequestError,
        httpx.HTTPStatusError,
        asyncio.TimeoutError,
    ) as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
