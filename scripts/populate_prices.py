import sys
import os
import time
import asyncio
import argparse
import httpx 
import json
import random
from datetime import datetime
from typing import Dict, List, Set, Optional

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    print("⚠️  tqdm not available. Install with: uv pip install tqdm")
    print("   Falling back to basic progress indicators...")
    TQDM_AVAILABLE = False

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from familybot.config import STEAMWORKS_API_KEY, FAMILY_USER_DICT, ITAD_API_KEY
from familybot.lib.database import (
    init_db, get_db_connection, get_cached_game_details, cache_game_details,
    get_cached_wishlist, cache_wishlist, get_cached_itad_price, cache_itad_price
)
from familybot.lib.family_utils import find_in_2d_list
from familybot.lib.logging_config import setup_script_logging

# Setup enhanced logging for this script
logger = setup_script_logging("populate_prices", "INFO")

# Suppress verbose HTTP request logging from httpx
import logging
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
        self.capacity = capacity if capacity is not None else max(1, int(rate * 10))
        self.tokens = self.capacity
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


class PricePopulator:
    """Handles comprehensive price data population with concurrent async processing and rate limiting."""
    
    def __init__(self, rate_limit_mode: str = "normal"):
        """Initialize the populator with specified rate limiting and concurrency."""
        self.rate_limits = {
            "fast": {"steam_api": 1.2, "store_api": 1.5, "itad_api": 1.0, "concurrency": 6},
            "normal": {"steam_api": 1.5, "store_api": 2.0, "itad_api": 1.2, "concurrency": 4},
            "slow": {"steam_api": 2.0, "store_api": 2.5, "itad_api": 1.5, "concurrency": 3},
            "conservative": {"steam_api": 3.0, "store_api": 4.0, "itad_api": 2.0, "concurrency": 2}
        }
        
        self.current_limits = self.rate_limits.get(rate_limit_mode, self.rate_limits["normal"])
        
        # Create token bucket rate limiters
        self.steam_bucket = TokenBucket(1.0 / self.current_limits["steam_api"])
        self.store_bucket = TokenBucket(1.0 / self.current_limits["store_api"])
        self.itad_bucket = TokenBucket(1.0 / self.current_limits["itad_api"])
        
        # Create semaphores for controlling concurrency
        self.steam_semaphore = asyncio.Semaphore(self.current_limits["concurrency"])
        self.itad_semaphore = asyncio.Semaphore(self.current_limits["concurrency"])
        
        # Add retry configuration for 429 errors
        self.max_retries = 3
        self.base_backoff = 1.0
        
        self.client = httpx.AsyncClient(timeout=15.0)

        print(f"🔧 Rate limiting mode: {rate_limit_mode}")
        print(f"   Steam API: {self.current_limits['steam_api']}s (token bucket)")
        print(f"   Store API: {self.current_limits['store_api']}s (token bucket)")
        print(f"   ITAD API: {self.current_limits['itad_api']}s (token bucket)")
        print(f"   Concurrency: {self.current_limits['concurrency']} simultaneous requests")
        print(f"   Retry policy: {self.max_retries} retries with exponential backoff")
    
    async def close(self):
        """Closes the httpx client session."""
        await self.client.aclose()

    async def make_request_with_retry(self, url: str, method: str = "GET", json_data: Optional[dict | list] = None, api_type: str = "store") -> Optional[httpx.Response]:
        """Make HTTP request with retry logic for 429 errors."""
        bucket = self.store_bucket if api_type == "store" else self.itad_bucket
        
        for attempt in range(self.max_retries + 1):
            try:
                # Acquire token from bucket
                await bucket.acquire()
                
                # Add jitter to prevent synchronized requests
                jitter = random.uniform(0, 0.1)
                await asyncio.sleep(jitter)
                
                # Make the request
                if method == "GET":
                    response = await self.client.get(url)
                elif method == "POST":
                    response = await self.client.post(url, json=json_data)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Check for rate limiting
                if response.status_code == 429:
                    if attempt < self.max_retries:
                        backoff_time = self.base_backoff * (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(f"Rate limited (429), retrying in {backoff_time:.1f}s (attempt {attempt + 1}/{self.max_retries + 1})")
                        await asyncio.sleep(backoff_time)
                        continue
                    else:
                        logger.error(f"Max retries exceeded for {url}")
                        return None
                
                return response
                
            except Exception as e:
                if attempt < self.max_retries:
                    backoff_time = self.base_backoff * (2 ** attempt)
                    logger.warning(f"Request failed: {e}, retrying in {backoff_time:.1f}s")
                    await asyncio.sleep(backoff_time)
                    continue
                else:
                    logger.error(f"Request failed after {self.max_retries} retries: {e}")
                    return None
        
        return None
    
    def handle_api_response(self, api_name: str, response: httpx.Response) -> Optional[dict]:
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
                        (steam_id, name, None)
                    )
                conn.commit()
                print(f"✅ Migrated {len(FAMILY_USER_DICT)} family members")
            
            cursor.execute("SELECT steam_id, friendly_name FROM family_members")
            for row in cursor.fetchall():
                members[row["steam_id"]] = row["friendly_name"]
            conn.close()
            print(f"👥 Loaded {len(members)} family members")
        except Exception as e:
            print(f"❌ Error loading family members: {e}")
            return {}
        return members
    
    def collect_all_game_ids(self, family_members: Dict[str, str]) -> Set[str]:
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
    
    async def fetch_steam_price(self, app_id: str) -> tuple[str, bool]:
        """Fetch price for a single Steam game with semaphore control."""
        async with self.steam_semaphore:
            try:
                game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                response = await self.make_request_with_retry(game_url, method="GET", api_type="store")
                
                if response is None:
                    return app_id, False
                
                game_info = self.handle_api_response(f"Steam Store ({app_id})", response)
                
                if game_info and game_info.get(str(app_id), {}).get("data"):
                    cache_game_details(app_id, game_info[str(app_id)]["data"], permanent=True)
                    return app_id, True
                else:
                    return app_id, False
            except Exception as e:
                logger.error(f"Error fetching Steam price for {app_id}: {e}")
                return app_id, False

    async def populate_steam_prices(self, game_ids: Set[str], dry_run: bool = False, force_refresh: bool = False) -> int:
        print(f"\n💰 Starting Steam price population...")
        if not game_ids:
            print("❌ No game IDs to process")
            return 0
        
        games_to_process = []
        for gid in game_ids:
            if force_refresh:
                games_to_process.append(gid)
            else:
                cached_details = get_cached_game_details(gid)
                if not cached_details or not cached_details.get('price_data'):
                    games_to_process.append(gid)
        games_skipped = len(game_ids) - len(games_to_process)
        
        print(f"   🎯 Games to process: {len(games_to_process)}")
        print(f"   ⏭️   Games skipped (already have price data): {games_skipped}")
        print(f"   🚀 Processing with {self.current_limits['concurrency']} concurrent requests")
        
        if dry_run:
            print("   🔍 DRY RUN: Would fetch Steam price data")
            return 0
        
        if not games_to_process:
            print("   ✅ All games already have Steam price data")
            return 0
        
        # Process games concurrently with real-time progress updates
        steam_prices_cached, steam_errors = 0, 0
        
        if TQDM_AVAILABLE:
            progress_bar = tqdm(total=len(games_to_process), desc="💰 Steam Prices", unit="game")
        
        # Create a semaphore to control concurrent updates to progress
        progress_lock = asyncio.Lock()
        
        async def fetch_with_progress(app_id: str) -> tuple[str, bool]:
            """Fetch price and update progress in real-time."""
            nonlocal steam_prices_cached, steam_errors
            
            result = await self.fetch_steam_price(app_id)
            
            # Update progress atomically
            async with progress_lock:
                app_id, success = result
                if success:
                    steam_prices_cached += 1
                else:
                    steam_errors += 1
                
                if TQDM_AVAILABLE:
                    progress_bar.update(1)
                    progress_bar.set_postfix_str(f"Cached: {steam_prices_cached}, Errors: {steam_errors}")  # type: ignore
                
                return result
        
        # Process in smaller batches for more responsive progress updates
        batch_size = self.current_limits['concurrency'] * 3
        for i in range(0, len(games_to_process), batch_size):
            batch = games_to_process[i:i + batch_size]
            
            # Create tasks for concurrent processing with progress updates
            tasks = [fetch_with_progress(app_id) for app_id in batch]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Progress update for non-tqdm users
            if not TQDM_AVAILABLE:
                processed = min(i + batch_size, len(games_to_process))
                print(f"   📈 Progress: {processed}/{len(games_to_process)} | Cached: {steam_prices_cached} | Errors: {steam_errors}")
        
        if TQDM_AVAILABLE:
            progress_bar.close()
        
        print(f"\n💰 Steam price population complete!\n   ✅ Prices cached: {steam_prices_cached}\n   ❌ Errors: {steam_errors}")
        return steam_prices_cached
    
    async def fetch_itad_price(self, app_id: str) -> tuple[str, str]:
        """Fetch ITAD price for a single game with semaphore control. Returns (app_id, status)."""
        async with self.itad_semaphore:
            try:
                lookup_url = f"https://api.isthereanydeal.com/games/lookup/v1?key={ITAD_API_KEY}&appid={app_id}"
                lookup_response = await self.make_request_with_retry(lookup_url, method="GET", api_type="itad")
                
                if lookup_response is None:
                    return app_id, "error"
                
                lookup_data = self.handle_api_response(f"ITAD Lookup ({app_id})", lookup_response)
                
                game_id = lookup_data.get("game", {}).get("id") if lookup_data else None
                if not game_id:
                    return app_id, "not_found" if lookup_data else "error"

                storelow_url = f"https://api.isthereanydeal.com/games/storelow/v2?key={ITAD_API_KEY}&country=US&shops=61"
                storelow_response = await self.make_request_with_retry(storelow_url, method="POST", json_data=[game_id], api_type="itad")
                
                if storelow_response is None:
                    return app_id, "error"
                
                storelow_data = self.handle_api_response(f"ITAD StoreLow ({app_id})", storelow_response)

                if storelow_data and storelow_data[0].get("lows"):
                    low = storelow_data[0]["lows"][0]
                    cache_itad_price(app_id, {
                        'lowest_price': str(low["price"]["amount"]), 
                        'lowest_price_formatted': f"${low['price']['amount']}", 
                        'shop_name': low.get("shop", {}).get("name", "Unknown Store")
                    }, permanent=True)
                    return app_id, "cached"
                else:
                    return app_id, "not_found"
            except Exception as e:
                logger.error(f"Error fetching ITAD price for {app_id}: {e}")
                return app_id, "error"

    async def populate_itad_prices(self, game_ids: Set[str], dry_run: bool = False, force_refresh: bool = False) -> int:
        print(f"\n📈 Starting ITAD price population...")
        if not ITAD_API_KEY or ITAD_API_KEY == "YOUR_ITAD_API_KEY_HERE":
            print("❌ ITAD API key not configured. Skipping ITAD price population.")
            return 0
        if not game_ids:
            print("❌ No game IDs to process")
            return 0
        
        games_to_process = [gid for gid in game_ids if force_refresh or not get_cached_itad_price(gid)]
        games_skipped = len(game_ids) - len(games_to_process)
        
        print(f"   🎯 Games to process: {len(games_to_process)}")
        print(f"   ⏭️   Games skipped (already have ITAD data): {games_skipped}")
        print(f"   🚀 Processing with {self.current_limits['concurrency']} concurrent requests")
        
        if dry_run:
            print("   🔍 DRY RUN: Would fetch ITAD price data")
            return 0
        if not games_to_process:
            print("   ✅ All games already have ITAD price data")
            return 0
        
        # Process games concurrently with real-time progress updates
        itad_prices_cached, itad_errors, itad_not_found = 0, 0, 0
        
        if TQDM_AVAILABLE:
            progress_bar = tqdm(total=len(games_to_process), desc="📈 ITAD Prices", unit="game")
        
        # Create a semaphore to control concurrent updates to progress
        progress_lock = asyncio.Lock()
        
        async def fetch_itad_with_progress(app_id: str) -> tuple[str, str]:
            """Fetch ITAD price and update progress in real-time."""
            nonlocal itad_prices_cached, itad_errors, itad_not_found
            
            result = await self.fetch_itad_price(app_id)
            
            # Update progress atomically
            async with progress_lock:
                app_id, status = result
                if status == "cached":
                    itad_prices_cached += 1
                elif status == "not_found":
                    itad_not_found += 1
                elif status == "error":
                    itad_errors += 1
                
                if TQDM_AVAILABLE:
                    progress_bar.update(1)
                    progress_bar.set_postfix_str(f"Cached: {itad_prices_cached}, Not Found: {itad_not_found}, Errors: {itad_errors}")  # type: ignore
                
                return result
        
        # Process in smaller batches for ITAD (more conservative) with real-time updates
        batch_size = self.current_limits['concurrency'] * 2
        for i in range(0, len(games_to_process), batch_size):
            batch = games_to_process[i:i + batch_size]
            
            # Create tasks for concurrent processing with progress updates
            tasks = [fetch_itad_with_progress(app_id) for app_id in batch]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Progress update for non-tqdm users
            if not TQDM_AVAILABLE:
                processed = min(i + batch_size, len(games_to_process))
                print(f"   📈 Progress: {processed}/{len(games_to_process)} | Cached: {itad_prices_cached} | Not Found: {itad_not_found} | Errors: {itad_errors}")
        
        if TQDM_AVAILABLE:
            progress_bar.close()
        
        print(f"\n📈 ITAD price population complete!\n   ✅ Prices cached: {itad_prices_cached}\n   ❓ Games not found on ITAD: {itad_not_found}\n   ❌ Errors: {itad_errors}")
        return itad_prices_cached
    
    async def refresh_current_prices(self, game_ids: Set[str], dry_run: bool = False) -> int:
        print(f"\n🔄 Refreshing current Steam prices...")
        if not game_ids:
            print("❌ No game IDs to process")
            return 0
        if dry_run:
            print(f"   🔍 DRY RUN: Would refresh {len(game_ids)} current prices")
            return 0
        return await self.populate_steam_prices(game_ids, dry_run=False, force_refresh=True)

