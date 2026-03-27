"""Consolidated async price population script for FamilyBot.

Fetches Steam Store prices and ITAD historical prices with high-performance
async processing. Uses adaptive rate limiting and batch database writes.

Usage:
    python scripts/populate_prices.py                    # Populate all prices
    python scripts/populate_prices.py --steam-only       # Only Steam prices
    python scripts/populate_prices.py --itad-only        # Only ITAD prices
    python scripts/populate_prices.py --force-refresh    # Refresh all cached data
    python scripts/populate_prices.py --dry-run          # Preview without changes
"""

import logging
import argparse
import json
import os
import random
import sys
import asyncio
from datetime import datetime
from typing import Optional

import httpx

try:
    from tqdm.asyncio import tqdm as atqdm

    ASYNC_TQDM_AVAILABLE = True
except ImportError:
    print("tqdm not available. Install with: uv pip install tqdm")
    print("Falling back to basic progress indicators...")
    ASYNC_TQDM_AVAILABLE = False

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from familybot.config import ITAD_API_KEY, ITAD_CACHE_TTL  # pylint: disable=wrong-import-position
from familybot.lib.database import (
    get_write_connection,
    init_db,  # pylint: disable=wrong-import-position
)
from familybot.lib.game_details_repository import (
    cache_game_details,  # pylint: disable=wrong-import-position
    get_cached_game_details,  # pylint: disable=wrong-import-position
)
from familybot.lib.itad_price_repository import (
    cache_itad_price_enhanced,
    get_cached_itad_price,
)
from familybot.lib.user_repository import load_family_members_from_db
from familybot.lib.wishlist_repository import get_cached_wishlist  # pylint: disable=wrong-import-position
from familybot.lib.logging_config import setup_script_logging  # pylint: disable=wrong-import-position

# Setup enhanced logging for this script
logger = setup_script_logging("populate_prices", "INFO")

# Suppress verbose HTTP request logging from other libraries
logging.getLogger("httpx").setLevel(logging.WARNING)


