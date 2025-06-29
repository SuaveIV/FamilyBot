import sys
import os
import time
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
    get_cached_wishlist, cache_wishlist, get_cached_itad_price, cache_itad_price,
    cache_game_details_with_source, migrate_database_phase1, migrate_database_phase2,
    cache_itad_price_enhanced
)
from familybot.lib.family_utils import find_in_2d_list
from familybot.lib.logging_config import setup_script_logging
from steam.webapi import WebAPI

# Setup enhanced logging for this script
logger = setup_script_logging("populate_prices", "INFO")

# Suppress verbose HTTP request logging from httpx
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)


class PricePopulator:
    """Handles comprehensive price data population with synchronous processing and rate limiting."""
    
    def __init__(self, rate_limit_mode: str = "normal"):
        """Initialize the populator with specified rate limiting."""
        self.rate_limits = {
            "fast": {"steam_api": 1.2, "store_api": 1.5, "itad_api": 1.0},
            "normal": {"steam_api": 1.5, "store_api": 2.0, "itad_api": 1.2},
            "slow": {"steam_api": 2.0, "store_api": 2.5, "itad_api": 1.5},
            "conservative": {"steam_api": 3.0, "store_api": 4.0, "itad_api": 2.0}
        }
        
        self.current_limits = self.rate_limits.get(rate_limit_mode, self.rate_limits["normal"])
        
        # Add retry configuration for 429 errors
        self.max_retries = 3
        self.base_backoff = 1.0
        
        self.client = httpx.Client(timeout=15.0) # Changed to synchronous client

        print(f"🔧 Rate limiting mode: {rate_limit_mode}")
        print(f"   Steam API: {self.current_limits['steam_api']}s (delay per request)")
        print(f"   Store API: {self.current_limits['store_api']}s (delay per request)")
        print(f"   ITAD API: {self.current_limits['itad_api']}s (delay per request)")
        print(f"   Retry policy: {self.max_retries} retries with exponential backoff")
    
    def close(self): # Changed to synchronous close
        """Closes the httpx client session."""
        self.client.close()

    def make_request_with_retry(self, url: str, method: str = "GET", json_data: Optional[dict | list] = None, api_type: str = "store") -> Optional[httpx.Response]:
        """Make HTTP request with retry logic for 429 errors."""
        # Determine the appropriate sleep time based on API type
        sleep_time = self.current_limits["store_api"] if api_type == "store" else self.current_limits["itad_api"]
        
        for attempt in range(self.max_retries + 1):
            try:
                # Add jitter to prevent synchronized requests (even in sequential mode, good practice)
                jitter = random.uniform(0, 0.1)
                time.sleep(sleep_time + jitter) # Synchronous sleep
                
                # Make the request
                if method == "GET":
                    response = self.client.get(url)
                elif method == "POST":
                    response = self.client.post(url, json=json_data)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Check for rate limiting
                if response.status_code == 429:
                    if attempt < self.max_retries:
                        backoff_time = self.base_backoff * (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(f"Rate limited (429), retrying in {backoff_time:.1f}s (attempt {attempt + 1}/{self.max_retries + 1})")
                        time.sleep(backoff_time) # Synchronous sleep
                        continue
                    else:
                        logger.error(f"Max retries exceeded for {url}")
                        return None
                
                return response
                
            except Exception as e:
                if attempt < self.max_retries:
                    backoff_time = self.base_backoff * (2 ** attempt)
                    logger.warning(f"Request failed: {e}, retrying in {backoff_time:.1f}s")
                    time.sleep(backoff_time) # Synchronous sleep
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
    
    def fetch_steam_price(self, app_id: str) -> tuple[str, bool]:
        """Fetch price for a single Steam game."""
        try:
            game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
            response = self.make_request_with_retry(game_url, method="GET", api_type="store")
            
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

    def fetch_steam_price_enhanced(self, app_id: str) -> tuple[str, bool, str]:
        """Enhanced Steam price fetching with Steam library fallback."""
        
        # Strategy 1: Current Steam Store API (keep existing)
        success, source = self.fetch_steam_store_price(app_id) # Assuming this method exists or will be created
        if success:
            return app_id, True, 'store_api'
        
        # Strategy 2: Steam library WebAPI fallback
        success, source = self.fetch_steam_library_price(app_id)
        if success:
            return app_id, True, 'steam_library'
        
        # Strategy 3: Steam library package lookup
        success, source = self.fetch_steam_package_price(app_id)
        if success:
            return app_id, True, 'package_lookup'
        
        return app_id, False, 'failed'

    def fetch_steam_library_price(self, app_id: str) -> tuple[bool, str]:
        """Use Steam library WebAPI as fallback for price data."""
        try:
            if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
                logger.debug(f"Steam library fallback skipped for {app_id}: No API key")
                return False, 'no_api_key'
            
            api = WebAPI(key=STEAMWORKS_API_KEY)
            
            # Try to get app info using Steam library
            try:
                # Get app list and find our app
                app_list = api.call('ISteamApps.GetAppList')
                if app_list and 'applist' in app_list:
                    for app in app_list['applist']['apps']:
                        if str(app.get('appid')) == app_id:
                            # Found the app, create basic game data
                            game_data = {
                                'name': app['name'],
                                'type': 'game',
                                'is_free': False,  # Default assumption
                                'categories': [],
                                'price_overview': None  # No price data from app list
                            }
                            
                            # Cache the basic game details
                            cache_game_details_with_source(app_id, game_data, 'steam_library')
                            logger.debug(f"Steam library fallback successful for app {app_id}: {app['name']}")
                            return True, 'steam_library'
                            
            except Exception as e:
                logger.debug(f"Steam library WebAPI call failed for {app_id}: {e}")
                return False, 'webapi_error'
            
            logger.debug(f"Steam library fallback: app {app_id} not found in app list")
            return False, 'not_found'
            
        except ImportError:
            logger.debug("Steam library not available for fallback")
            return False, 'library_unavailable'
        except Exception as e:
            logger.debug(f"Steam library fallback failed for {app_id}: {e}")
            return False, 'library_error'

    def fetch_steam_package_price(self, app_id: str) -> tuple[bool, str]:
        """Use Steam library for package-based price lookup."""
        try:
            if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
                return False, 'no_api_key'
            
            api = WebAPI(key=STEAMWORKS_API_KEY)
            
            # Try to get package information for the app
            # This is more advanced and may require additional Steam library features
            # Implementation depends on available Steam library capabilities
            
            logger.debug(f"Steam package lookup attempted for app {app_id}")
            return False, 'not_implemented'  # Placeholder for future implementation
            
        except ImportError:
            return False, 'library_unavailable'
        except Exception as e:
            logger.debug(f"Steam package lookup failed for {app_id}: {e}")
            return False, 'package_error'

    def fetch_steam_store_price(self, app_id: str) -> tuple[bool, str]:
        """Wrapper for existing fetch_steam_price to match new return signature."""
        success = self.fetch_steam_price(app_id)[1]
        return success, 'store_api'

    def populate_steam_prices(self, game_ids: Set[str], dry_run: bool = False, force_refresh: bool = False) -> int:
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
        print(f"   🚀 Processing sequentially (1 request at a time)")
        
        if dry_run:
            print("   🔍 DRY RUN: Would fetch Steam price data")
            return 0
        
        if not games_to_process:
            print("   ✅ All games already have Steam price data")
            return 0
        
        steam_prices_cached, steam_errors = 0, 0
        
        if TQDM_AVAILABLE:
            progress_bar = tqdm(total=len(games_to_process), desc="💰 Steam Prices", unit="game")
        
        for app_id in games_to_process:
            app_id, success, source = self.fetch_steam_price_enhanced(app_id)
            if success:
                steam_prices_cached += 1
            else:
                steam_errors += 1
            
            if TQDM_AVAILABLE:
                progress_bar.update(1)
                progress_bar.set_postfix_str(f"Cached: {steam_prices_cached}, Errors: {steam_errors}, Source: {source}")  # type: ignore
            else:
                processed = steam_prices_cached + steam_errors
                print(f"   📈 Progress: {processed}/{len(games_to_process)} | Cached: {steam_prices_cached} | Errors: {steam_errors} | Source: {source}")
        
        if TQDM_AVAILABLE:
            progress_bar.close()
        
        print(f"\n💰 Steam price population complete!\n   ✅ Prices cached: {steam_prices_cached}\n   ❌ Errors: {steam_errors}")
        return steam_prices_cached
    
    def fetch_itad_price_enhanced(self, app_id: str) -> tuple[str, str]:
        """Enhanced ITAD fetching with Steam library assistance and name-based search fallback."""
        
        # Strategy 1: Current ITAD App ID lookup (keep existing)
        result = self.fetch_itad_by_appid(app_id)
        if result == "cached":
            return app_id, result
        
        # Strategy 2: Steam library assisted game identification
        game_info = self.get_steam_library_game_info(app_id)
        if game_info and game_info.get('name'):
            result = self.fetch_itad_by_name(app_id, game_info['name'])
            if result == "cached":
                return app_id, result
        
        # Strategy 3: Enhanced name variations (future implementation)
        # Could try alternative names, remove subtitles, etc.
        
        return app_id, "not_found"

    def fetch_itad_by_appid(self, app_id: str) -> str:
        """Original ITAD App ID lookup method."""
        try:
            lookup_url = f"https://api.isthereanydeal.com/games/lookup/v1?key={ITAD_API_KEY}&appid={app_id}"
            lookup_response = self.make_request_with_retry(lookup_url, method="GET", api_type="itad")
            
            if lookup_response is None:
                return "error"
            
            lookup_data = self.handle_api_response(f"ITAD Lookup ({app_id})", lookup_response)
            
            game_id = lookup_data.get("game", {}).get("id") if lookup_data else None
            if not game_id:
                return "not_found" if lookup_data else "error"

            # Use games/prices/v3 for comprehensive price data (Phase 2 enhancement)
            prices_url = f"https://api.isthereanydeal.com/games/prices/v3?key={ITAD_API_KEY}&country=US&shops=61"
            prices_response = self.make_request_with_retry(prices_url, method="POST", json_data=[game_id], api_type="itad")
            
            if prices_response is None:
                return "error"
            
            prices_data = self.handle_api_response(f"ITAD Prices ({app_id})", prices_response)

            if prices_data and len(prices_data) > 0 and prices_data[0].get("historyLow"):
                history_low = prices_data[0]["historyLow"]["all"]
                cache_itad_price_enhanced(app_id, {
                    'lowest_price': str(history_low["amount"]), 
                    'lowest_price_formatted': f"${history_low['amount']}", 
                    'shop_name': "Historical Low (All Stores)"
                }, lookup_method='appid', permanent=True)
                return "cached"
            else:
                return "not_found"
        except Exception as e:
            logger.error(f"Error fetching ITAD price by App ID for {app_id}: {e}")
            return "error"

    def get_steam_library_game_info(self, app_id: str) -> Optional[dict]:
        """Get enhanced game info from Steam library for ITAD matching."""
        try:
            if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
                return None
            
            api = WebAPI(key=STEAMWORKS_API_KEY)
            
            # Get app list and find our app
            app_list = api.call('ISteamApps.GetAppList')
            if app_list and 'applist' in app_list:
                for app in app_list['applist']['apps']:
                    if str(app.get('appid')) == app_id:
                        return {
                            'name': app['name'],
                            'appid': app['appid']
                        }
            
            return None
            
        except Exception as e:
            logger.debug(f"Steam library game info failed for {app_id}: {e}")
            return None

    def fetch_itad_by_name(self, app_id: str, game_name: str) -> str:
        """Try ITAD lookup by game name when App ID lookup fails."""
        try:
            # Use ITAD search API to find game by name
            search_url = f"https://api.isthereanydeal.com/games/search/v1?key={ITAD_API_KEY}&title={game_name}"
            
            search_response = self.make_request_with_retry(search_url, method="GET", api_type="itad")
            if search_response is None:
                return "error"
            
            search_data = self.handle_api_response(f"ITAD Search ({game_name})", search_response)
            if not search_data or len(search_data) == 0:
                return "not_found"
            
            # Take the first match (most relevant)
            game_id = search_data[0].get('id')
            if not game_id:
                return "not_found"
            
            # Now get price data using the found game ID with games/prices/v3
            prices_url = f"https://api.isthereanydeal.com/games/prices/v3?key={ITAD_API_KEY}&country=US&shops=61"
            prices_response = self.make_request_with_retry(prices_url, method="POST", json_data=[game_id], api_type="itad")
            
            if prices_response is None:
                return "error"
            
            prices_data = self.handle_api_response(f"ITAD Prices ({game_name})", prices_response)
            
            if prices_data and len(prices_data) > 0 and prices_data[0].get("historyLow"):
                history_low = prices_data[0]["historyLow"]["all"]
                
                # Cache with enhanced metadata
                cache_itad_price_enhanced(app_id, {
                    'lowest_price': str(history_low["amount"]), 
                    'lowest_price_formatted': f"${history_low['amount']}", 
                    'shop_name': "Historical Low (All Stores)"
                }, lookup_method='name_search', steam_game_name=game_name, permanent=True)
                
                return "cached"
            else:
                return "not_found"
                
        except Exception as e:
            logger.error(f"ITAD name search failed for {game_name}: {e}")
            return "error"

    def fetch_itad_price(self, app_id: str) -> tuple[str, str]:
        """Fetch ITAD price for a single game using enhanced method. Returns (app_id, status)."""
        return self.fetch_itad_price_enhanced(app_id)

    def populate_itad_prices(self, game_ids: Set[str], dry_run: bool = False, force_refresh: bool = False) -> int:
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
        print(f"   🚀 Processing sequentially (1 request at a time)")
        
        if dry_run:
            print("   🔍 DRY RUN: Would fetch ITAD price data")
            return 0
        if not games_to_process:
            print("   ✅ All games already have ITAD price data")
            return 0
        
        itad_prices_cached, itad_errors, itad_not_found = 0, 0, 0
        
        if TQDM_AVAILABLE:
            progress_bar = tqdm(total=len(games_to_process), desc="📈 ITAD Prices", unit="game")
        
        for app_id in games_to_process:
            result = self.fetch_itad_price(app_id)
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
            else:
                processed = itad_prices_cached + itad_not_found + itad_errors
                print(f"   📈 Progress: {processed}/{len(games_to_process)} | Cached: {itad_prices_cached} | Not Found: {itad_not_found} | Errors: {itad_errors}")
        
        if TQDM_AVAILABLE:
            progress_bar.close()
        
        print(f"\n📈 ITAD price population complete!\n   ✅ Prices cached: {itad_prices_cached}\n   ❓ Games not found on ITAD: {itad_not_found}\n   ❌ Errors: {itad_errors}")
        return itad_prices_cached
    
    def refresh_current_prices(self, game_ids: Set[str], dry_run: bool = False) -> int:
        print(f"\n🔄 Refreshing current Steam prices...")
        if not game_ids:
            print("❌ No game IDs to process")
            return 0
        if dry_run:
            print(f"   🔍 DRY RUN: Would refresh {len(game_ids)} current prices")
            return 0
        return self.populate_steam_prices(game_ids, dry_run=False, force_refresh=True)

def main():
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
        migrate_database_phase1() # Run Phase 1 migrations
        migrate_database_phase2() # Run Phase 2 migrations
    except Exception as e:
        print(f"❌ Failed to initialize database or run migrations: {e}")
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
            total_steam_cached = populator.refresh_current_prices(all_game_ids, args.dry_run) if args.refresh_current else populator.populate_steam_prices(all_game_ids, args.dry_run, args.force_refresh)
        
        if not args.steam_only:
            total_itad_cached = populator.populate_itad_prices(all_game_ids, args.dry_run, args.force_refresh)
    finally:
        populator.close()

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
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
