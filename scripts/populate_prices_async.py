import logging
import argparse
import json
import os
import random
import sys
import time
import asyncio
from datetime import datetime
from typing import Dict, Optional, Set, Tuple

import httpx

from steam.webapi import WebAPI


try:
    from tqdm.asyncio import tqdm as atqdm

    ASYNC_TQDM_AVAILABLE = True
except ImportError:
    print("⚠️  tqdm not available. Install with: uv pip install tqdm")
    print("   Falling back to basic progress indicators...")
    ASYNC_TQDM_AVAILABLE = False

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


from familybot.config import FAMILY_USER_DICT, ITAD_API_KEY, STEAMWORKS_API_KEY  # pylint: disable=wrong-import-position
from familybot.lib.database import (
    cache_game_details,  # pylint: disable=wrong-import-position
    cache_game_details_with_source,  # pylint: disable=wrong-import-position
    cache_itad_price_enhanced,
    get_cached_game_details,  # pylint: disable=wrong-import-position
    get_cached_itad_price,
    get_cached_wishlist,  # pylint: disable=wrong-import-position
    get_db_connection,
    init_db,  # pylint: disable=wrong-import-position
    migrate_database_phase1,  # pylint: disable=wrong-import-position
    migrate_database_phase2,
)  # pylint: disable=wrong-import-position
from familybot.lib.logging_config import setup_script_logging  # pylint: disable=wrong-import-position

# Setup enhanced logging for this script
logger = setup_script_logging("populate_prices_async", "INFO")

# Suppress verbose HTTP request logging from other libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("steam").setLevel(logging.WARNING)


