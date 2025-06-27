import sys
import os
import time
import asyncio
import argparse
import requests
import json
from datetime import datetime
from typing import Dict, List, Set, Optional

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    print("⚠️  tqdm not available. Install with: pip install tqdm")
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


class PricePopulator:
    """Handles comprehensive price data population with rate limiting."""
    
    def __init__(self, rate_limit_mode: str = "normal"):
        """Initialize the populator with specified rate limiting."""
        self.rate_limits = {
            "fast": {"steam_api": 0.8, "store_api": 1.0, "itad_api": 0.5},
            "normal": {"steam_api": 1.0, "store_api": 1.5, "itad_api": 1.0},
            "slow": {"steam_api": 1.5, "store_api": 2.0, "itad_api": 2.0},
            "conservative": {"steam_api": 2.0, "store_api": 3.0, "itad_api": 3.0}
        }
        
        self.current_limits = self.rate_limits.get(rate_limit_mode, self.rate_limits["normal"])
        self.last_steam_api_call = 0.0
        self.last_store_api_call = 0.0
        self.last_itad_api_call = 0.0
        
        print(f"🔧 Rate limiting mode: {rate_limit_mode}")
        print(f"   Steam API: {self.current_limits['steam_api']}s")
        print(f"   Store API: {self.current_limits['store_api']}s")
        print(f"   ITAD API: {self.current_limits['itad_api']}s")
    
    async def rate_limit_steam_api(self):
        """Enforce rate limiting for Steam API calls."""
        current_time = time.time()
        time_since_last = current_time - self.last_steam_api_call
        
        if time_since_last < self.current_limits["steam_api"]:
            sleep_time = self.current_limits["steam_api"] - time_since_last
            await asyncio.sleep(sleep_time)
        
        self.last_steam_api_call = time.time()
    
    async def rate_limit_store_api(self):
        """Enforce rate limiting for Steam Store API calls."""
        current_time = time.time()
        time_since_last = current_time - self.last_store_api_call
        
        if time_since_last < self.current_limits["store_api"]:
            sleep_time = self.current_limits["store_api"] - time_since_last
            await asyncio.sleep(sleep_time)
        
        self.last_store_api_call = time.time()
    
    async def rate_limit_itad_api(self):
        """Enforce rate limiting for ITAD API calls."""
        current_time = time.time()
        time_since_last = current_time - self.last_itad_api_call
        
        if time_since_last < self.current_limits["itad_api"]:
            sleep_time = self.current_limits["itad_api"] - time_since_last
            await asyncio.sleep(sleep_time)
        
        self.last_itad_api_call = time.time()
    
    def handle_api_response(self, api_name: str, response: requests.Response) -> Optional[dict]:
        """Handle API responses with error checking."""
        try:
            response.raise_for_status()
            return json.loads(response.text)
        except requests.exceptions.RequestException as e:
            print(f"❌ Request error for {api_name}: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error for {api_name}: {e}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error for {api_name}: {e}")
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
    
    def collect_all_game_ids(self, family_members: Dict[str, str]) -> Set[str]:
        """Collect all unique game IDs from family member wishlists only."""
        all_game_ids = set()
        
        print("\n📊 Collecting game IDs from family wishlists...")
        
        # Collect from wishlists only (deals commands only work with wishlist games)
        for steam_id, name in family_members.items():
            cached_wishlist = get_cached_wishlist(steam_id)
            if cached_wishlist:
                all_game_ids.update(cached_wishlist)
                print(f"   📋 {name}: {len(cached_wishlist)} wishlist games")
            else:
                print(f"   ⚠️  {name}: No cached wishlist found")
        
        print(f"\n🎯 Total unique wishlist games to process: {len(all_game_ids)}")
        return all_game_ids
    
    async def populate_steam_prices(self, game_ids: Set[str], dry_run: bool = False, force_refresh: bool = False) -> int:
        """Populate Steam Store price data for all games."""
        print(f"\n💰 Starting Steam price population...")
        
        if not game_ids:
            print("❌ No game IDs to process")
            return 0
        
        games_to_process = []
        games_skipped = 0
        
        # Filter games that need price updates
        for app_id in game_ids:
            if not force_refresh:
                cached_game = get_cached_game_details(app_id)
                if cached_game and (cached_game.get('price_data') or cached_game.get('price_overview')):
                    games_skipped += 1
                    continue
            games_to_process.append(app_id)
        
        print(f"   🎯 Games to process: {len(games_to_process)}")
        print(f"   ⏭️  Games skipped (already have price data): {games_skipped}")
        
        if dry_run:
            print("   🔍 DRY RUN: Would fetch Steam price data")
            return 0
        
        if not games_to_process:
            print("   ✅ All games already have Steam price data")
            return 0
        
        steam_prices_cached = 0
        steam_errors = 0
        
        if TQDM_AVAILABLE:
            game_iterator = tqdm(games_to_process, desc="💰 Steam Prices", unit="game")
        else:
            game_iterator = games_to_process
        
        for i, app_id in enumerate(game_iterator):
            try:
                await self.rate_limit_store_api()
                game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                
                response = requests.get(game_url, timeout=10)
                game_info = self.handle_api_response(f"Steam Store ({app_id})", response)
                
                if not game_info:
                    steam_errors += 1
                    continue
                
                game_data = game_info.get(str(app_id), {}).get("data")
                if not game_data:
                    steam_errors += 1
                    continue
                
                # Cache the complete game data (includes price_overview)
                cache_game_details(app_id, game_data, permanent=True)
                steam_prices_cached += 1
                
                if TQDM_AVAILABLE and isinstance(game_iterator, tqdm):
                    game_iterator.set_postfix_str(f"Cached: {steam_prices_cached}, Errors: {steam_errors}")
                elif not TQDM_AVAILABLE and (i + 1) % 50 == 0:
                    print(f"   📈 Progress: {i + 1}/{len(games_to_process)} | Cached: {steam_prices_cached} | Errors: {steam_errors}")
                
            except Exception as e:
                steam_errors += 1
                if not TQDM_AVAILABLE:
                    print(f"   ⚠️  Error processing Steam price for {app_id}: {e}")
                continue
        
        print(f"\n💰 Steam price population complete!")
        print(f"   ✅ Prices cached: {steam_prices_cached}")
        print(f"   ❌ Errors: {steam_errors}")
        
        return steam_prices_cached
    
    async def populate_itad_prices(self, game_ids: Set[str], dry_run: bool = False, force_refresh: bool = False) -> int:
        """Populate ITAD historical price data for all games."""
        print(f"\n📈 Starting ITAD price population...")
        
        if not ITAD_API_KEY or ITAD_API_KEY == "YOUR_ITAD_API_KEY_HERE":
            print("❌ ITAD API key not configured. Skipping ITAD price population.")
            return 0
        
        if not game_ids:
            print("❌ No game IDs to process")
            return 0
        
        games_to_process = []
        games_skipped = 0
        
        # Filter games that need ITAD updates
        for app_id in game_ids:
            if not force_refresh:
                cached_itad = get_cached_itad_price(app_id)
                if cached_itad:
                    games_skipped += 1
                    continue
            games_to_process.append(app_id)
        
        print(f"   🎯 Games to process: {len(games_to_process)}")
        print(f"   ⏭️  Games skipped (already have ITAD data): {games_skipped}")
        
        if dry_run:
            print("   🔍 DRY RUN: Would fetch ITAD price data")
            return 0
        
        if not games_to_process:
            print("   ✅ All games already have ITAD price data")
            return 0
        
        itad_prices_cached = 0
        itad_errors = 0
        itad_not_found = 0
        
        if TQDM_AVAILABLE:
            game_iterator = tqdm(games_to_process, desc="📈 ITAD Prices", unit="game")
        else:
            game_iterator = games_to_process
        
        for i, app_id in enumerate(game_iterator):
            try:
                # Step 1: Lookup game ID on ITAD
                await self.rate_limit_itad_api()
                lookup_url = f"https://api.isthereanydeal.com/games/lookup/v1?key={ITAD_API_KEY}&appid={app_id}"
                
                lookup_response = requests.get(lookup_url, timeout=10)
                lookup_data = self.handle_api_response(f"ITAD Lookup ({app_id})", lookup_response)
                
                if not lookup_data:
                    itad_errors += 1
                    continue
                
                game_id = lookup_data.get("game", {}).get("id")
                if not game_id:
                    itad_not_found += 1
                    continue
                
                # Step 2: Get historical low price
                await self.rate_limit_itad_api()
                storelow_url = f"https://api.isthereanydeal.com/games/storelow/v2?key={ITAD_API_KEY}&country=US&shops=61"
                
                storelow_response = requests.post(storelow_url, json=[game_id], timeout=10)
                storelow_data = self.handle_api_response(f"ITAD StoreLow ({app_id})", storelow_response)
                
                if not storelow_data or not storelow_data[0].get("lows"):
                    itad_not_found += 1
                    continue
                
                # Extract price information
                price_amount = storelow_data[0]["lows"][0]["price"]["amount"]
                shop_name = storelow_data[0]["lows"][0].get("shop", {}).get("name", "Unknown Store")
                
                # Cache the ITAD price data for 24 hours (longer during sales)
                cache_itad_price(app_id, {
                    'lowest_price': str(price_amount),
                    'lowest_price_formatted': f"${price_amount}",
                    'shop_name': shop_name
                }, cache_hours=24)
                
                itad_prices_cached += 1
                
                if TQDM_AVAILABLE and isinstance(game_iterator, tqdm):
                    game_iterator.set_postfix_str(f"Cached: {itad_prices_cached}, Not Found: {itad_not_found}, Errors: {itad_errors}")
                elif not TQDM_AVAILABLE and (i + 1) % 25 == 0:  # Less frequent updates for ITAD
                    print(f"   📈 Progress: {i + 1}/{len(games_to_process)} | Cached: {itad_prices_cached} | Not Found: {itad_not_found} | Errors: {itad_errors}")
                
            except Exception as e:
                itad_errors += 1
                if not TQDM_AVAILABLE:
                    print(f"   ⚠️  Error processing ITAD price for {app_id}: {e}")
                continue
        
        print(f"\n📈 ITAD price population complete!")
        print(f"   ✅ Prices cached: {itad_prices_cached}")
        print(f"   ❓ Games not found on ITAD: {itad_not_found}")
        print(f"   ❌ Errors: {itad_errors}")
        
        return itad_prices_cached
    
    async def refresh_current_prices(self, game_ids: Set[str], dry_run: bool = False) -> int:
        """Refresh current Steam prices for games (useful during active sales)."""
        print(f"\n🔄 Refreshing current Steam prices...")
        
        if not game_ids:
            print("❌ No game IDs to process")
            return 0
        
        if dry_run:
            print(f"   🔍 DRY RUN: Would refresh {len(game_ids)} current prices")
            return 0
        
        # Force refresh all Steam prices
        return await self.populate_steam_prices(game_ids, dry_run=False, force_refresh=True)


