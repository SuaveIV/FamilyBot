import os
import sys
import random
import json
import argparse
import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Optional
import httpx

from steam.webapi import WebAPI

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from familybot.config import STEAMWORKS_API_KEY, ITAD_API_KEY  # pylint: disable=wrong-import-position
from familybot.lib.database import (
    get_db_connection,
    init_db,
)
from familybot.lib.family_library_repository import cache_family_library
from familybot.lib.family_utils import get_family_game_list_url  # pylint: disable=wrong-import-position
from familybot.lib.game_details_repository import (
    cache_game_details,
    get_cached_game_details,
)
from familybot.lib.logging_config import setup_script_logging  # pylint: disable=wrong-import-position
from familybot.lib.steam_itad_mapping_repository import (
    get_cached_itad_ids_bulk,
    bulk_cache_itad_mappings,
)
from familybot.lib.user_games_repository import cache_user_games
from familybot.lib.user_repository import load_family_members_from_db
from familybot.lib.utils import TokenBucket  # pylint: disable=wrong-import-position
from familybot.lib.wishlist_repository import (
    cache_wishlist,
    get_cached_wishlist,
)
from familybot.lib.wishlist_service import add_to_wishlist  # pylint: disable=wrong-import-position

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

        self._app_list_cache = None
        self._app_list_lock = asyncio.Lock()

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
        self,
        url: str,
        api_type: str = "steam",
        method: str = "GET",
        params: Optional[dict] = None,
        json: Optional[dict | list] = None,
        timeout: Optional[float] = None,
        headers: Optional[dict] = None,
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
                # Only pass timeout if explicitly provided, otherwise use client default (15.0s)
                request_kwargs: dict[str, Any] = {"params": params, "headers": headers}
                if json is not None:
                    request_kwargs["json"] = json
                if timeout is not None:
                    request_kwargs["timeout"] = timeout

                if method.upper() == "POST":
                    response = await self.client.post(url, **request_kwargs)
                else:
                    response = await self.client.get(url, **request_kwargs)

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

    def batch_write_games(self, games_data: dict[str, dict]) -> int:
        """Write a batch of game details to the database in a single transaction."""
        if not games_data:
            return 0

        conn = get_db_connection()
        written = 0
        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN TRANSACTION")
            batch_written = 0
            for app_id, data in games_data.items():
                cache_game_details(app_id, data, permanent=False, conn=conn)
                batch_written += 1
            conn.commit()
            written += batch_written
        except Exception as e:
            conn.rollback()
            logger.error("Batch write failed: %s", e)
            # Fallback to individual writes to save what we can
            for app_id, data in games_data.items():
                try:
                    cache_game_details(app_id, data, permanent=False)
                    written += 1
                except Exception:
                    pass
        finally:
            if cursor is not None:
                cursor.close()
            # Do not close the shared connection from get_db_connection()
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

        # Capture steam_api in a local variable to satisfy type checker
        steam_api = self.steam_api

        async with self._app_list_lock:
            if self._app_list_cache is None:

                def get_app_list():
                    try:
                        app_list_response = steam_api.call("ISteamApps.GetAppList_v2")
                        if (
                            app_list_response
                            and "applist" in app_list_response
                            and "apps" in app_list_response["applist"]
                        ):
                            # Convert to dict for fast O(1) lookups
                            return {
                                str(app.get("appid")): app.get("name")
                                for app in app_list_response["applist"]["apps"]
                            }
                        return {}
                    except (ValueError, TypeError, KeyError, OSError) as e:
                        logger.debug("Steam library app list lookup failed: %s", e)
                        return {}

                self._app_list_cache = await asyncio.to_thread(get_app_list)

        app_name = self._app_list_cache.get(app_id)
        if app_name:
            logger.debug(
                "Found fallback name via steam library for app %s: %s",
                app_id,
                app_name,
            )
            return {
                "name": app_name,
                "type": "game",
                "is_free": False,
                "categories": [],
                "price_overview": None,
            }

        return None

    def load_family_members(self) -> dict[str, str]:
        """Load family members from database."""
        return load_family_members_from_db()

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
        self, family_members: dict[str, str], dry_run: bool = False
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
            total_cached, total_processed = await self._populate_libraries_with_tqdm(
                family_members, dry_run, total_processed, total_cached
            )
        else:
            total_cached, total_processed = await self._populate_libraries_without_tqdm(
                family_members, dry_run, total_processed, total_cached
            )

        print("\n🎮 Family library population complete!")
        print(f"   📊 Total games processed: {total_processed}")
        print(f"   💾 New games cached: {total_cached}")

        return total_cached

    async def _populate_libraries_with_tqdm(
        self,
        family_members: dict[str, str],
        dry_run: bool,
        total_processed: int,
        total_cached: int,
    ) -> tuple[int, int]:
        """Populate libraries using tqdm progress bars. Returns (total_cached, total_processed)."""
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

                user_cached, user_skipped, games_to_fetch, total_processed = (
                    self._process_user_games(games, total_processed)
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

        return total_cached, total_processed

    async def _populate_libraries_without_tqdm(
        self,
        family_members: dict[str, str],
        dry_run: bool,
        total_processed: int,
        total_cached: int,
    ) -> tuple[int, int]:
        """Populate libraries without tqdm progress bars. Returns (total_cached, total_processed)."""
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

                user_cached, user_skipped, games_to_fetch, total_processed = (
                    self._process_user_games(games, total_processed)
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

        return total_cached, total_processed

    def _process_user_games(self, games, total_processed):
        """Process user games and return cached, skipped counts, games to fetch, and updated count."""
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

        return user_cached, user_skipped, games_to_fetch, total_processed

    async def _fetch_games_with_progress(
        self, games_to_fetch, name, *, user_cached, user_skipped, progress_lock
    ):
        """Fetch games with tqdm progress tracking."""
        games_progress_iterator_tqdm = tqdm(
            total=len(games_to_fetch), desc=f"🎮 {name[:15]}", unit="game", leave=False
        )
        total_cached = 0

        async def fetch_game_with_progress(app_id: str) -> Optional[tuple[str, dict]]:
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

                cache_game_details(app_id, game_data, permanent=False)
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

    async def _process_itad_chunk(
        self,
        chunk: list[str],
        new_mappings: dict[str, str],
        failed_count: int,
        pbar_update: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """Process a chunk of ITAD ID lookups.

        Args:
            chunk: List of app IDs to look up
            new_mappings: Dictionary to update with new mappings
            failed_count: Current failure count to update
            pbar_update: Optional callback to update progress bar

        Returns:
            Updated failed_count
        """
        shop_queries = [f"app/{app_id}" for app_id in chunk]
        lookup_url = "https://api.isthereanydeal.com/lookup/id/shop/61/v1"
        try:
            # Use retry logic for POST (rate limiting handled by make_request_with_retry)
            response = await self.make_request_with_retry(
                lookup_url,
                api_type="store",
                method="POST",
                json=shop_queries,
                params={"key": ITAD_API_KEY},
                timeout=30,
            )

            if response is None:
                # 429s are handled by make_request_with_retry and cause None to be returned after retries
                failed_count += len(chunk)
                if pbar_update:
                    pbar_update(len(chunk), failed_count)
                return failed_count

            lookup_data = self.handle_api_response("ITAD Bulk Lookup", response)
            if not isinstance(lookup_data, dict):
                failed_count += len(chunk)
                if pbar_update:
                    pbar_update(len(chunk), failed_count)
                return failed_count

            for shop_query, itad_id in lookup_data.items():
                app_id = shop_query.replace("app/", "")
                if itad_id:
                    new_mappings[app_id] = itad_id
                else:
                    failed_count += 1

            if pbar_update:
                pbar_update(len(chunk), failed_count)

        except (ValueError, ImportError) as e:
            logger.error("ITAD bulk lookup chunk failed: %s", e)
            failed_count += len(chunk)
            if pbar_update:
                pbar_update(len(chunk), failed_count)
        except KeyboardInterrupt:
            raise
        except httpx.RequestError as e:
            logger.error("ITAD bulk lookup chunk failed: %s", e)
            failed_count += len(chunk)
            if pbar_update:
                pbar_update(len(chunk), failed_count)

        return failed_count

    async def resolve_itad_ids(self, dry_run: bool = False) -> int:
        """Resolve and cache ITAD IDs for all known games using bulk lookup."""
        if not ITAD_API_KEY or ITAD_API_KEY == "YOUR_ITAD_API_KEY_HERE":
            print("\n⚠️  ITAD API key not configured. Skipping ITAD ID resolution.")
            return 0

        print("\n🔗 Starting ITAD ID resolution...")

        if dry_run:
            print("   🔍 Would resolve ITAD IDs for all cached games")
            return 0

        # Collect all known app IDs from the database
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT appid FROM game_details_cache")
                all_appids = [row["appid"] for row in cursor.fetchall()]
            finally:
                cursor.close()
        finally:
            conn.close()

        if not all_appids:
            print("   ⚠️  No games found in database")
            return 0

        print(f"   📊 Found {len(all_appids)} games to check")

        # Check which ones already have ITAD mappings
        cached_mappings = get_cached_itad_ids_bulk(all_appids)
        uncached = [aid for aid in all_appids if aid not in cached_mappings]

        print(f"   💾 Already mapped: {len(cached_mappings)}")
        print(f"   🔍 Need lookup: {len(uncached)}")

        if not uncached:
            print("   ✅ All games already have ITAD ID mappings")
            return 0

        # Bulk lookup in chunks of 100
        new_mappings = {}
        failed_count = 0
        chunk_size = 100

        if TQDM_AVAILABLE:
            pbar = tqdm(
                total=len(uncached),
                desc="Resolving ITAD IDs",
                unit="game",
                leave=True,
            )
            try:

                def pbar_update(size: int, failed_count: int):
                    pbar.update(size)
                    pbar.set_postfix_str(
                        f"Mapped: {len(new_mappings)}, Failed: {failed_count}"
                    )

                for i in range(0, len(uncached), chunk_size):
                    chunk = uncached[i : i + chunk_size]
                    failed_count = await self._process_itad_chunk(
                        chunk, new_mappings, failed_count, pbar_update
                    )
            finally:
                pbar.close()
        else:
            for i in range(0, len(uncached), chunk_size):
                chunk = uncached[i : i + chunk_size]
                failed_count = await self._process_itad_chunk(
                    chunk, new_mappings, failed_count
                )

        # Cache new mappings
        if new_mappings:
            bulk_cache_itad_mappings(new_mappings)

        print("\n🔗 ITAD ID resolution complete!")
        print(f"   ✅ New mappings cached: {len(new_mappings)}")
        print(f"   ❌ Failed to resolve: {failed_count}")

        return len(new_mappings)

    async def _fetch_wishlist_item(self, app_id: str):
        """Fetch a single wishlist item's game details."""
        try:
            game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
            response = await self.make_request_with_retry(game_url, api_type="store")

            if response:
                game_info = self.handle_api_response(f"AppDetails ({app_id})", response)
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
            logger.warning("Error processing game %s: %s", app_id, e)
            return None

    async def populate_wishlists(
        self, family_members: dict[str, str], dry_run: bool = False
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
                        add_to_wishlist(global_wishlist, str(app_id), steam_id)
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
                    add_to_wishlist(global_wishlist, app_id, steam_id)

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

            # Run batch concurrently
            tasks = [self._fetch_wishlist_item(app_id) for app_id in batch]
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

        # Resolve ITAD IDs for all discovered games
        await populator.resolve_itad_ids(args.dry_run)

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
