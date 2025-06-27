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
    from tqdm.asyncio import tqdm as atqdm
    TQDM_AVAILABLE = True
except ImportError:
    print("⚠️  tqdm not available. Install with: pip install tqdm")
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


class DatabasePopulator:
    """Handles database population with rate limiting and progress tracking."""
    
    def __init__(self, rate_limit_mode: str = "normal"):
        """Initialize the populator with specified rate limiting."""
        self.rate_limits = {
            "fast": {"steam_api": 0.8, "store_api": 1.0},
            "normal": {"steam_api": 1.0, "store_api": 1.5},
            "slow": {"steam_api": 1.5, "store_api": 2.0}
        }
        
        self.current_limits = self.rate_limits.get(rate_limit_mode, self.rate_limits["normal"])
        self.last_steam_api_call = 0.0
        self.last_store_api_call = 0.0
        
        print(f"🔧 Rate limiting mode: {rate_limit_mode}")
        print(f"   Steam API: {self.current_limits['steam_api']}s")
        print(f"   Store API: {self.current_limits['store_api']}s")
    
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
    
    def handle_api_response(self, api_name: str, response: requests.Response) -> Optional[dict]:
        """Handle API responses with error checking and enhanced logging."""
        try:
            response.raise_for_status()
            return json.loads(response.text)
        except requests.exceptions.RequestException as e:
            log_api_error(logger, api_name, e, f"Status: {response.status_code}")
            print(f"❌ Request error for {api_name}: {e}")
            return None
        except json.JSONDecodeError as e:
            log_api_error(logger, api_name, e, f"Response: {response.text[:100]}")
            print(f"❌ JSON decode error for {api_name}: {e}")
            return None
        except Exception as e:
            log_api_error(logger, api_name, e)
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
    
    async def populate_family_libraries(self, family_members: Dict[str, str], dry_run: bool = False) -> int:
        """Populate database with all family member game libraries."""
        print("\n🎮 Starting family library population...")
        
        if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
            print("❌ Steam API key not configured. Cannot fetch family libraries.")
            return 0
        
        total_cached = 0
        total_processed = 0
        
        if TQDM_AVAILABLE:
            member_iterator = tqdm(family_members.items(), desc="👥 Family Members", unit="member", leave=True)
        else:
            member_iterator = family_members.items()

        for steam_id, name in member_iterator:
            if TQDM_AVAILABLE:
                # Explicitly cast to tqdm type for Pylance, or check if it's a tqdm instance
                # This helps Pylance understand that `member_iterator` has `set_postfix_str`
                if isinstance(member_iterator, tqdm):
                    member_iterator.set_postfix_str(f"Processing {name}") # pyright: ignore [reportAttributeAccessIssue]
                else: # Fallback for non-tqdm iterators if any custom ones are used
                    print(f"\n📊 Processing {name}...")
            else:
                print(f"\n📊 Processing {name}...")
            
            try:
                # Get user's owned games
                await self.rate_limit_steam_api()
                owned_games_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={STEAMWORKS_API_KEY}&steamid={steam_id}&include_appinfo=1&include_played_free_games=1"
                
                if dry_run:
                    if not TQDM_AVAILABLE:
                        print(f"   🔍 Would fetch owned games for {name}")
                    continue
                
                response = requests.get(owned_games_url, timeout=15)
                games_data = self.handle_api_response(f"GetOwnedGames ({name})", response)
                
                if not games_data:
                    if not TQDM_AVAILABLE:
                        print(f"   ❌ Failed to get games for {name}")
                    continue
                
                games = games_data.get("response", {}).get("games", [])
                if not games:
                    if not TQDM_AVAILABLE:
                        print(f"   ⚠️  No games found for {name} (private profile?)")
                    continue
                
                if not TQDM_AVAILABLE:
                    print(f"   🎯 Found {len(games)} games")
                
                user_cached = 0
                user_skipped = 0
                
                if TQDM_AVAILABLE:
                    games_progress_iterator = tqdm(games, desc=f"🎮 {name[:15]}", unit="game", leave=False)
                else:
                    games_progress_iterator = games

                for game in games_progress_iterator:
                    app_id = str(game.get("appid"))
                    if not app_id:
                        continue
                    
                    total_processed += 1
                    
                    # Check if already cached
                    if get_cached_game_details(app_id):
                        user_skipped += 1
                        if TQDM_AVAILABLE and isinstance(games_progress_iterator, tqdm):
                            games_progress_iterator.set_postfix_str(f"Cached: {user_cached}, Skipped: {user_skipped}")
                        continue
                    
                    # Fetch game details
                    await self.rate_limit_store_api()
                    game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                    
                    try:
                        game_response = requests.get(game_url, timeout=10)
                        game_info = self.handle_api_response(f"AppDetails ({app_id})", game_response)
                        
                        if not game_info:
                            continue
                        
                        game_data = game_info.get(str(app_id), {}).get("data")
                        if not game_data:
                            continue
                        
                        # Cache the game details
                        cache_game_details(app_id, game_data, permanent=True)
                        user_cached += 1
                        total_cached += 1
                        
                        if TQDM_AVAILABLE and isinstance(games_progress_iterator, tqdm):
                            games_progress_iterator.set_postfix_str(f"Cached: {user_cached}, Skipped: {user_skipped}")
                        
                    except Exception as e:
                        if not TQDM_AVAILABLE:
                            print(f"   ⚠️  Error processing game {app_id}: {e}")
                        continue
                
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
                await self.rate_limit_steam_api()
                wishlist_url = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?key={STEAMWORKS_API_KEY}&steamid={steam_id}"
                
                response = requests.get(wishlist_url, timeout=15)
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
        
        # Process common wishlist games
        common_games = [item for item in global_wishlist if len(item[1]) > 1]
        if not common_games:
            print("\n🎯 No common wishlist games found")
            return 0
        
        print(f"\n🎯 Processing {len(common_games)} common wishlist games...")
        
        if dry_run:
            print("   🔍 Would process common wishlist games for caching")
            return 0
        
        for i, item in enumerate(common_games):
            app_id = item[0]
            
            # Check if already cached
            if get_cached_game_details(app_id):
                continue
            
            try:
                await self.rate_limit_store_api()
                game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                
                response = requests.get(game_url, timeout=10)
                game_info = self.handle_api_response(f"AppDetails ({app_id})", response)
                
                if not game_info:
                    continue
                
                game_data = game_info.get(str(app_id), {}).get("data")
                if not game_data:
                    continue
                
                # Cache the game details
                cache_game_details(app_id, game_data, permanent=True)
                total_cached += 1
                
                # Progress update every 10 games
                if (i + 1) % 10 == 0:
                    print(f"   📈 Progress: {i + 1}/{len(common_games)} games processed")
            
            except Exception as e:
                print(f"   ⚠️  Error processing game {app_id}: {e}")
                continue
        
        print(f"\n🎯 Wishlist population complete!")
        print(f"   💾 Common games cached: {total_cached}")
        
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