async def main():
    parser = argparse.ArgumentParser(description="Populate comprehensive price data for FamilyBot")
    parser.add_argument("--steam-only", action="store_true", help="Only populate Steam Store prices")
    parser.add_argument("--itad-only", action="store_true", help="Only populate ITAD historical prices")
    parser.add_argument("--refresh-current", action="store_true", help="Force refresh current Steam prices (useful during sales)")
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh all price data, even if cached")
    parser.add_argument("--fast", action="store_true", help="Use faster rate limiting")
    parser.add_argument("--slow", action="store_true", help="Use slower rate limiting")
    parser.add_argument("--conservative", action="store_true", help="Use very conservative rate limiting")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()

    rate_mode = "fast" if args.fast else "slow" if args.slow else "conservative" if args.conservative else "normal"
    
    print("💰 FamilyBot Price Population Script\n" + "=" * 50)
    if args.dry_run: print("🔍 DRY RUN MODE - No changes will be made")
    if args.refresh_current: print("🔄 REFRESH MODE - Will update current prices even if cached")
    if args.force_refresh: print("🔄 FORCE REFRESH MODE - Will update all price data even if cached")
    
    try:
        init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        return 1
    
    populator = PricePopulator(rate_mode)
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
            total_steam_cached = await populator.refresh_current_prices(all_game_ids, args.dry_run) if args.refresh_current else await populator.populate_steam_prices(all_game_ids, args.dry_run, args.force_refresh)
        
        if not args.steam_only:
            total_itad_cached = await populator.populate_itad_prices(all_game_ids, args.dry_run, args.force_refresh)
    finally:
        await populator.close()

    duration = datetime.now() - start_time
    print("\n" + "=" * 50 + "\n🎉 Price Population Complete!")
    print(f"⏱️   Duration: {duration.total_seconds():.1f} seconds")
    if all_game_ids: print(f"🎮 Games processed: {len(all_game_ids)}")
    print(f"💰 Steam prices cached: {total_steam_cached}")
    print(f"📈 ITAD prices cached: {total_itad_cached}")
    print(f"💾 Total price entries updated: {total_steam_cached + total_itad_cached}")
    
    if not args.dry_run:
        print("\n🚀 Price data population complete!\n   All deal commands will now run at maximum speed!\n   Perfect for Steam Summer/Winter Sales! 🎊")
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
