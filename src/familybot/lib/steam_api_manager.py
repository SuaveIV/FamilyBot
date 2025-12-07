import asyncio
import time
import requests
import random
from steam.webapi import WebAPI

from familybot.config import STEAMWORKS_API_KEY
from familybot.lib.logging_config import get_logger

logger = get_logger(__name__)

class SteamAPIManager:
    # --- RATE LIMITING CONSTANTS ---
    MAX_WISHLIST_GAMES_TO_PROCESS = 100  # Limit appdetails calls to 100 games per run
    STEAM_API_RATE_LIMIT = 3.0  # Minimum seconds between Steam API calls (e.g., GetOwnedGames, GetFamilySharedApps)
    STEAM_STORE_API_RATE_LIMIT = 2.0  # Minimum seconds between Steam Store API calls (e.g., appdetails)
    FULL_SCAN_RATE_LIMIT = 5.0  # Minimum seconds between Steam Store API calls for full wishlist scans

    def __init__(self):
        self.steam_api = (
            WebAPI(key=STEAMWORKS_API_KEY)
            if STEAMWORKS_API_KEY
            and STEAMWORKS_API_KEY != "YOUR_STEAMWORKS_API_KEY_HERE"
            else None
        )
        self._last_steam_api_call = 0.0
        self._last_steam_store_api_call = 0.0
        self.max_retries = 3
        self.base_backoff = 1.0

        if not self.steam_api:
            logger.warning(
                "SteamWorks API key not configured. Some features will be disabled."
            )

    async def rate_limit_steam_api(self) -> None:
        """Enforce rate limiting for Steam API calls (non-storefront)."""
        current_time = time.time()
        time_since_last_call = current_time - self._last_steam_api_call

        if time_since_last_call < self.STEAM_API_RATE_LIMIT:
            sleep_time = self.STEAM_API_RATE_LIMIT - time_since_last_call
            logger.debug(
                f"Rate limiting Steam API call, sleeping for {sleep_time:.2f} seconds"
            )
            await asyncio.sleep(sleep_time)

        self._last_steam_api_call = time.time()

    async def rate_limit_steam_store_api(self) -> None:
        """Enforce rate limiting for Steam Store API calls (e.g., appdetails)."""
        current_time = time.time()
        time_since_last_call = current_time - self._last_steam_store_api_call

        if time_since_last_call < self.STEAM_STORE_API_RATE_LIMIT:
            sleep_time = self.STEAM_STORE_API_RATE_LIMIT - time_since_last_call
            logger.debug(
                f"Rate limiting Steam Store API call, sleeping for {sleep_time:.2f} seconds"
            )
            await asyncio.sleep(sleep_time)

        self._last_steam_store_api_call = time.time()

    async def rate_limit_full_scan(self) -> None:
        """Enforce slower rate limiting for full wishlist scans to avoid hitting API limits."""
        current_time = time.time()
        time_since_last_call = current_time - self._last_steam_store_api_call

        if time_since_last_call < self.FULL_SCAN_RATE_LIMIT:
            sleep_time = self.FULL_SCAN_RATE_LIMIT - time_since_last_call
            logger.debug(
                f"Rate limiting full scan API call, sleeping for {sleep_time:.2f} seconds"
            )
            await asyncio.sleep(sleep_time)

        self._last_steam_store_api_call = time.time()

    async def make_request_with_retry(
        self, url: str, timeout: int = 10
    ) -> requests.Response | None:
        """Make HTTP request with retry logic for 429 errors and better error handling."""
        for attempt in range(self.max_retries + 1):
            try:
                # Add jitter to prevent synchronized requests
                if attempt > 0:
                    jitter = random.uniform(0, 0.1)
                    await asyncio.sleep(jitter)

                # Make the request
                response = requests.get(url, timeout=timeout)

                # Check for rate limiting
                if response.status_code == 429:
                    if attempt < self.max_retries:
                        backoff_time = self.base_backoff * (
                            2**attempt
                        ) + random.uniform(0, 1)
                        logger.warning(
                            f"Rate limited (429), retrying in {backoff_time:.1f}s (attempt {attempt + 1}/{self.max_retries + 1}) for {url}"
                        )
                        await asyncio.sleep(backoff_time)
                        continue
                    logger.error(f"Max retries exceeded for {url}")
                    return None

                return response

            except (requests.RequestException, requests.Timeout) as e:
                if attempt < self.max_retries:
                    backoff_time = self.base_backoff * (2**attempt)
                    logger.warning(
                        f"Request failed: {e}, retrying in {backoff_time:.1f}s"
                    )
                    await asyncio.sleep(backoff_time)
                    continue
                logger.error(f"Request failed after {self.max_retries} retries: {e}")
                return None

        return None