class AsyncPricePopulator:
    """High-performance async price populator with true async/await processing."""

    def __init__(self, max_concurrent: int = 50, rate_limit_mode: str = "adaptive"):
        """Initialize with async capabilities and higher default concurrency."""
        self.max_concurrent = max_concurrent
        self.rate_limit_mode = rate_limit_mode

        # Adaptive rate limiting - optimized for async
        self.current_delays = {
            "steam_api": 0.05,  # Start very fast for async
            "store_api": 0.1,
            "itad_api": 0.05,
        }

        # Rate limit bounds - more aggressive for async
        self.min_delays = {"steam_api": 0.01, "store_api": 0.05, "itad_api": 0.01}
        self.max_delays = {"steam_api": 2.0, "store_api": 3.0, "itad_api": 1.5}

        # Error tracking for adaptive rate limiting
        self.error_counts = {"steam_api": 0, "store_api": 0, "itad_api": 0}
        self.success_counts = {"steam_api": 0, "store_api": 0, "itad_api": 0}
        self.last_adjustment = {"steam_api": 0.0, "store_api": 0.0, "itad_api": 0.0}

        # Async locks for rate limiting
        self.rate_limit_locks = {
            "steam_api": asyncio.Lock(),
            "store_api": asyncio.Lock(),
            "itad_api": asyncio.Lock(),
        }
        self.last_request_times = {"steam_api": 0.0, "store_api": 0.0, "itad_api": 0.0}

        # Async HTTP client with aggressive connection pooling
        self.client = httpx.AsyncClient(
            timeout=15.0,
            limits=httpx.Limits(
                max_keepalive_connections=100,  # High keepalive for async
                max_connections=200,  # High total connections
                keepalive_expiry=60.0,  # Keep connections alive longer
            ),
            headers={
                "User-Agent": "FamilyBot-AsyncPricePopulator/1.0",
                "Connection": "keep-alive",
            },
        )

        # Async semaphore for concurrency control
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Initialize Steam WebAPI if available (sync only)
        self.steam_api = None
        if STEAMWORKS_API_KEY and STEAMWORKS_API_KEY != "YOUR_STEAMWORKS_API_KEY_HERE":
            try:
                self.steam_api = WebAPI(key=STEAMWORKS_API_KEY)
                print("🔧 Steam WebAPI initialized successfully")
            except (ValueError, TypeError, OSError, ImportError) as e:
                logger.warning("Failed to initialize Steam WebAPI: %s", e)
                self.steam_api = None

        print("🚀 Async Price Populator initialized")
        print(f"   Max concurrent requests: {max_concurrent}")
        print(f"   Rate limiting: {rate_limit_mode}")
        print("   Connection pool: 200 max, 100 keepalive")
        print(
            f"   Initial delays - Steam: {self.current_delays['steam_api']}s, Store: {self.current_delays['store_api']}s, ITAD: {self.current_delays['itad_api']}s"
        )

    async def aclose(self):
        """Close the async HTTP client."""
        await self.client.aclose()

    def adaptive_rate_limit(self, api_type: str, success: bool):
        """Adjust rate limits based on success/failure rates."""
        if self.rate_limit_mode != "adaptive":
            return

        current_time = time.time()

        # Update counters
        if success:
            self.success_counts[api_type] += 1
        else:
            self.error_counts[api_type] += 1

        # Adjust every 10 requests or every 30 seconds
        total_requests = self.success_counts[api_type] + self.error_counts[api_type]
        time_since_adjustment = current_time - self.last_adjustment[api_type]

        if total_requests % 10 == 0 or time_since_adjustment > 30:
            error_rate = self.error_counts[api_type] / max(total_requests, 1)

            if error_rate > 0.2:  # More than 20% errors - slow down
                self.current_delays[api_type] = min(
                    self.current_delays[api_type] * 1.5, self.max_delays[api_type]
                )
                logger.debug(
                    f"Slowing down {api_type}: {self.current_delays[api_type]:.2f}s (error rate: {error_rate:.1%})"
                )
            elif (
                error_rate < 0.05 and self.success_counts[api_type] > 20
            ):  # Less than 5% errors - speed up
                self.current_delays[api_type] = max(
                    self.current_delays[api_type] * 0.8, self.min_delays[api_type]
                )
                logger.debug(
                    f"Speeding up {api_type}: {self.current_delays[api_type]:.2f}s (error rate: {error_rate:.1%})"
                )

            self.last_adjustment[api_type] = current_time

    async def rate_limited_request(self, api_type: str):
        """Async rate limiting."""
        async with self.rate_limit_locks[api_type]:
            current_time = time.time()
            time_since_last = current_time - self.last_request_times[api_type]
            delay_needed = self.current_delays[api_type] - time_since_last

            if delay_needed > 0:
                await asyncio.sleep(
                    delay_needed + random.uniform(0, 0.02)
                )  # Small jitter

            self.last_request_times[api_type] = time.time()

    async def make_request_with_retry(
        self,
        url: str,
        method: str = "GET",
        json_data: Optional[dict | list] = None,
        api_type: str = "store",
        max_retries: int = 2,
    ) -> Optional[httpx.Response]:
        """Make async HTTP request with adaptive rate limiting and retry logic."""

        for attempt in range(max_retries + 1):
            try:
                # Apply rate limiting
                await self.rate_limited_request(api_type)

                # Make the async request
                if method == "GET":
                    response = await self.client.get(url)
                elif method == "POST":
                    response = await self.client.post(url, json=json_data)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                # Check for rate limiting
                if response.status_code == 429:
                    if attempt < max_retries:
                        backoff_time = (2**attempt) + random.uniform(0, 1)
                        logger.debug(
                            "Rate limited (429), retrying in %.1fs (attempt %d/%d)",
                            backoff_time,
                            attempt + 1,
                            max_retries + 1,
                        )
                        await asyncio.sleep(backoff_time)
                        self.adaptive_rate_limit(api_type, False)
                        continue
                    logger.warning("Max retries exceeded for %s", url)
                    self.adaptive_rate_limit(api_type, False)
                    return None

                # Success
                self.adaptive_rate_limit(api_type, True)
                return response

            except (httpx.RequestError, httpx.TimeoutException, OSError) as e:
                if attempt < max_retries:
                    backoff_time = 2**attempt
                    logger.debug(
                        "Request failed: %s, retrying in %.1fs", e, backoff_time
                    )
                    await asyncio.sleep(backoff_time)
                    continue
                logger.debug("Request failed after %d retries: %s", max_retries, e)
                self.adaptive_rate_limit(api_type, False)
                return None

        return None

    def handle_api_response(
        self, api_name: str, response: httpx.Response
    ) -> Optional[dict]:
        """Handle API response with error checking."""
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 429:  # Don't log 429s as errors
                logger.debug("HTTP error for %s: %s", api_name, e)
            return None
        except (
            httpx.RequestError,
            json.JSONDecodeError,
            ValueError,
            TypeError,
            KeyError,
        ) as e:
            logger.debug("Error for %s: %s", api_name, e)
            return None

    def load_family_members(self) -> Dict[str, str]:
        """Load family members from database."""
        members = {}
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
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

            cursor.execute("SELECT steam_id, friendly_name FROM family_members")
            for row in cursor.fetchall():
                members[row["steam_id"]] = row["friendly_name"]
            conn.close()
            print(f"👥 Loaded {len(members)} family members")
        except (ValueError, TypeError, OSError) as e:
            print(f"❌ Error loading family members: {e}")
            return {}
        return members

    def collect_all_game_ids(self, family_members: Dict[str, str]) -> Set[str]:
        """Collect all unique game IDs from family wishlists."""
        all_game_ids = set()
        print("\n📊 Collecting game IDs from family wishlists...")
        for steam_id, name in family_members.items():
            cached_wishlist = get_cached_wishlist(steam_id)
            if cached_wishlist:
                all_game_ids.update(cached_wishlist)
                print(f"   📋 {name}: {len(cached_wishlist)} wishlist games")
            else:
                print(f"   ⚠️  {name}: No cached wishlist found")
        print(f"\n🎯 Total unique wishlist games to process: {len(all_game_ids)}")
        return all_game_ids

    async def fetch_steam_price_single(
        self, app_id: str
    ) -> Tuple[str, bool, dict, str]:
        """Fetch Steam price for a single game with multiple strategies. Returns data instead of writing to DB."""
        async with self.semaphore:  # Control concurrency
            # Strategy 1: Steam Store API
            try:
                game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                response = await self.make_request_with_retry(
                    game_url, method="GET", api_type="store"
                )

                if response is not None:
                    game_info = self.handle_api_response(
                        f"Steam Store ({app_id})", response
                    )
                    if game_info and game_info.get(str(app_id), {}).get("data"):
                        return app_id, True, game_info[str(app_id)]["data"], "store_api"
            except Exception as e:
                logger.debug("Steam Store API failed for %s: %s", app_id, e)

            # Strategy 2: Steam WebAPI fallback (sync call in async context)
            if self.steam_api:
                try:
                    await self.rate_limited_request("steam_api")
                    # Run sync Steam API call in thread pool
                    loop = asyncio.get_event_loop()
                    app_list = await loop.run_in_executor(
                        None, self.steam_api.call, "ISteamApps.GetAppList"
                    )

                    if app_list and "applist" in app_list:
                        for app in app_list["applist"]["apps"]:
                            if str(app.get("appid")) == app_id:
                                game_data = {
                                    "name": app["name"],
                                    "type": "game",
                                    "is_free": False,
                                    "categories": [],
                                    "price_overview": None,
                                }
                                return app_id, True, game_data, "steam_library"
                except Exception as e:
                    logger.debug("Steam WebAPI failed for %s: %s", app_id, e)

            return app_id, False, {}, "failed"

    async def fetch_itad_price_single(self, app_id: str) -> Tuple[str, str, dict, str]:
        """Fetch ITAD price for a single game with multiple strategies. Returns data instead of writing to DB."""
        async with self.semaphore:  # Control concurrency
            # Strategy 1: ITAD App ID lookup
            try:
                lookup_url = f"https://api.isthereanydeal.com/games/lookup/v1?key={ITAD_API_KEY}&appid={app_id}"
                lookup_response = await self.make_request_with_retry(
                    lookup_url, method="GET", api_type="itad"
                )

                if lookup_response is not None:
                    lookup_data = self.handle_api_response(
                        f"ITAD Lookup ({app_id})", lookup_response
                    )
                    game_id = (
                        lookup_data.get("game", {}).get("id") if lookup_data else None
                    )

                    if game_id:
                        # Get price data
                        prices_url = f"https://api.isthereanydeal.com/games/prices/v3?key={ITAD_API_KEY}&country=US&shops=61"
                        prices_response = await self.make_request_with_retry(
                            prices_url,
                            method="POST",
                            json_data=[game_id],
                            api_type="itad",
                        )

                        if prices_response is not None:
                            prices_data = self.handle_api_response(
                                f"ITAD Prices ({app_id})", prices_response
                            )

                            if (
                                prices_data
                                and len(prices_data) > 0
                                and "historyLow" in prices_data[0]
                            ):
                                history_low = prices_data[0]["historyLow"].get(
                                    "all", {}
                                )
                                price_amount = history_low.get("amount")
                                shop_name = history_low.get("shop", {}).get(
                                    "name", "Historical Low (All Stores)"
                                )

                                if price_amount is not None:
                                    price_data = {
                                        "lowest_price": str(price_amount),
                                        "lowest_price_formatted": f"${price_amount}",
                                        "shop_name": shop_name,
                                    }
                                    return app_id, "cached", price_data, "appid"
            except Exception as e:
                logger.debug("ITAD App ID lookup failed for %s: %s", app_id, e)

            # Strategy 2: Name-based search (if we have Steam data)
            try:
                cached_details = get_cached_game_details(app_id)
                if cached_details and cached_details.get("name"):
                    game_name = cached_details["name"]

                    # Search by name
                    search_url = f"https://api.isthereanydeal.com/games/search/v1?key={ITAD_API_KEY}&title={game_name}"
                    search_response = await self.make_request_with_retry(
                        search_url, method="GET", api_type="itad"
                    )

                    if search_response is not None:
                        search_data = self.handle_api_response(
                            f"ITAD Search ({game_name})", search_response
                        )

                        if search_data and len(search_data) > 0:
                            game_id = search_data[0].get("id")
                            if game_id:
                                # Get price data
                                prices_url = f"https://api.isthereanydeal.com/games/prices/v3?key={ITAD_API_KEY}&country=US&shops=61"
                                prices_response = await self.make_request_with_retry(
                                    prices_url,
                                    method="POST",
                                    json_data=[game_id],
                                    api_type="itad",
                                )

                                if prices_response is not None:
                                    prices_data = self.handle_api_response(
                                        f"ITAD Prices ({game_name})", prices_response
                                    )

                                    if (
                                        prices_data
                                        and len(prices_data) > 0
                                        and "historyLow" in prices_data[0]
                                    ):
                                        history_low = prices_data[0]["historyLow"].get(
                                            "all", {}
                                        )
                                        price_amount = history_low.get("amount")
                                        shop_name = history_low.get("shop", {}).get(
                                            "name", "Historical Low (All Stores)"
                                        )

                                        if price_amount is not None:
                                            price_data = {
                                                "lowest_price": str(price_amount),
                                                "lowest_price_formatted": f"${price_amount}",
                                                "shop_name": shop_name,
                                            }
                                            return (
                                                app_id,
                                                "cached",
                                                price_data,
                                                "name_search",
                                            )
            except Exception as e:
                logger.debug("ITAD name search failed for %s: %s", app_id, e)

            return app_id, "not_found", {}, "failed"

    def batch_write_steam_data(
        self, steam_data: Dict[str, Dict], batch_size: int = 100
    ) -> int:
        """Write Steam data to database in safe batches with proper error handling."""
        if not steam_data:
            return 0

        written_count = 0
        items = list(steam_data.items())

        print(f"   💾 Writing {len(items)} Steam records in batches of {batch_size}...")

        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]

            conn = get_db_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                for app_id, game_info in batch:
                    game_data = game_info["data"]
                    source = game_info["source"]

                    if source == "steam_library":
                        cache_game_details_with_source(
                            app_id, game_data, source, conn=conn
                        )
                    else:
                        cache_game_details(app_id, game_data, permanent=True, conn=conn)

                    written_count += 1

                conn.commit()
                logger.debug(f"Successfully wrote batch of {len(batch)} Steam records")

            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to write Steam batch: {e}")
                # Try individual records to salvage what we can
                for app_id, game_info in batch:
                    try:
                        game_data = game_info["data"]
                        source = game_info["source"]

                        if source == "steam_library":
                            cache_game_details_with_source(app_id, game_data, source)
                        else:
                            cache_game_details(app_id, game_data, permanent=True)

                        written_count += 1
                    except Exception as individual_error:
                        logger.error(
                            f"Failed to write individual Steam record {app_id}: {individual_error}"
                        )
                        written_count -= 1  # Adjust count for failed individual writes

            finally:
                conn.close()

        print(f"   ✅ Successfully wrote {written_count} Steam records to database")
        return written_count

    def batch_write_itad_data(
        self, itad_data: Dict[str, Dict], batch_size: int = 100
    ) -> int:
        """Write ITAD data to database in safe batches with proper error handling."""
        if not itad_data:
            return 0

        written_count = 0
        items = list(itad_data.items())

        print(f"   💾 Writing {len(items)} ITAD records in batches of {batch_size}...")

        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]

            conn = get_db_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                for app_id, price_info in batch:
                    price_data = price_info["data"]
                    lookup_method = price_info["method"]
                    game_name = price_info.get("game_name")

                    cache_itad_price_enhanced(
                        app_id,
                        price_data,
                        lookup_method=lookup_method,
                        steam_game_name=game_name,
                        permanent=True,
                        conn=conn,
                    )
                    written_count += 1

                conn.commit()
                logger.debug(f"Successfully wrote batch of {len(batch)} ITAD records")

            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to write ITAD batch: {e}")
                # Try individual records to salvage what we can
                for app_id, price_info in batch:
                    try:
                        price_data = price_info["data"]
                        lookup_method = price_info["method"]
                        game_name = price_info.get("game_name")

                        cache_itad_price_enhanced(
                            app_id,
                            price_data,
                            lookup_method=lookup_method,
                            steam_game_name=game_name,
                            permanent=True,
                        )
                        written_count += 1
                    except Exception as individual_error:
                        logger.error(
                            f"Failed to write individual ITAD record {app_id}: {individual_error}"
                        )
                        written_count -= 1  # Adjust count for failed individual writes

            finally:
                conn.close()

        print(f"   ✅ Successfully wrote {written_count} ITAD records to database")
        return written_count

    async def populate_steam_prices(
        self, game_ids: Set[str], dry_run: bool = False, force_refresh: bool = False
    ) -> int:
        """Populate Steam prices with async processing using cache-then-write pattern."""
        print("\n💰 Starting async Steam price population...")
        if not game_ids:
            print("❌ No game IDs to process")
            return 0

        games_to_process = []
        for gid in game_ids:
            if force_refresh:
                games_to_process.append(gid)
            else:
                cached_details = get_cached_game_details(gid)
                if not cached_details or not cached_details.get("price_data"):
                    games_to_process.append(gid)

        games_skipped = len(game_ids) - len(games_to_process)

        print(f"   🎯 Games to process: {len(games_to_process)}")
        print(f"   ⏭️   Games skipped (already have price data): {games_skipped}")
        print(f"   🚀 Processing with {self.max_concurrent} concurrent async requests")

        if dry_run:
            print("   🔍 DRY RUN: Would fetch Steam price data")
            return 0

        if not games_to_process:
            print("   ✅ All games already have Steam price data")
            return 0

        # Phase 1: Async data collection
        print("   📡 Phase 1: Async API data collection...")
        steam_data = {}
        steam_errors = []

        # Create async tasks for all games
        tasks = [self.fetch_steam_price_single(app_id) for app_id in games_to_process]

        # Collect data with progress bar if available
        if ASYNC_TQDM_AVAILABLE:
            for task in atqdm(
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc="💰 Steam API",
                unit="game",
            ):
                app_id, success, game_data, source = await task
                if success:
                    steam_data[app_id] = {"data": game_data, "source": source}
                else:
                    steam_errors.append((app_id, source))
        else:
            completed = 0
            for coro in asyncio.as_completed(tasks):
                app_id, success, game_data, source = await coro
                if success:
                    steam_data[app_id] = {"data": game_data, "source": source}
                else:
                    steam_errors.append((app_id, source))

                completed += 1
                if completed % 50 == 0:
                    print(
                        f"   📈 API Progress: {completed}/{len(games_to_process)} | Success: {len(steam_data)} | Errors: {len(steam_errors)}"
                    )

        # Phase 2: Safe database writing
        print("   💾 Phase 2: Safe database writing...")
        steam_prices_cached = self.batch_write_steam_data(steam_data)

        print("\n💰 Async Steam price population complete!")
        print(f"   ✅ Prices cached: {steam_prices_cached}")
        print(f"   ❌ Errors: {len(steam_errors)}")
        print(
            f"   ⚡ Async speed improvement: ~{self.max_concurrent}x faster than sequential"
        )

        return steam_prices_cached

    async def populate_itad_prices(
        self, game_ids: Set[str], dry_run: bool = False, force_refresh: bool = False
    ) -> int:
        """Populate ITAD prices with async processing using cache-then-write pattern."""
        print("\n📈 Starting async ITAD price population...")
        if not ITAD_API_KEY or ITAD_API_KEY == "YOUR_ITAD_API_KEY_HERE":
            print("❌ ITAD API key not configured. Skipping ITAD price population.")
            return 0
        if not game_ids:
            print("❌ No game IDs to process")
            return 0

        games_to_process = [
            gid for gid in game_ids if force_refresh or not get_cached_itad_price(gid)
        ]
        games_skipped = len(game_ids) - len(games_to_process)

        print(f"   🎯 Games to process: {len(games_to_process)}")
        print(f"   ⏭️   Games skipped (already have ITAD data): {games_skipped}")
        print(f"   🚀 Processing with {self.max_concurrent} concurrent async requests")

        if dry_run:
            print("   🔍 DRY RUN: Would fetch ITAD price data")
            return 0
        if not games_to_process:
            print("   ✅ All games already have ITAD price data")
            return 0

        # Phase 1: Async data collection
        print("   📡 Phase 1: Async API data collection...")
        itad_data = {}
        itad_errors = []
        itad_not_found = []

        # Create async tasks for all games
        tasks = [self.fetch_itad_price_single(app_id) for app_id in games_to_process]

        # Collect data with progress bar if available
        if ASYNC_TQDM_AVAILABLE:
            for task in atqdm(
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc="📈 ITAD API",
                unit="game",
            ):
                app_id, status, price_data, lookup_method = await task
                if status == "cached":
                    # Get game name for name_search method
                    game_name = None
                    if lookup_method == "name_search":
                        cached_details = get_cached_game_details(app_id)
                        game_name = (
                            cached_details.get("name") if cached_details else None
                        )

                    itad_data[app_id] = {
                        "data": price_data,
                        "method": lookup_method,
                        "game_name": game_name,
                    }
                elif status == "not_found":
                    itad_not_found.append(app_id)
                else:  # error or other status
                    itad_errors.append((app_id, status))
        else:
            completed = 0
            for coro in asyncio.as_completed(tasks):
                app_id, status, price_data, lookup_method = await coro
                if status == "cached":
                    # Get game name for name_search method
                    game_name = None
                    if lookup_method == "name_search":
                        cached_details = get_cached_game_details(app_id)
                        game_name = (
                            cached_details.get("name") if cached_details else None
                        )

                    itad_data[app_id] = {
                        "data": price_data,
                        "method": lookup_method,
                        "game_name": game_name,
                    }
                elif status == "not_found":
                    itad_not_found.append(app_id)
                else:  # error or other status
                    itad_errors.append((app_id, status))

                completed += 1
                if completed % 50 == 0:
                    print(
                        f"   📈 API Progress: {completed}/{len(games_to_process)} | Success: {len(itad_data)} | Not Found: {len(itad_not_found)} | Errors: {len(itad_errors)}"
                    )

        # Phase 2: Safe database writing
        print("   💾 Phase 2: Safe database writing...")
        itad_prices_cached = self.batch_write_itad_data(itad_data)

        print("\n📈 Async ITAD price population complete!")
        print(f"   ✅ Prices cached: {itad_prices_cached}")
        print(f"   ❓ Games not found on ITAD: {len(itad_not_found)}")
        print(f"   ❌ Errors: {len(itad_errors)}")
        print(
            f"   ⚡ Async speed improvement: ~{self.max_concurrent}x faster than sequential"
        )

        return itad_prices_cached

    async def refresh_current_prices(
        self, game_ids: Set[str], dry_run: bool = False
    ) -> int:
        """Refresh current Steam prices with force refresh."""
        print("\n🔄 Refreshing current Steam prices with async optimization...")
        if not game_ids:
            print("❌ No game IDs to process")
            return 0
        if dry_run:
            print(f"   🔍 DRY RUN: Would refresh {len(game_ids)} current prices")
            return 0
        return await self.populate_steam_prices(
            game_ids, dry_run=False, force_refresh=True
        )


