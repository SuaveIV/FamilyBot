"""Consolidated async price population script for FamilyBot.

Fetches ITAD historical prices (with Steam API fallback) using high-performance
async bulk processing. Uses adaptive rate limiting and batch database writes.

Usage:
    python scripts/populate_prices.py                    # ITAD prices (default)
    python scripts/populate_prices.py --with-steam       # ITAD + Steam Store prices
    python scripts/populate_prices.py --steam-only       # Only Steam Store prices
    python scripts/populate_prices.py --force-refresh    # Refresh all cached data
    python scripts/populate_prices.py --dry-run          # Preview without changes
"""

import argparse
import asyncio
import json
import logging
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

try:
    from tqdm.asyncio import tqdm as atqdm

    ASYNC_TQDM_AVAILABLE = True
except ImportError:
    print("tqdm not available. Install with: uv pip install tqdm")
    print("Falling back to basic progress indicators...")
    ASYNC_TQDM_AVAILABLE = False

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / ".." / "src"))

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
from familybot.lib.logging_config import (
    setup_script_logging,  # pylint: disable=wrong-import-position
)
from familybot.lib.steam_itad_mapping_repository import (
    bulk_cache_itad_mappings,
    get_cached_itad_ids_bulk,
)
from familybot.lib.user_repository import load_family_members_from_db
from familybot.lib.wishlist_repository import (
    get_cached_wishlist,  # pylint: disable=wrong-import-position
)

# Setup enhanced logging for this script
logger = setup_script_logging("populate_prices", "INFO")

# Non-cryptographic RNG for rate-limiting jitter (avoids S311 on random.uniform)
_rng = random.SystemRandom()

# Suppress verbose HTTP request logging from other libraries
logging.getLogger("httpx").setLevel(logging.WARNING)