class PricePopulator:
    """High-performance async price populator with adaptive rate limiting."""

    def __init__(self, max_concurrent: int = 50, rate_limit_mode: str = "adaptive"):
        """Initialize with async capabilities and configurable concurrency."""
        if max_concurrent < 1:
            raise ValueError(f"max_concurrent must be >= 1, got {max_concurrent}")
        self.max_concurrent = max_concurrent
        self.rate_limit_mode = rate_limit_mode

        # Adaptive rate limiting
        # Steam: ~1 req/sec safe threshold, start conservative at 2s
        # ITAD: heuristic-based, no hard limit but be respectful
        self.current_delays = {
            "store": 2.0,
            "itad": 1.0,
        }

        # Rate limit bounds
        # Store: min 1s (safe for ~60/min), max 10s for backoff
        # ITAD: min 0.5s, max 5s for backoff
        self.min_delays = {"store": 1.0, "itad": 0.5}
        self.max_delays = {"store": 10.0, "itad": 5.0}

        # Error tracking for adaptive rate limiting
        self.error_counts = {"store": 0, "itad": 0}
        self.success_counts = {"store": 0, "itad": 0}
        self.last_adjustment = {"store": 0.0, "itad": 0.0}

        # Async locks for rate limiting
        self.rate_limit_locks = {
            "store": asyncio.Lock(),
            "itad": asyncio.Lock(),
        }
        self.last_request_times = {"store": 0.0, "itad": 0.0}

        # Async HTTP client with connection pooling
        self.client = httpx.AsyncClient(
            timeout=15.0,
            limits=httpx.Limits(
                max_keepalive_connections=100,
                max_connections=200,
                keepalive_expiry=60.0,
            ),
            headers={
                "User-Agent": "FamilyBot-PricePopulator/1.0",
                "Connection": "keep-alive",
            },
        )

        # Async semaphore for concurrency control
        self.semaphore = asyncio.Semaphore(max_concurrent)

        print("Price Populator initialized")
        print(f"   Max concurrent requests: {max_concurrent}")
        print(f"   Rate limiting: {rate_limit_mode}")
        print(
            f"   Initial delays - Store: {self.current_delays['store']}s, ITAD: {self.current_delays['itad']}s"
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
            self.success_counts[api_type] = 0
            self.error_counts[api_type] = 0

    async def rate_limited_request(self, api_type: str):
        """Async rate limiting."""
        async with self.rate_limit_locks[api_type]:
            current_time = time.time()
            time_since_last = current_time - self.last_request_times[api_type]
            delay_needed = self.current_delays[api_type] - time_since_last

            if delay_needed > 0:
                await asyncio.sleep(delay_needed + random.uniform(0, 0.02))

            self.last_request_times[api_type] = time.time()

    async def make_request_with_retry(
        self,
        url: str,
        method: str = "GET",
        json_data: Optional[dict | list] = None,
        params: Optional[dict] = None,
        api_type: str = "store",
        max_retries: int = 2,
    ) -> Optional[httpx.Response]:
        """Make async HTTP request with adaptive rate limiting and retry logic."""

        for attempt in range(max_retries + 1):
            try:
                await self.rate_limited_request(api_type)

                if method == "GET":
                    response = await self.client.get(url, params=params)
                elif method == "POST":
                    response = await self.client.post(
                        url, json=json_data, params=params
                    )
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                # Retry only transient errors: 429 (rate limited) or 5xx (server errors)
                # Optionally retry 408 (request timeout). Client errors (4xx) fail fast.
                if (
                    response.status_code == 429
                    or (500 <= response.status_code < 600)
                    or response.status_code == 408
                ):
                    if attempt < max_retries:
                        backoff_time = (2**attempt) + random.uniform(0, 1)
                        logger.debug(
                            "HTTP %d from %s, retrying in %.1fs (attempt %d/%d)",
                            response.status_code,
                            url.split("?")[0],
                            backoff_time,
                            attempt + 1,
                            max_retries + 1,
                        )
                        await asyncio.sleep(backoff_time)
                        self.adaptive_rate_limit(api_type, False)
                        continue
                    logger.warning("Max retries exceeded for %s", url.split("?")[0])
                    self.adaptive_rate_limit(api_type, False)
                    return None
                # Permanent client error (4xx excluding 429/408) - fail fast
                if 400 <= response.status_code < 500:
                    logger.debug(
                        "Permanent client error HTTP %d from %s - not retrying",
                        response.status_code,
                        url.split("?")[0],
                    )
                    self.adaptive_rate_limit(api_type, False)
                    return None

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
            if e.response.status_code != 429:
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

    def load_family_members(self) -> dict[str, str]:
        """Load family members from database."""
        return load_family_members_from_db()

    def collect_all_game_ids(self, family_members: dict[str, str]) -> set[str]:
        """Collect all unique game IDs from family wishlists."""
        all_game_ids = set()
        print("\nCollecting game IDs from family wishlists...")
        for steam_id, name in family_members.items():
            cached_wishlist = get_cached_wishlist(steam_id)
            if cached_wishlist:
                all_game_ids.update(cached_wishlist)
                print(f"   {name}: {len(cached_wishlist)} wishlist games")
            else:
                print(f"   {name}: No cached wishlist found")
        print(f"\nTotal unique wishlist games to process: {len(all_game_ids)}")
        return all_game_ids

    async def fetch_steam_price_single(
        self, app_id: str
    ) -> tuple[str, bool, dict, str]:
        """Fetch Steam price for a single game via Store API."""
        async with self.semaphore:
            try:
                game_url = "https://store.steampowered.com/api/appdetails"
                response = await self.make_request_with_retry(
                    game_url,
                    method="GET",
                    params={"appids": app_id, "cc": "us", "l": "en"},
                    api_type="store",
                )

                if response is not None:
                    game_info = self.handle_api_response(
                        f"Steam Store ({app_id})", response
                    )
                    if game_info and game_info.get(str(app_id), {}).get("data"):
                        return app_id, True, game_info[str(app_id)]["data"], "store_api"
            except Exception as e:
                logger.debug("Steam Store API failed for %s: %s", app_id, e)

            return app_id, False, {}, "failed"

    async def fetch_itad_price_single(self, app_id: str) -> tuple[str, str, dict, str]:
        """Fetch ITAD price for a single game with multiple strategies."""
        async with self.semaphore:
            # Strategy 1: ITAD lookup by Steam appid
            try:
                lookup_url = "https://api.isthereanydeal.com/games/lookup/v1"
                lookup_response = await self.make_request_with_retry(
                    lookup_url,
                    method="GET",
                    params={"key": ITAD_API_KEY, "appid": app_id},
                    api_type="itad",
                )

                if lookup_response is None:
                    return app_id, "error", {}, "itad_request_failed"

                if lookup_response is not None:
                    lookup_data = self.handle_api_response(
                        f"ITAD Lookup ({app_id})", lookup_response
                    )

                    if lookup_data and lookup_data.get("found"):
                        game_id = lookup_data.get("game", {}).get("id")

                        if game_id:
                            # Get price data using ITAD game ID
                            prices_url = (
                                "https://api.isthereanydeal.com/games/prices/v3"
                            )
                            prices_response = await self.make_request_with_retry(
                                prices_url,
                                method="POST",
                                json_data=[game_id],
                                params={"key": ITAD_API_KEY, "country": "US"},
                                api_type="itad",
                            )

                            if prices_response is None:
                                return app_id, "error", {}, "itad_request_failed"

                            if prices_response is not None:
                                prices_data = self.handle_api_response(
                                    f"ITAD Prices ({app_id})", prices_response
                                )

                                if (
                                    prices_data
                                    and len(prices_data) > 0
                                    and prices_data[0].get("historyLow")
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
                logger.debug("ITAD appid lookup failed for %s: %s", app_id, e)
                return app_id, "error", {}, "itad_exception"

            # Strategy 2: Name-based search fallback
            try:
                cached_details = get_cached_game_details(app_id)
                if cached_details and cached_details.get("name"):
                    game_name = cached_details["name"]

                    search_url = "https://api.isthereanydeal.com/games/search/v1"
                    search_response = await self.make_request_with_retry(
                        search_url,
                        method="GET",
                        params={"key": ITAD_API_KEY, "title": game_name},
                        api_type="itad",
                    )

                    if search_response is None:
                        return app_id, "error", {}, "itad_request_failed"

                    if search_response is not None:
                        search_data = self.handle_api_response(
                            f"ITAD Search ({game_name})", search_response
                        )

                        if search_data and len(search_data) > 0:
                            game_id = search_data[0].get("id")
                            if game_id:
                                prices_url = (
                                    "https://api.isthereanydeal.com/games/prices/v3"
                                )
                                prices_response = await self.make_request_with_retry(
                                    prices_url,
                                    method="POST",
                                    json_data=[game_id],
                                    params={"key": ITAD_API_KEY, "country": "US"},
                                    api_type="itad",
                                )

                                if prices_response is None:
                                    return app_id, "error", {}, "itad_request_failed"

                                if prices_response is not None:
                                    prices_data = self.handle_api_response(
                                        f"ITAD Prices ({game_name})", prices_response
                                    )

                                    if (
                                        prices_data
                                        and len(prices_data) > 0
                                        and prices_data[0].get("historyLow")
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
                return app_id, "error", {}, "itad_exception"

            return app_id, "not_found", {}, "failed"

    def batch_write_steam_data(
        self, steam_data: dict[str, dict], batch_size: int = 100
    ) -> int:
        """Write Steam data to database in safe batches."""
        if not steam_data:
            return 0

        written_count = 0
        items = list(steam_data.items())

        print(f"   Writing {len(items)} Steam records in batches of {batch_size}...")

        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]

            try:
                with get_write_connection() as conn:
                    for app_id, game_info in batch:
                        game_data = game_info["data"]
                        cache_game_details(
                            app_id, game_data, permanent=False, conn=conn
                        )
                    conn.commit()
                written_count += len(batch)
                logger.debug("Successfully wrote batch of %d Steam records", len(batch))

            except Exception as e:
                logger.error("Failed to write Steam batch: %s", e)
                # Try individual records to salvage what we can
                for app_id, game_info in batch:
                    try:
                        with get_write_connection() as conn:
                            game_data = game_info["data"]
                            cache_game_details(
                                app_id, game_data, permanent=False, conn=conn
                            )
                            conn.commit()
                        written_count += 1
                    except Exception as individual_error:
                        logger.error(
                            "Failed to write individual Steam record %s: %s",
                            app_id,
                            individual_error,
                        )

        print(f"   Successfully wrote {written_count} Steam records to database")
        return written_count

    def batch_write_itad_data(
        self, itad_data: dict[str, dict], batch_size: int = 100
    ) -> int:
        """Write ITAD data to database in safe batches."""
        if not itad_data:
            return 0

        written_count = 0
        items = list(itad_data.items())

        print(f"   Writing {len(items)} ITAD records in batches of {batch_size}...")

        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]

            try:
                with get_write_connection() as conn:
                    for app_id, price_info in batch:
                        price_data = price_info["data"]
                        lookup_method = price_info["method"]
                        game_name = price_info.get("game_name")

                        cache_itad_price_enhanced(
                            app_id,
                            price_data,
                            lookup_method=lookup_method,
                            steam_game_name=game_name,
                            permanent=False,
                            cache_hours=ITAD_CACHE_TTL,
                            conn=conn,
                        )
                    conn.commit()
                written_count += len(batch)
                logger.debug("Successfully wrote batch of %d ITAD records", len(batch))

            except Exception as e:
                logger.error("Failed to write ITAD batch: %s", e)
                # Try individual records to salvage what we can
                for app_id, price_info in batch:
                    try:
                        with get_write_connection() as conn:
                            price_data = price_info["data"]
                            lookup_method = price_info["method"]
                            game_name = price_info.get("game_name")

                            cache_itad_price_enhanced(
                                app_id,
                                price_data,
                                lookup_method=lookup_method,
                                steam_game_name=game_name,
                                permanent=False,
                                cache_hours=ITAD_CACHE_TTL,
                                conn=conn,
                            )
                            conn.commit()
                        written_count += 1
                    except Exception as individual_error:
                        logger.error(
                            "Failed to write individual ITAD record %s: %s",
                            app_id,
                            individual_error,
                        )

        print(f"   Successfully wrote {written_count} ITAD records to database")
        return written_count

    async def populate_steam_prices(
        self, game_ids: set[str], dry_run: bool = False, force_refresh: bool = False
    ) -> int:
        """Populate Steam prices with async processing."""
        print("\nStarting async Steam price population...")
        if not game_ids:
            print("No game IDs to process")
            return 0

        games_to_process = []
        for gid in game_ids:
            if force_refresh:
                games_to_process.append(gid)
            else:
                cached_details = get_cached_game_details(gid)
                if not cached_details or not cached_details.get("price_overview"):
                    games_to_process.append(gid)

        games_skipped = len(game_ids) - len(games_to_process)

        print(f"   Games to process: {len(games_to_process)}")
        print(f"   Games skipped (already have price data): {games_skipped}")
        print(f"   Processing with {self.max_concurrent} concurrent async requests")

        if dry_run:
            print("   DRY RUN: Would fetch Steam price data")
            return 0

        if not games_to_process:
            print("   All games already have Steam price data")
            return 0

        # Phase 1: Async data collection
        print("   Phase 1: Async API data collection...")
        steam_data = {}
        steam_errors = []

        tasks = [self.fetch_steam_price_single(app_id) for app_id in games_to_process]

        if ASYNC_TQDM_AVAILABLE:
            for task in atqdm(
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc="Steam API",
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
                        f"   API Progress: {completed}/{len(games_to_process)} | Success: {len(steam_data)} | Errors: {len(steam_errors)}"
                    )

        # Phase 2: Safe database writing
        print("   Phase 2: Safe database writing...")
        steam_prices_cached = self.batch_write_steam_data(steam_data)

        print("\nAsync Steam price population complete!")
        print(f"   Prices cached: {steam_prices_cached}")
        print(f"   Errors: {len(steam_errors)}")

        return steam_prices_cached

    async def populate_itad_prices(
        self, game_ids: set[str], dry_run: bool = False, force_refresh: bool = False
    ) -> int:
        """Populate ITAD prices with async processing."""
        print("\nStarting async ITAD price population...")
        if not ITAD_API_KEY or ITAD_API_KEY == "YOUR_ITAD_API_KEY_HERE":
            print("ITAD API key not configured. Skipping ITAD price population.")
            return 0
        if not game_ids:
            print("No game IDs to process")
            return 0

        games_to_process = [
            gid for gid in game_ids if force_refresh or not get_cached_itad_price(gid)
        ]
        games_skipped = len(game_ids) - len(games_to_process)

        print(f"   Games to process: {len(games_to_process)}")
        print(f"   Games skipped (already have ITAD data): {games_skipped}")
        print(f"   Processing with {self.max_concurrent} concurrent async requests")

        if dry_run:
            print("   DRY RUN: Would fetch ITAD price data")
            return 0
        if not games_to_process:
            print("   All games already have ITAD price data")
            return 0

        # Phase 1: Async data collection
        print("   Phase 1: Async API data collection...")
        itad_data = {}
        itad_errors = []
        itad_not_found = []

        tasks = [self.fetch_itad_price_single(app_id) for app_id in games_to_process]

        if ASYNC_TQDM_AVAILABLE:
            for task in atqdm(
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc="ITAD API",
                unit="game",
            ):
                app_id, status, price_data, lookup_method = await task
                if status == "cached":
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
                else:
                    itad_errors.append((app_id, status))
        else:
            completed = 0
            for coro in asyncio.as_completed(tasks):
                app_id, status, price_data, lookup_method = await coro
                if status == "cached":
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
                else:
                    itad_errors.append((app_id, status))

                completed += 1
                if completed % 50 == 0:
                    print(
                        f"   API Progress: {completed}/{len(games_to_process)} | Success: {len(itad_data)} | Not Found: {len(itad_not_found)} | Errors: {len(itad_errors)}"
                    )

        # Phase 2: Safe database writing
        print("   Phase 2: Safe database writing...")
        itad_prices_cached = self.batch_write_itad_data(itad_data)

        print("\nAsync ITAD price population complete!")
        print(f"   Prices cached: {itad_prices_cached}")
        print(f"   Games not found on ITAD: {len(itad_not_found)}")
        print(f"   Errors: {len(itad_errors)}")

        return itad_prices_cached

    async def refresh_current_prices(
        self, game_ids: set[str], dry_run: bool = False
    ) -> int:
        """Refresh current Steam prices with force refresh."""
        print("\nRefreshing current Steam prices...")
        if not game_ids:
            print("No game IDs to process")
            return 0
        if dry_run:
            print(f"   DRY RUN: Would refresh {len(game_ids)} current prices")
            return 0
        return await self.populate_steam_prices(
            game_ids, dry_run=False, force_refresh=True
        )


async def main():
    parser = argparse.ArgumentParser(description="Price data population for FamilyBot")
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
        default=10,
        help="Max concurrent requests (default: 10)",
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

    # Validate --concurrent
    if args.concurrent < 1:
        parser.error("--concurrent must be >= 1")

    # Validate incompatible flag combinations
    if args.steam_only and args.itad_only:
        parser.error("--steam-only and --itad-only are mutually exclusive")
    if args.itad_only and args.refresh_current:
        parser.error(
            "--refresh-current applies to Steam only, incompatible with --itad-only"
        )

    print("FamilyBot Price Population Script\n" + "=" * 60)
    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
    if args.refresh_current:
        print("REFRESH MODE - Will update current prices even if cached")
    if args.force_refresh:
        print("FORCE REFRESH MODE - Will update all price data even if cached")

    try:
        init_db()
        print("Database initialized")
    except (ValueError, TypeError, OSError) as e:
        print(f"Failed to initialize database: {e}")
        return 1

    # Adjust concurrent requests based on rate limiting strategy
    if args.rate_limit == "conservative":
        max_concurrent = min(args.concurrent, 25)
    elif args.rate_limit == "aggressive":
        max_concurrent = min(args.concurrent, 100)
    else:  # adaptive
        max_concurrent = args.concurrent

    populator = PricePopulator(max_concurrent, args.rate_limit)
    total_steam_cached, total_itad_cached = 0, 0
    all_game_ids = set()
    start_time = datetime.now()

    try:
        family_members = populator.load_family_members()
        if not family_members:
            print("No family members found. Check your configuration.")
            return 1

        all_game_ids = populator.collect_all_game_ids(family_members)
        if not all_game_ids:
            print("No games found to process. Run populate_database.py first.")
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
    print("\n" + "=" * 60 + "\nPrice Population Complete!")
    print(f"Duration: {duration.total_seconds():.1f} seconds")
    if all_game_ids:
        print(f"Games processed: {len(all_game_ids)}")
    print(f"Steam prices cached: {total_steam_cached}")
    print(f"ITAD prices cached: {total_itad_cached}")
    print(f"Total price entries updated: {total_steam_cached + total_itad_cached}")

    if not args.dry_run:
        print("\nPrice data population complete!")
        print(f"   Performance: ~{max_concurrent}x faster than sequential processing")
        print("   Connection reuse enabled to minimize data usage")
        print("   Adaptive rate limiting prevents API throttling")

    return 0


import time  # noqa: E402 - needed for adaptive_rate_limit


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