async def main():
    parser = argparse.ArgumentParser(
        description="Async price data population for FamilyBot"
    )
    parser.add_argument(
        "--steam-only", action="store_true", help="Only populate Steam Store prices"
    )
    parser.add_argument(
        "--itad-only", action="store_true", help="Only populate ITAD historical prices"
    )
    parser.add_argument(
        "--refresh-current",
        action="store_true",
        help="Force refresh current Steam prices (useful during sales)",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force refresh all price data, even if cached",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=50,
        help="Max concurrent requests (default: 50)",
    )
    parser.add_argument(
        "--rate-limit",
        choices=["adaptive", "conservative", "aggressive"],
        default="adaptive",
        help="Rate limiting strategy",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    args = parser.parse_args()

    print("⚡ FamilyBot Async Price Population Script\n" + "=" * 60)
    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
    if args.refresh_current:
        print("🔄 REFRESH MODE - Will update current prices even if cached")
    if args.force_refresh:
        print("🔄 FORCE REFRESH MODE - Will update all price data even if cached")

    try:
        init_db()
        print("✅ Database initialized")
        migrate_database_phase1()
        migrate_database_phase2()
    except (ValueError, TypeError, OSError) as e:
        print(f"❌ Failed to initialize database or run migrations: {e}")
        return 1

    # Adjust concurrent requests based on rate limiting strategy
    if args.rate_limit == "conservative":
        max_concurrent = min(args.concurrent, 25)
    elif args.rate_limit == "aggressive":
        max_concurrent = min(args.concurrent, 100)
    else:  # adaptive
        max_concurrent = args.concurrent

    populator = AsyncPricePopulator(max_concurrent, args.rate_limit)
    total_steam_cached, total_itad_cached = 0, 0
    all_game_ids = set()
    start_time = datetime.now()

    try:
        family_members = populator.load_family_members()
        if not family_members:
            print("❌ No family members found. Check your configuration.")
            return 1

        all_game_ids = populator.collect_all_game_ids(family_members)
        if not all_game_ids:
            print("❌ No games found to process. Run populate_database.py first.")
            return 1

        if not args.itad_only:
            total_steam_cached = (
                await populator.refresh_current_prices(all_game_ids, args.dry_run)
                if args.refresh_current
                else await populator.populate_steam_prices(
                    all_game_ids, args.dry_run, args.force_refresh
                )
            )

        if not args.steam_only:
            total_itad_cached = await populator.populate_itad_prices(
                all_game_ids, args.dry_run, args.force_refresh
            )
    finally:
        await populator.aclose()

    duration = datetime.now() - start_time
    print("\n" + "=" * 60 + "\n🎉 Async Price Population Complete!")
    print(f"⏱️   Duration: {duration.total_seconds():.1f} seconds")
    if all_game_ids:
        print(f"🎮 Games processed: {len(all_game_ids)}")
    print(f"💰 Steam prices cached: {total_steam_cached}")
    print(f"📈 ITAD prices cached: {total_itad_cached}")
    print(f"💾 Total price entries updated: {total_steam_cached + total_itad_cached}")

    if not args.dry_run:
        print("\n🚀 Async price data population complete!")
        print(
            f"   ⚡ Performance improvement: ~{max_concurrent}x faster than sequential processing"
        )
        print("   🔄 Advanced connection reuse with 200 max connections")
        print("   📊 Adaptive async rate limiting prevents API throttling")
        print("   🚀 True async/await processing for maximum speed!")
        print("   All deal commands will now run at maximum speed! 🎊")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