async def main():
    """Main function to run the price population."""
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
    
    # Determine rate limiting mode
    rate_mode = "normal"
    if args.fast:
        rate_mode = "fast"
    elif args.slow:
        rate_mode = "slow"
    elif args.conservative:
        rate_mode = "conservative"
    
    print("💰 FamilyBot Price Population Script")
    print("=" * 50)
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
    
    if args.refresh_current:
        print("🔄 REFRESH MODE - Will update current prices even if cached")
    
    if args.force_refresh:
        print("🔄 FORCE REFRESH MODE - Will update all price data even if cached")
    
    # Initialize database
    try:
        init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        return 1
    
    # Initialize populator
    populator = PricePopulator(rate_mode)
    
    # Load family members
    family_members = populator.load_family_members()
    if not family_members:
        print("❌ No family members found. Check your configuration.")
        return 1
    
    # Collect all game IDs
    all_game_ids = populator.collect_all_game_ids(family_members)
    if not all_game_ids:
        print("❌ No games found to process. Run populate_database.py first.")
        return 1
    
    start_time = datetime.now()
    total_steam_cached = 0
    total_itad_cached = 0
    
    # Populate Steam prices
    if not args.itad_only:
        if args.refresh_current:
            total_steam_cached = await populator.refresh_current_prices(all_game_ids, args.dry_run)
        else:
            total_steam_cached = await populator.populate_steam_prices(all_game_ids, args.dry_run, args.force_refresh)
    
    # Populate ITAD prices
    if not args.steam_only:
        total_itad_cached = await populator.populate_itad_prices(all_game_ids, args.dry_run, args.force_refresh)
    
    # Final summary
    end_time = datetime.now()
    duration = end_time - start_time
    
    print("\n" + "=" * 50)
    print("🎉 Price Population Complete!")
    print(f"⏱️  Duration: {duration.total_seconds():.1f} seconds")
    print(f"🎮 Games processed: {len(all_game_ids)}")
    print(f"💰 Steam prices cached: {total_steam_cached}")
    print(f"📈 ITAD prices cached: {total_itad_cached}")
    print(f"💾 Total price entries: {total_steam_cached + total_itad_cached}")
    
    if not args.dry_run:
        print("\n🚀 Price data population complete!")
        print("   All deal commands will now run at maximum speed!")
        print("   Perfect for Steam Summer/Winter Sales! 🎊")
    
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