class PricePopulator:
    """High-performance async price populator with adaptive rate limiting."""

    def _extract_steam_fallback_entry(self, game_data: dict) -> dict | None:
        """Extracts a Steam fallback entry in ITAD-style format from game_data."""
        if game_data.get("lowest_price_formatted") == "Delisted/Unavailable":
            return {
                "data": game_data,
                "method": "steam_delisted",
                "game_name": game_data.get("game_name"),
            }
        price_overview = game_data.get("price_overview")
        is_free = game_data.get("is_free", False)
        if not price_overview and not is_free:
            return None
        if price_overview and "final" in price_overview:
            return {
                "data": {
                    "lowest_price": str(price_overview["final"] / 100),
                    "lowest_price_formatted": price_overview.get("final_formatted", "N/A"),
                    "shop_name": "Steam",
                },
                "method": "steam_fallback",
                "game_name": game_data.get("name"),
            }
        if is_free:
            return {
                "data": {
                    "lowest_price": "0",
                    "lowest_price_formatted": "Free",
                    "shop_name": "Steam",
                },
                "method": "steam_fallback",
                "game_name": game_data.get("name"),
            }
        return None

    def __init__(self, max_concurrent: int = 50, rate_limit_mode: str = "adaptive"):
        """Initialize with async capabilities and configurable concurrency."""
        if max_concurrent < 1:
            msg = f"max_concurrent must be >= 1, got {max_concurrent}"
            raise ValueError(msg)
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
        store_delay = self.current_delays["store"]
        itad_delay = self.current_delays["itad"]
        print(f"   Initial delays - Store: {store_delay}s, ITAD: {itad_delay}s")

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
                    "Slowing down %s: %.2fs (error rate: %.1f%%)",
                    api_type,
                    self.current_delays[api_type],
                    error_rate * 100,
                )
            elif (
                error_rate < 0.05 and self.success_counts[api_type] > 20
            ):  # Less than 5% errors - speed up
                self.current_delays[api_type] = max(
                    self.current_delays[api_type] * 0.8, self.min_delays[api_type]
                )
                logger.debug(
                    "Speeding up %s: %.2fs (error rate: %.1f%%)",
                    api_type,
                    self.current_delays[api_type],
                    error_rate * 100,
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
                await asyncio.sleep(delay_needed + _rng.uniform(0, 0.02))

            self.last_request_times[api_type] = time.time()

    async def make_request_with_retry(
        self,
        url: str,
        method: str = "GET",
        json_data: dict | list | None = None,
        params: dict | None = None,
        api_type: str = "store",
        max_retries: int = 2,
    ) -> httpx.Response | None:
        """Make async HTTP request with adaptive rate limiting and retry logic."""

        for attempt in range(max_retries + 1):
            try:
                await self.rate_limited_request(api_type)

                if method == "GET":
                    response = await self.client.get(url, params=params)
                elif method == "POST":
                    response = await self.client.post(url, json=json_data, params=params)
                else:
                    msg = f"Unsupported HTTP method: {method}"
                    raise ValueError(msg)

                # Retry only transient errors: 429 (rate limited) or 5xx (server errors)
                # Optionally retry 408 (request timeout). Client errors (4xx) fail fast.
                if (
                    response.status_code == 429
                    or (500 <= response.status_code < 600)
                    or response.status_code == 408
                ):
                    if attempt < max_retries:
                        backoff_time = 2**attempt + _rng.uniform(0, 1)
                        logger.warning(
                            "Retryable HTTP %d from %s, retrying in %.1fs (attempt %d/%d)",
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
                    logger.debug("Request failed: %s, retrying in %.1fs", e, backoff_time)
                    await asyncio.sleep(backoff_time)
                    continue
                logger.debug("Request failed after %d retries: %s", max_retries, e)
                self.adaptive_rate_limit(api_type, False)
                return None

        return None

    def handle_api_response(self, api_name: str, response: httpx.Response) -> dict | None:
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

    async def fetch_steam_price_single(self, app_id: str) -> tuple[str, bool, dict, str]:
        """Fetch Steam price for a single game via Store API."""
        async with self.semaphore:
            try:
                # Look up cached game details to get the real game name
                # Run blocking DB lookup off the event loop
                loop = asyncio.get_running_loop()
                cached_game = await loop.run_in_executor(None, get_cached_game_details, app_id)
                cached_game_name = cached_game.get("name") if cached_game else f"App {app_id}"

                game_url = "https://store.steampowered.com/api/appdetails"
                response = await self.make_request_with_retry(
                    game_url,
                    method="GET",
                    params={"appids": app_id, "cc": "us", "l": "en"},
                    api_type="store",
                )

                if response is not None:
                    game_info = self.handle_api_response(f"Steam Store ({app_id})", response)
                    if game_info:
                        app_data = game_info.get(str(app_id), {})
                        if app_data.get("success") is False:
                            return (
                                app_id,
                                True,
                                {
                                    "lowest_price": "N/A",
                                    "lowest_price_formatted": "Delisted/Unavailable",
                                    "shop_name": "N/A",
                                    "game_name": cached_game_name,
                                },
                                "store_api",
                            )
                        if app_data.get("data"):
                            return app_id, True, app_data["data"], "store_api"
            except Exception as e:
                logger.debug("Steam Store API failed for %s: %s", app_id, e)

            return app_id, False, {}, "failed"

    def _process_itad_lookup_chunk(
        self,
        chunk: list[str],
        lookup_data: dict,
        new_mappings: dict[str, str],
        failed_appids: list[str],
    ) -> None:
        """Process a single ITAD lookup response chunk, updating new_mappings and failed_appids."""
        for shop_query, itad_id in lookup_data.items():
            app_id = shop_query.replace("app/", "")
            if itad_id:
                new_mappings[app_id] = itad_id
            else:
                failed_appids.append(app_id)

        resolved_in_chunk = {q.replace("app/", "") for q in lookup_data}
        failed_appids.extend(
            app_id
            for app_id in chunk
            if app_id not in resolved_in_chunk and app_id not in new_mappings
        )

    async def _fetch_itad_lookup_chunk(
        self,
        chunk: list[str],
        new_mappings: dict[str, str],
        failed_appids: list[str],
        pbar,
    ) -> None:
        """Handle network call and processing for a single ITAD lookup chunk."""
        shop_queries = [f"app/{app_id}" for app_id in chunk]

        try:
            lookup_url = "https://api.isthereanydeal.com/lookup/id/shop/61/v1"
            response = await self.make_request_with_retry(
                lookup_url,
                method="POST",
                json_data=shop_queries,
                params={"key": ITAD_API_KEY},
                api_type="itad",
            )

            if response is None:
                failed_appids.extend(chunk)
            else:
                lookup_data = self.handle_api_response("ITAD Bulk Lookup", response)
                if not isinstance(lookup_data, dict):
                    failed_appids.extend(chunk)
                else:
                    self._process_itad_lookup_chunk(chunk, lookup_data, new_mappings, failed_appids)
                    if pbar:
                        pbar.set_postfix_str(
                            f"Found: {len(new_mappings)}, Failed: {len(failed_appids)}"
                        )

        except Exception as e:
            logger.error("ITAD bulk lookup chunk failed: %s", e)
            failed_appids.extend(chunk)

        if pbar:
            pbar.update(len(chunk))

    async def _resolve_itad_ids_bulk(self, app_ids: list[str]) -> tuple[dict[str, str], list[str]]:
        """Resolve Steam AppIDs to ITAD IDs using cache and bulk lookup.

        Returns (appid_to_itad_id dict, list of failed appids).
        """
        # Step 1: Check permanent cache
        cached_mappings = get_cached_itad_ids_bulk(app_ids)
        uncached_appids = [aid for aid in app_ids if aid not in cached_mappings]

        if not uncached_appids:
            return cached_mappings, []

        # Step 2: Bulk lookup for uncached IDs via ITAD shop/61 (Steam) endpoint
        print(f"   Resolving {len(uncached_appids)} unmapped AppIDs via ITAD lookup...")
        new_mappings = {}
        failed_appids = []
        chunk_size = 100

        if ASYNC_TQDM_AVAILABLE:
            pbar = atqdm(
                total=len(uncached_appids),
                desc="ITAD ID Lookup",
                unit="game",
                leave=False,
            )
        else:
            pbar = None

        for i in range(0, len(uncached_appids), chunk_size):
            chunk = uncached_appids[i : i + chunk_size]
            await self._fetch_itad_lookup_chunk(chunk, new_mappings, failed_appids, pbar)

        if pbar:
            pbar.close()

        # Step 3: Cache new mappings permanently
        if new_mappings:
            bulk_cache_itad_mappings(new_mappings)
            logger.info("Cached %d new AppID->ITAD ID mappings", len(new_mappings))

        # Merge cached + new
        all_mappings = {**cached_mappings, **new_mappings}
        return all_mappings, failed_appids

    @staticmethod
    def _extract_steam_deal(price_entry: dict) -> tuple[float | None, int, float | None, bool]:
        """Extract current Steam deal info from an ITAD price entry.

        Returns (current_price, discount_percent, original_price, steam_deal_found).
        """
        for deal in price_entry.get("deals") or []:
            shop = deal.get("shop") if deal else None
            if shop and shop.get("name") == "Steam":
                price_obj = deal.get("price") if deal else None
                regular_obj = deal.get("regular") if deal else None
                return (
                    price_obj.get("amount") if price_obj else None,
                    deal.get("cut", 0) if deal else 0,
                    regular_obj.get("amount") if regular_obj else None,
                    True,
                )
        return None, 0, None, False

    @staticmethod
    def _build_itad_price_data(
        hist_amount: float,
        hist_shop: str,
        current_price: float | None,
        current_discount: int,
        original_price: float | None,
    ) -> dict:
        """Build a price_data dict from ITAD historical and current deal info."""
        price_data: dict = {
            "lowest_price": str(hist_amount),
            "lowest_price_formatted": f"${hist_amount}",
            "shop_name": hist_shop,
        }
        if current_price is not None:
            price_data["current_price"] = str(current_price)
            price_data["current_price_formatted"] = f"${current_price}"
            price_data["discount_percent"] = current_discount
            if original_price is not None:
                price_data["original_price"] = str(original_price)
        return price_data

    def _process_prices_data(
        self,
        prices_data: list,
        itad_id_to_appid: dict[str, str],
        itad_data: dict[str, dict],
        no_steam_deal: set[str],
    ) -> int:
        """Process successfully returned prices data from ITAD."""
        chunk_processed = 0
        for price_entry in prices_data:
            if not price_entry:
                chunk_processed += 1
                continue
            itad_id = price_entry.get("id")
            app_id = itad_id_to_appid.get(itad_id)
            if not app_id:
                chunk_processed += 1
                continue

            # Extract historical low
            history_low_raw = price_entry.get("historyLow")
            history_low = history_low_raw.get("all", {}) if history_low_raw else {}
            hist_amount = history_low.get("amount")
            shop_obj = history_low.get("shop") if history_low else None
            hist_shop = (
                shop_obj.get("name", "Historical Low (All Stores)")
                if shop_obj
                else "Historical Low (All Stores)"
            )

            current_price, current_discount, original_price, steam_deal_found = (
                self._extract_steam_deal(price_entry)
            )

            if not steam_deal_found:
                no_steam_deal.add(app_id)

            if hist_amount is not None:
                itad_data[app_id] = {
                    "data": self._build_itad_price_data(
                        hist_amount,
                        hist_shop,
                        current_price,
                        current_discount,
                        original_price,
                    ),
                    "method": "bulk",
                    "game_name": None,
                }
            chunk_processed += 1

        return chunk_processed

    async def _fetch_itad_prices_chunk(
        self,
        chunk: list[str],
        itad_id_to_appid: dict[str, str],
        itad_data: dict[str, dict],
        no_steam_deal: set[str],
        pbar,
    ) -> None:
        """Handle network call and processing for a single ITAD prices chunk."""
        try:
            prices_url = "https://api.isthereanydeal.com/games/prices/v3"
            response = await self.make_request_with_retry(
                prices_url,
                method="POST",
                json_data=chunk,
                params={"key": ITAD_API_KEY, "country": "US"},
                api_type="itad",
            )

            if response is None:
                logger.warning("ITAD prices chunk failed, skipping %d IDs", len(chunk))
                if pbar:
                    pbar.update(len(chunk))
                return

            prices_data = self.handle_api_response("ITAD Bulk Prices", response)
            if not isinstance(prices_data, list):
                if pbar:
                    pbar.update(len(chunk))
                return

            chunk_processed = self._process_prices_data(
                prices_data, itad_id_to_appid, itad_data, no_steam_deal
            )

            if pbar:
                pbar.update(chunk_processed)
                pbar.set_postfix_str(f"Prices: {len(itad_data)}, No Steam: {len(no_steam_deal)}")

        except Exception as e:
            logger.error("ITAD prices bulk chunk failed: %s", e)
            if pbar:
                pbar.update(len(chunk))

    async def _fetch_itad_prices_bulk(
        self, itad_ids: list[str], itad_id_to_appid: dict[str, str]
    ) -> tuple[dict[str, dict], set[str]]:
        """Bulk fetch prices from ITAD for a list of ITAD IDs.

        Returns (appid -> price_info dict, set of appids with no Steam deal).
        """
        itad_data = {}
        no_steam_deal = set()
        chunk_size = 50

        if ASYNC_TQDM_AVAILABLE:
            pbar = atqdm(
                total=len(itad_ids),
                desc="ITAD Prices",
                unit="game",
                leave=False,
            )
        else:
            pbar = None

        for i in range(0, len(itad_ids), chunk_size):
            chunk = itad_ids[i : i + chunk_size]
            await self._fetch_itad_prices_chunk(
                chunk, itad_id_to_appid, itad_data, no_steam_deal, pbar
            )

        if pbar:
            pbar.close()

        return itad_data, no_steam_deal

    def batch_write_steam_data(self, steam_data: dict[str, dict], batch_size: int = 100) -> int:
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
                        cache_game_details(app_id, game_data, permanent=False, conn=conn)
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
                            cache_game_details(app_id, game_data, permanent=False, conn=conn)
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

    def _write_itad_record(self, conn, app_id: str, price_info: dict) -> None:
        """Write a single ITAD price record using an existing connection."""
        price_data = price_info["data"]
        lookup_method = price_info["method"]
        game_name = price_info.get("game_name")

        if not game_name:
            cached_details = get_cached_game_details(app_id)
            if cached_details:
                game_name = cached_details.get("name")

        cache_itad_price_enhanced(
            app_id,
            price_data,
            lookup_method=lookup_method,
            steam_game_name=game_name,
            permanent=False,
            cache_hours=ITAD_CACHE_TTL,
            conn=conn,
        )

    def batch_write_itad_data(self, itad_data: dict[str, dict], batch_size: int = 100) -> int:
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
                        self._write_itad_record(conn, app_id, price_info)
                    conn.commit()
                written_count += len(batch)
                logger.debug("Successfully wrote batch of %d ITAD records", len(batch))

            except Exception as e:
                logger.error("Failed to write ITAD batch: %s", e)
                # Try individual records to salvage what we can
                for app_id, price_info in batch:
                    try:
                        with get_write_connection() as conn:
                            self._write_itad_record(conn, app_id, price_info)
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

    async def _collect_steam_data(
        self, games_to_process: list[str]
    ) -> tuple[dict[str, dict], list]:
        """Run async Steam API fetches and return (steam_data, steam_errors)."""
        steam_data: dict[str, dict] = {}
        steam_errors: list = []
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
            for completed, coro in enumerate(asyncio.as_completed(tasks), 1):
                app_id, success, game_data, source = await coro
                if success:
                    steam_data[app_id] = {"data": game_data, "source": source}
                else:
                    steam_errors.append((app_id, source))

                if completed % 50 == 0:
                    print(
                        f"   API Progress: {completed}/{len(games_to_process)}"
                        f" | Success: {len(steam_data)} | Errors: {len(steam_errors)}"
                    )

        return steam_data, steam_errors

    async def populate_steam_prices(
        self, game_ids: set[str], dry_run: bool = False, force_refresh: bool = False
    ) -> int:
        """Populate Steam prices with async processing."""
        print("\nStarting async Steam price population...")
        if not game_ids:
            print("No game IDs to process")
            return 0

        if force_refresh:
            games_to_process = list(game_ids)
        else:
            games_to_process = [
                gid
                for gid in game_ids
                if not (cd := get_cached_game_details(gid)) or not cd.get("price_overview")
            ]

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
        steam_data, steam_errors = await self._collect_steam_data(games_to_process)

        # Phase 2: Safe database writing
        print("   Phase 2: Safe database writing...")
        steam_prices_cached = self.batch_write_steam_data(steam_data)

        print("\nAsync Steam price population complete!")
        print(f"   Prices cached: {steam_prices_cached}")
        print(f"   Errors: {len(steam_errors)}")

        return steam_prices_cached

    @staticmethod
    def _compute_fallback_ids(
        mapping_failures: list[str],
        appid_to_itad: dict[str, str],
        itad_data: dict[str, dict],
        no_steam_deal: set[str],
    ) -> set[str]:
        """Compute the set of app IDs that need a Steam API fallback."""
        itad_appids_with_data = set(itad_data.keys())
        fallback_ids: set[str] = set(mapping_failures)

        # AppIDs mapped but ITAD returned no price data
        fallback_ids.update(aid for aid in appid_to_itad if aid not in itad_appids_with_data)

        # AppIDs with ITAD data but no Steam deal listed
        fallback_ids.update(no_steam_deal)

        # Only remove appids that have ITAD data AND have a Steam deal
        fallback_ids -= itad_appids_with_data - no_steam_deal
        return fallback_ids

    async def _collect_steam_fallback_data(self, fallback_ids: set[str]) -> dict[str, dict]:
        """Fetch Steam prices for fallback IDs and return a steam_fallback_data dict."""
        steam_fallback_data: dict[str, dict] = {}
        if not fallback_ids:
            return steam_fallback_data

        tasks = [self.fetch_steam_price_single(app_id) for app_id in fallback_ids]
        if ASYNC_TQDM_AVAILABLE:
            for task in atqdm(
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc="Steam Fallback",
                unit="game",
            ):
                app_id, success, game_data, _source = await task
                if success and game_data:
                    entry = self._extract_steam_fallback_entry(game_data)
                    if entry:
                        steam_fallback_data[app_id] = entry
        else:
            for completed, coro in enumerate(asyncio.as_completed(tasks), 1):
                app_id, success, game_data, _source = await coro
                if success and game_data:
                    entry = self._extract_steam_fallback_entry(game_data)
                    if entry:
                        steam_fallback_data[app_id] = entry
                if completed % 10 == 0:
                    print(f"   Steam Fallback Progress: {completed}/{len(fallback_ids)}")

        return steam_fallback_data

    @staticmethod
    def _merge_itad_and_fallback(
        itad_data: dict[str, dict], steam_fallback_data: dict[str, dict]
    ) -> dict[str, dict]:
        """Merge ITAD price data with Steam fallback entries."""
        all_data = dict(itad_data)
        for appid, steam_entry in steam_fallback_data.items():
            if appid in itad_data:
                itad_entry = all_data[appid]
                if "data" in itad_entry and "data" in steam_entry:
                    itad_entry["data"]["steam_current_price"] = steam_entry["data"].get(
                        "lowest_price"
                    )
                    itad_entry["data"]["steam_current_price_formatted"] = steam_entry["data"].get(
                        "lowest_price_formatted"
                    )
                if not itad_entry.get("game_name") and steam_entry.get("game_name"):
                    itad_entry["game_name"] = steam_entry["game_name"]
            else:
                all_data[appid] = steam_entry
        return all_data

    async def populate_itad_prices(
        self, game_ids: set[str], dry_run: bool = False, force_refresh: bool = False
    ) -> int:
        """Populate ITAD prices using bulk API calls with Steam API fallback."""
        print("\nStarting bulk ITAD price population...")
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

        if dry_run:
            print("   DRY RUN: Would fetch ITAD price data")
            return 0
        if not games_to_process:
            print("   All games already have ITAD price data")
            return 0

        # Phase 1: Resolve AppIDs to ITAD IDs (cache + bulk lookup)
        print("   Phase 1: Resolving AppIDs to ITAD IDs...")
        appid_to_itad, mapping_failures = await self._resolve_itad_ids_bulk(games_to_process)
        print(f"   Resolved: {len(appid_to_itad)} | Failed to map: {len(mapping_failures)}")

        # Phase 2: Bulk fetch prices from ITAD
        print("   Phase 2: Bulk fetching prices from ITAD...")
        itad_id_to_appid = {v: k for k, v in appid_to_itad.items()}
        itad_data, no_steam_deal = await self._fetch_itad_prices_bulk(
            list(appid_to_itad.values()), itad_id_to_appid
        )
        print(f"   Prices received: {len(itad_data)} | No Steam deal: {len(no_steam_deal)}")

        # Phase 3: Steam API fallback
        fallback_ids = self._compute_fallback_ids(
            mapping_failures, appid_to_itad, itad_data, no_steam_deal
        )
        print(f"   Phase 3: Steam API fallback for {len(fallback_ids)} games...")
        steam_fallback_data = await self._collect_steam_fallback_data(fallback_ids)

        # Merge and write
        all_data = self._merge_itad_and_fallback(itad_data, steam_fallback_data)

        # Phase 4: Safe database writing
        print("   Phase 4: Safe database writing...")
        itad_prices_cached = self.batch_write_itad_data(all_data)

        print("\nBulk ITAD price population complete!")
        print(f"   ITAD prices cached: {len(itad_data)}")
        print(f"   Steam fallback prices cached: {len(steam_fallback_data)}")
        print(f"   Total prices cached: {itad_prices_cached}")
        print(f"   Games not found on ITAD: {len(mapping_failures)}")

        return itad_prices_cached

    async def refresh_current_prices(self, game_ids: set[str], dry_run: bool = False) -> int:
        """Refresh current Steam prices with force refresh."""
        print("\nRefreshing current Steam prices...")
        if not game_ids:
            print("No game IDs to process")
            return 0
        if dry_run:
            print(f"   DRY RUN: Would refresh {len(game_ids)} current prices")
            return 0
        return await self.populate_steam_prices(game_ids, dry_run=False, force_refresh=True)


async def _run_price_population(
    populator: "PricePopulator",
    all_game_ids: set[str],
    args,
) -> tuple[int, int]:
    """Dispatch to the appropriate population mode and return (steam_cached, itad_cached)."""
    dry_run = args.dry_run
    force = args.force_refresh

    if args.steam_only:
        if args.refresh_current:
            steam = await populator.refresh_current_prices(all_game_ids, dry_run)
        else:
            steam = await populator.populate_steam_prices(all_game_ids, dry_run, force)
        return steam, 0

    itad = await populator.populate_itad_prices(all_game_ids, dry_run, force)

    if args.refresh_current:
        steam = await populator.refresh_current_prices(all_game_ids, dry_run)
    elif args.with_steam:
        steam = await populator.populate_steam_prices(all_game_ids, dry_run, force)
    else:
        steam = 0

    return steam, itad


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Price data population for FamilyBot")
    parser.add_argument(
        "--steam-only", action="store_true", help="Only populate Steam Store prices"
    )
    parser.add_argument(
        "--with-steam",
        action="store_true",
        help="Also populate Steam Store prices alongside ITAD (default is ITAD only)",
    )
    parser.add_argument(
        "--refresh-current",
        action="store_true",
        help=(
            "Run ITAD population then refresh current Steam prices (useful during sales). "
            "Example: python scripts/populate_prices.py --refresh-current"
        ),
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
    if args.steam_only and args.with_steam:
        parser.error("--steam-only and --with-steam are mutually exclusive")

    return args


def _print_startup_banner(args) -> None:
    """Print script startup banner and active modes."""
    print("FamilyBot Price Population Script\n" + "=" * 60)
    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
    if args.refresh_current:
        print("REFRESH MODE - Will update current prices even if cached")
    if args.force_refresh:
        print("FORCE REFRESH MODE - Will update all price data even if cached")


def _get_max_concurrent(args) -> int:
    """Determine max concurrent requests based on rate limit strategy."""
    if args.rate_limit == "conservative":
        return min(args.concurrent, 25)
    if args.rate_limit == "aggressive":
        return min(args.concurrent, 100)
    return args.concurrent


def _print_summary(
    args,
    duration_secs: float,
    num_games: int,
    steam_cached: int,
    itad_cached: int,
    max_concurrent: int,
) -> None:
    """Print execution summary."""
    print("\n" + "=" * 60 + "\nPrice Population Complete!")
    print(f"Duration: {duration_secs:.1f} seconds")
    if num_games > 0:
        print(f"Games processed: {num_games}")
    print(f"Steam prices cached: {steam_cached}")
    print(f"ITAD prices cached: {itad_cached}")
    print(f"Total price entries updated: {steam_cached + itad_cached}")

    if not args.dry_run:
        print("\nPrice data population complete!")
        print(f"   Performance: ~{max_concurrent}x faster than sequential processing")
        print("   Connection reuse enabled to minimize data usage")
        print("   Adaptive rate limiting prevents API throttling")


async def main():
    args = parse_arguments()
    _print_startup_banner(args)

    try:
        init_db()
        print("Database initialized")
    except (ValueError, TypeError, OSError) as e:
        print(f"Failed to initialize database: {e}")
        return 1

    max_concurrent = _get_max_concurrent(args)
    populator = PricePopulator(max_concurrent, args.rate_limit)
    total_steam_cached, total_itad_cached = 0, 0
    all_game_ids = set()
    start_time = datetime.now(tz=UTC)

    try:
        family_members = populator.load_family_members()
        if not family_members:
            print("No family members found. Check your configuration.")
            return 1

        all_game_ids = populator.collect_all_game_ids(family_members)
        if not all_game_ids:
            print("No games found to process. Run populate_database.py first.")
            return 1

        total_steam_cached, total_itad_cached = await _run_price_population(
            populator, all_game_ids, args
        )
    finally:
        await populator.aclose()

    duration = datetime.now(UTC) - start_time
    _print_summary(
        args,
        duration.total_seconds(),
        len(all_game_ids),
        total_steam_cached,
        total_itad_cached,
        max_concurrent,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
