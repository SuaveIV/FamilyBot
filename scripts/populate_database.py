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
    from tqdm.asyncio import tqdm as atqdm
    TQDM_AVAILABLE = True
except ImportError:
    print("⚠️  tqdm not available. Install with: uv pip install tqdm")
    print("   Falling back to basic progress indicators...")
    TQDM_AVAILABLE = False

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from familybot.config import STEAMWORKS_API_KEY, FAMILY_USER_DICT
from familybot.lib.database import (
    init_db, get_db_connection, get_cached_game_details, cache_game_details,
    get_cached_wishlist, cache_wishlist, get_cached_family_library, cache_family_library
)
from familybot.lib.family_utils import get_family_game_list_url, find_in_2d_list
from familybot.lib.logging_config import setup_script_logging, log_private_profile_detection, log_api_error, log_rate_limit, log_performance_metric

# Setup enhanced logging for this script
logger = setup_script_logging("populate_database", "INFO")

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


class DatabasePopulator:
    """Handles database population with token bucket rate limiting and async processing."""
    
    def __init__(self, rate_limit_mode: str = "normal"):
        """Initialize the populator with specified rate limiting."""
        self.rate_limits = {
            "fast": {"steam_api": 1.0, "store_api": 1.2},
            "normal": {"steam_api": 1.2, "store_api": 1.5},
            "slow": {"steam_api": 1.8, "store_api": 2.2}
        }
        
        self.current_limits = self.rate_limits.get(rate_limit_mode, self.rate_limits["normal"])
        
        # Create token bucket rate limiters
        self.steam_bucket = TokenBucket(1.0 / self.current_limits["steam_api"])
        self.store_bucket = TokenBucket(1.0 / self.current_limits["store_api"])
        
        # Add retry configuration for 429 errors
        self.max_retries = 3
        self.base_backoff = 1.0
        
        self.client = httpx.AsyncClient(timeout=15.0)
        
        print(f"🔧 Rate limiting mode: {rate_limit_mode}")
        print(f"   Steam API: {self.current_limits['steam_api']}s (token bucket)")
        print(f"   Store API: {self.current_limits['store_api']}s (token bucket)")
        print(f"   Retry policy: {self.max_retries} retries with exponential backoff")
    
    async def close(self):
        """Closes the httpx client session."""
        await self.client.aclose()

    async def make_request_with_retry(self, url: str, api_type: str = "steam") -> Optional[httpx.Response]:
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
                print("📥 Migrating family members from config to database...")
                for steam_id, name in FAMILY_USER_DICT.items():
                    cursor.execute(
                        "INSERT OR IGNORE INTO family_members (steam_id, friendly_name, discord_id) VALUES (?, ?, ?)",
                        (steam_id, name, None)
                    )
                conn.commit()
                print(f"✅ Migrated {len(FAMILY_USER_DICT)} family members")
            
            # Load family members
            cursor.execute("SELECT steam_id, friendly_name FROM family_members")
            for row in cursor.fetchall():
                members[row["steam_id"]] = row["friendly_name"]
            
            conn.close()
            print(f"👥 Loaded {len(members)} family members")
            
        except Exception as e:
            print(f"❌ Error loading family members: {e}")
            return {}
        
        return members
    
    async def populate_family_libraries(self, family_members: Dict[str, str], dry_run: bool = False) -> int:
        """Populate database with all family member game libraries."""
        print("\n🎮 Starting family library population...")
        
        if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
            print("❌ Steam API key not configured. Cannot fetch family libraries.")
            return 0
        
        total_cached = 0
        total_processed = 0
        
        if TQDM_AVAILABLE: # Use tqdm if available
            member_iterator_tqdm = tqdm(family_members.items(), desc="👥 Family Members", unit="member", leave=True)
            for steam_id, name in member_iterator_tqdm:
                member_iterator_tqdm.set_postfix_str(f"Processing {name}")
                
                try:
                    owned_games_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAMWORKS_API_KEY}&steamid={steam_id}&include_appinfo=1&include_played_free_games=1"
                    
                    if dry_run:
                        continue
                    
                    response = await self.make_request_with_retry(owned_games_url, api_type="steam")
                    if response is None:
                        continue
                    
                    games_data = self.handle_api_response(f"GetOwnedGames ({name})", response)
                    
                    if not games_data:
                        continue
                    
                    games = games_data.get("response", {}).get("games", [])
                    if not games:
                        continue
                    
                    user_cached = 0
                    user_skipped = 0
                    
                    # Process games with real-time async updates
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
                        games_progress_iterator_tqdm = tqdm(total=len(games_to_fetch), desc=f"🎮 {name[:15]}", unit="game", leave=False)
                        
                        # Create progress tracking for real-time updates
                        progress_lock = asyncio.Lock()
                        
                        async def fetch_game_with_progress(app_id: str) -> bool:
                            """Fetch game details and update progress in real-time."""
                            nonlocal user_cached
                            
                            game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                            
                            try:
                                game_response = await self.make_request_with_retry(game_url, api_type="store")
                                if game_response is None:
                                    return False
                                
                                game_info = self.handle_api_response(f"AppDetails ({app_id})", game_response)
                                
                                if not game_info:
                                    return False
                                
                                game_data = game_info.get(str(app_id), {}).get("data")
                                if not game_data:
                                    return False
                                
                                cache_game_details(app_id, game_data, permanent=True)
                                
                                # Update progress atomically
                                async with progress_lock:
                                    nonlocal user_cached, total_cached
                                    user_cached += 1
                                    total_cached += 1
                                    games_progress_iterator_tqdm.update(1)
                                    games_progress_iterator_tqdm.set_postfix_str(f"Cached: {user_cached}, Skipped: {user_skipped}")
                                
                                return True
                                
                            except Exception as e:
                                async with progress_lock:
                                    games_progress_iterator_tqdm.update(1)
                                    games_progress_iterator_tqdm.set_postfix_str(f"Cached: {user_cached}, Skipped: {user_skipped}")
                                return False
                        
                        # Process games in small batches for responsive updates
                        batch_size = 5  # Conservative batch size for database population
                        for i in range(0, len(games_to_fetch), batch_size):
                            batch = games_to_fetch[i:i + batch_size]
                            tasks = [fetch_game_with_progress(app_id) for app_id in batch]
                            await asyncio.gather(*tasks, return_exceptions=True)
                        
                        games_progress_iterator_tqdm.close()
                    else:
                        # No games to fetch, just show the skipped count
                        if TQDM_AVAILABLE:
                            games_progress_iterator_tqdm = tqdm(total=1, desc=f"🎮 {name[:15]}", unit="game", leave=False)
                            games_progress_iterator_tqdm.update(1)
                            games_progress_iterator_tqdm.set_postfix_str(f"Cached: {user_cached}, Skipped: {user_skipped}")
                            games_progress_iterator_tqdm.close()
                    
                except Exception as e:
                    continue
        else: # Fallback to basic print statements if tqdm is not available
            member_iterator_plain = family_members.items()
            for steam_id, name in member_iterator_plain:
                print(f"\n📊 Processing {name}...")
                
                try:
                    owned_games_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAMWORKS_API_KEY}&steamid={steam_id}&include_appinfo=1&include_played_free_games=1"
                    
                    if dry_run:
                        print(f"   🔍 Would fetch owned games for {name}")
                        continue
                    
                    response = await self.make_request_with_retry(owned_games_url, api_type="steam")
                    if response is None:
                        print(f"   ❌ Failed to get games for {name}")
                        continue
                    
                    games_data = self.handle_api_response(f"GetOwnedGames ({name})", response)
                    
                    if not games_data:
                        print(f"   ❌ Failed to get games for {name}")
                        continue
                    
                    games = games_data.get("response", {}).get("games", [])
                    if not games:
                        print(f"   ⚠️  No games found for {name} (private profile?)")
                        continue
                    
                    print(f"   🎯 Found {len(games)} games")
                    
                    user_cached = 0
                    user_skipped = 0
                    
                    # Process games with async batching even without tqdm
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
                        print(f"   🎯 Processing {len(games_to_fetch)} new games...")
                        
                        async def fetch_game_simple(app_id: str) -> bool:
                            """Fetch game details for non-tqdm mode."""
                            nonlocal user_cached, total_cached
                            
                            game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                            
                            try:
                                game_response = await self.make_request_with_retry(game_url, api_type="store")
                                if game_response is None:
                                    return False
                                
                                game_info = self.handle_api_response(f"AppDetails ({app_id})", game_response)
                                
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
                                print(f"   ⚠️  Error processing game {app_id}: {e}")
                                return False
                        
                        # Process games in small batches with progress updates
                        batch_size = 5
                        for i in range(0, len(games_to_fetch), batch_size):
                            batch = games_to_fetch[i:i + batch_size]
                            tasks = [fetch_game_simple(app_id) for app_id in batch]
                            await asyncio.gather(*tasks, return_exceptions=True)
                            
                            # Progress update every batch
                            processed = min(i + batch_size, len(games_to_fetch))
                            print(f"   📈 Progress: {processed}/{len(games_to_fetch)} | Cached: {user_cached}")
                    
                    if not TQDM_AVAILABLE:
                        print(f"   ✅ {name} complete: {user_cached} cached, {user_skipped} skipped")
                        
                except Exception as e:
                    if not TQDM_AVAILABLE:
                        print(f"   ❌ Error processing {name}: {e}")
                    continue
        
        print(f"\n🎮 Family library population complete!")
        print(f"   📊 Total games processed: {total_processed}")
        print(f"   💾 New games cached: {total_cached}")
        
        return total_cached
    
    async def populate_wishlists(self, family_members: Dict[str, str], dry_run: bool = False) -> int:
        """Populate database with family member wishlists."""
        print("\n🎯 Starting wishlist population...")
        
        if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
            print("❌ Steam API key not configured. Cannot fetch wishlists.")
            return 0
        
        global_wishlist = []
        total_cached = 0
        
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
                wishlist_url = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?key={STEAMWORKS_API_KEY}&steamid={steam_id}"
                
                response = await self.make_request_with_retry(wishlist_url, api_type="steam")
                if response is None:
                    print(f"   ❌ Failed to get wishlist for {name}")
                    continue
                
                if response.text == '{"success":2}':
                    print(f"   ⚠️  {name}'s wishlist is private or empty")
                    continue
                
                wishlist_data = self.handle_api_response(f"GetWishlist ({name})", response)
                if not wishlist_data:
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
                cache_wishlist(steam_id, user_wishlist_appids, cache_hours=24)
                print(f"   ✅ {name}'s wishlist cached")
                
            except Exception as e:
                print(f"   ❌ Error processing {name}'s wishlist: {e}")
                continue
        
        # Process ALL wishlist games (not just common ones)
        all_unique_games = list(set([item[0] for item in global_wishlist]))
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
        
        if TQDM_AVAILABLE:
            games_iterator = tqdm(games_to_fetch, desc="🎯 Wishlist Games", unit="game", leave=True)
        else:
            games_iterator = games_to_fetch
        
        for i, app_id in enumerate(games_iterator):
            try:
                game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                
                response = await self.make_request_with_retry(game_url, api_type="store")
                if response is None:
                    continue
                
                game_info = self.handle_api_response(f"AppDetails ({app_id})", response)
                
                if not game_info:
                    continue
                
                game_data = game_info.get(str(app_id), {}).get("data")
                if not game_data:
                    continue
                
                # Cache the game details
                cache_game_details(app_id, game_data, permanent=True)
                total_cached += 1
                
                # Progress update for non-tqdm mode
                if not TQDM_AVAILABLE and (i + 1) % 10 == 0:
                    print(f"   📈 Progress: {i + 1}/{len(games_to_fetch)} games processed")
            
            except Exception as e:
                if not TQDM_AVAILABLE:
                    print(f"   ⚠️  Error processing game {app_id}: {e}")
                continue
        
        print(f"\n🎯 Wishlist population complete!")
        print(f"   💾 All wishlist games cached: {total_cached}")
        
        return total_cached


async def main():
    """Main function to run the database population."""
    parser = argparse.ArgumentParser(description="Populate FamilyBot database with comprehensive game data")
    parser.add_argument("--library-only", action="store_true", help="Only scan family member libraries")
    parser.add_argument("--wishlist-only", action="store_true", help="Only scan wishlists")
    parser.add_argument("--fast", action="store_true", help="Use faster rate limiting")
    parser.add_argument("--slow", action="store_true", help="Use slower rate limiting")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    
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
    except Exception as e:
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
            total_library_cached = await populator.populate_family_libraries(family_members, args.dry_run)
        
        # Populate wishlists
        if not args.library_only:
            total_wishlist_cached = await populator.populate_wishlists(family_members, args.dry_run)
        
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
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
