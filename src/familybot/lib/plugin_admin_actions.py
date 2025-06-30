import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from familybot.config import (ADMIN_DISCORD_ID, FAMILY_STEAM_ID,
                              FAMILY_USER_DICT, NEW_GAME_CHANNEL_ID,
                              PROJECT_ROOT, STEAMWORKS_API_KEY,
                              WISHLIST_CHANNEL_ID)
from familybot.lib.database import (cache_family_library, cache_game_details,
                                    cache_wishlist, get_cached_family_library,
                                    get_cached_game_details,
                                    get_cached_wishlist, get_db_connection)
from familybot.lib.familly_game_manager import get_saved_games, set_saved_games
from familybot.lib.family_utils import (find_in_2d_list, format_message,
                                        get_family_game_list_url)
from familybot.lib.logging_config import (get_logger, log_api_error,
                                          log_private_profile_detection,
                                          log_rate_limit)
from familybot.lib.utils import (ProgressTracker, get_lowest_price,
                                 truncate_message_list)

logger = get_logger("plugin_admin_actions")

# --- Rate limiting constants (copied from steam_family.py for consistency) ---
STEAM_API_RATE_LIMIT = 3.0
STEAM_STORE_API_RATE_LIMIT = 2.0
FULL_SCAN_RATE_LIMIT = 5.0

# --- Global variables for rate limiting (per process, not shared across multiple processes) ---
_last_steam_api_call = 0.0
_last_steam_store_api_call = 0.0

# --- Migration Flag for Family Members (copied from steam_family.py) ---
_family_members_migrated_this_run = False

async def _rate_limit_steam_api() -> None:
    """Enforce rate limiting for Steam API calls (non-storefront)."""
    global _last_steam_api_call
    current_time = time.time()
    time_since_last_call = current_time - _last_steam_api_call
    
    if time_since_last_call < STEAM_API_RATE_LIMIT:
        sleep_time = STEAM_API_RATE_LIMIT - time_since_last_call
        logger.debug(f"Rate limiting Steam API call, sleeping for {sleep_time:.2f} seconds")
        await asyncio.sleep(sleep_time)
    
    _last_steam_api_call = time.time()

async def _rate_limit_steam_store_api() -> None:
    """Enforce rate limiting for Steam Store API calls (e.g., appdetails)."""
    global _last_steam_store_api_call
    current_time = time.time()
    time_since_last_call = current_time - _last_steam_store_api_call
    
    if time_since_last_call < STEAM_STORE_API_RATE_LIMIT:
        sleep_time = STEAM_STORE_API_RATE_LIMIT - time_since_last_call
        logger.debug(f"Rate limiting Steam Store API call, sleeping for {sleep_time:.2f} seconds")
        await asyncio.sleep(sleep_time)
    
    _last_steam_store_api_call = time.time()

async def _rate_limit_full_scan() -> None:
    """Enforce slower rate limiting for full wishlist scans to avoid hitting API limits."""
    global _last_steam_store_api_call
    current_time = time.time()
    time_since_last_call = current_time - _last_steam_store_api_call
    
    if time_since_last_call < FULL_SCAN_RATE_LIMIT:
        sleep_time = FULL_SCAN_RATE_LIMIT - time_since_last_call
        logger.debug(f"Rate limiting full scan API call, sleeping for {sleep_time:.2f} seconds")
        await asyncio.sleep(sleep_time)
    
    _last_steam_store_api_call = time.time()

async def _handle_api_response(api_name: str, response: requests.Response) -> dict | None:
    """Helper to process API responses, handle errors, and return JSON data."""
    try:
        response.raise_for_status()
        json_data = json.loads(response.text)
        return json_data
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error for {api_name}: {e}. URL: {response.request.url}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for {api_name}: {e}. Raw: {response.text[:200]}")
    except Exception as e:
        logger.critical(f"An unexpected error occurred processing {api_name} response: {e}", exc_info=True)
    return None

async def _load_family_members_from_db() -> dict:
    """
    Loads family member data (steam_id: friendly_name) from the database,
    performing a one-time migration from config.yml if necessary.
    """
    global _family_members_migrated_this_run
    members = {}
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not _family_members_migrated_this_run:
            cursor.execute("SELECT COUNT(*) FROM family_members")
            if cursor.fetchone()[0] == 0 and FAMILY_USER_DICT:
                logger.info("Database: 'family_members' table is empty. Attempting to migrate from config.yml.")
                config_members_to_insert = []
                for steam_id, name in FAMILY_USER_DICT.items():
                    config_members_to_insert.append((steam_id, name, None))
                
                try:
                    if config_members_to_insert:
                        cursor.executemany("INSERT OR IGNORE INTO family_members (steam_id, friendly_name, discord_id) VALUES (?, ?, ?)", config_members_to_insert)
                        conn.commit()
                        logger.info(f"Database: Migrated {len(config_members_to_insert)} family members from config.yml.")
                        _family_members_migrated_this_run = True
                    else:
                        logger.info("Database: No family members found in config.yml for migration.")
                        _family_members_migrated_this_run = True
                except sqlite3.Error as e:
                    logger.error(f"Database: Error during family_members migration from config.yml: {e}")
            else:
                logger.debug("Database: 'family_members' table already has data or config.yml is empty. Skipping config.yml migration.")
                _family_members_migrated_this_run = True

        cursor.execute("SELECT steam_id, friendly_name FROM family_members")
        for row in cursor.fetchall():
            steam_id = row["steam_id"]
            friendly_name = row["friendly_name"]
            # Basic validation for SteamID64: must be 17 digits and start with '7656119'
            if isinstance(steam_id, str) and len(steam_id) == 17 and steam_id.startswith("7656119"):
                members[steam_id] = friendly_name
            else:
                logger.warning(f"Database: Invalid SteamID '{steam_id}' found for user '{friendly_name}'. Skipping this entry.")
        logger.debug(f"Loaded {len(members)} valid family members from database.")
    except sqlite3.Error as e:
        logger.error(f"Error reading family members from DB: {e}")
    finally:
        if conn:
            conn.close()
    return members

async def purge_game_details_cache_action() -> Dict[str, Any]:
    """
    Purges the game details cache table.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM game_details_cache")
        cache_count = cursor.fetchone()[0]
        
        cursor.execute("DELETE FROM game_details_cache")
        conn.commit()
        conn.close()
        
        logger.info(f"Admin purged game details cache: {cache_count} entries deleted")
        return {"success": True, "message": f"Cache purge complete! Deleted {cache_count} cached game entries.\n\nNext steps:\n- Run populate-database to rebuild cache with USD pricing and new boolean fields."}
    except Exception as e:
        logger.error(f"Error purging game details cache: {e}", exc_info=True)
        return {"success": False, "message": f"Error purging cache: {e}"}

async def force_new_game_action() -> Dict[str, Any]:
    """
    Forces a check for new games and triggers notifications.
    """
    logger.info("Running force_new_game_action...")

    try:
        # Try to get cached family library first
        cached_family_library = get_cached_family_library()
        if cached_family_library is not None:
            logger.info(f"Using cached family library for new game check ({len(cached_family_library)} games)")
            game_list = cached_family_library
        else:
            # If not cached, fetch from API
            await _rate_limit_steam_api() # Apply rate limit before API call
            url_family_list = get_family_game_list_url() # Use the correct URL for family shared apps
            answer = requests.get(url_family_list, timeout=15)
            games_json = await _handle_api_response("GetFamilySharedApps", answer)
            if not games_json: 
                return {"success": False, "message": "Failed to get family shared apps."}

            game_list = games_json.get("response", {}).get("apps", [])
            if not game_list:
                logger.warning("No apps found in family game list response for new game check.")
                return {"success": False, "message": "No games found in the family library."}
            
            # Cache the family library for 30 minutes
            cache_family_library(game_list, cache_minutes=30)

        current_family_members = await _load_family_members_from_db()
        
        game_owner_list = {}
        game_array = []
        for game in game_list:
            if game.get("exclude_reason") != 3:
                appid = str(game.get("appid"))
                game_array.append(appid)
                if len(game.get("owner_steamids", [])) == 1:
                    game_owner_list[appid] = str(game["owner_steamids"][0])


        saved_games_with_timestamps = get_saved_games()
        saved_appids = {item[0] for item in saved_games_with_timestamps}

        new_appids = set(game_array) - saved_appids

        all_games_for_db_update = []
        current_utc_iso = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'

        for appid in game_array:
            if appid in new_appids:
                all_games_for_db_update.append((appid, current_utc_iso))
            else:
                found_timestamp = next((ts for ap, ts in saved_games_with_timestamps if ap == appid), None)
                if found_timestamp:
                    all_games_for_db_update.append((appid, found_timestamp))
                else:
                    all_games_for_db_update.append((appid, current_utc_iso))


        new_games_to_notify_raw = [(appid, current_utc_iso) for appid in new_appids]
        new_games_to_notify_raw.sort(key=lambda x: x[1], reverse=True)

        if len(new_games_to_notify_raw) > 10:
            logger.warning(f"Detected {len(new_games_to_notify_raw)} new games. Processing only the latest 10 (by AppID) to avoid rate limits.")
            # In a real scenario, you might want to send a Discord message here.
            # For web UI, we just log and process a subset.
            new_games_to_process = new_games_to_notify_raw[:10]
            message_prefix = f"Detected {len(new_games_to_notify_raw)} new games. Processing only the latest 10. More may be announced in subsequent checks.\n"
        else:
            new_games_to_process = new_games_to_notify_raw
            message_prefix = ""

        notification_messages = []
        if new_games_to_process:
            logger.info(f"Processing {len(new_games_to_process)} new games for notification.")
            for new_appid_tuple in new_games_to_process:
                new_appid = new_appid_tuple[0]

                # Try to get cached game details first
                cached_game = get_cached_game_details(new_appid)
                if cached_game:
                    logger.info(f"Using cached game details for new game AppID: {new_appid}")
                    game_data = cached_game
                else:
                    # If not cached, fetch from API
                    await _rate_limit_steam_store_api() # Apply store API rate limit
                    game_url = f"https://store.steampowered.com/api/appdetails?appids={new_appid}&cc=us&l=en"
                    logger.info(f"Fetching app details from API for new game AppID: {new_appid}")
                    app_info_response = requests.get(game_url, timeout=10)
                    game_info_json = await _handle_api_response("AppDetails (New Game)", app_info_response)
                    if not game_info_json: continue

                    game_data = game_info_json.get(str(new_appid), {}).get("data")
                    if not game_data:
                        logger.warning(f"No game data found for new game AppID {new_appid} in app details response.")
                        continue
                    
                    # Cache the game details permanently (game details rarely change)
                    cache_game_details(new_appid, game_data, permanent=True)

                is_family_shared_game = any(cat.get("id") == 62 for cat in game_data.get("categories", []))

                if game_data.get("type") == "game" and game_data.get("is_free") == False and is_family_shared_game:
                    owner_steam_id = game_owner_list.get(str(new_appid))
                    owner_name = current_family_members.get(owner_steam_id, f"Unknown Owner ({owner_steam_id})")
                    
                    # Build the base message
                    game_name = game_data.get("name", f"Unknown Game")
                    message = f"Thank you to {owner_name} for **{game_name}**\nhttps://store.steampowered.com/app/{new_appid}"
                    
                    # Add pricing information if available
                    try:
                        current_price = game_data.get('price_overview', {}).get('final_formatted', 'N/A')
                        lowest_price = get_lowest_price(int(new_appid))
                        
                        if current_price != 'N/A' or lowest_price != 'N/A':
                            price_info = []
                            if current_price != 'N/A':
                                price_info.append(f"Current: {current_price}")
                            if lowest_price != 'N/A':
                                price_info.append(f"Lowest ever: ${lowest_price}")
                            
                            if price_info:
                                message += f"\n💰 {'|'.join(price_info)}"
                    except Exception as e:
                        logger.warning(f"Could not get pricing info for new game {new_appid}: {e}")
                    
                    notification_messages.append(message)
                else:
                    logger.debug(f"Skipping new game {new_appid}: not a paid game, not family shared, or not type 'game'.")

            set_saved_games(all_games_for_db_update)
            if notification_messages:
                full_message = message_prefix + "\n\n".join(notification_messages)
                return {"success": True, "message": f"New games detected: {len(new_games_to_process)} games processed. Details:\n{full_message}"}
            else:
                return {"success": True, "message": "No new family shared games detected for notification."}
        else:
            logger.info('No new games detected.')
            return {"success": True, "message": "No new games detected."}

    except Exception as e:
        logger.critical(f"An unexpected error occurred in force_new_game_action: {e}", exc_info=True)
        return {"success": False, "message": f"Error forcing new game notification: {str(e)}"}

async def force_wishlist_action() -> Dict[str, Any]:
    """
    Forces a refresh of the wishlist data.
    """
    logger.info("Running force_wishlist_action task...")
    if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
        logger.error("STEAMWORKS_API_KEY is not configured for wishlist task.")
        return {"success": False, "message": "Steam API key is not configured for wishlist task."}

    global_wishlist = []

    current_family_members = await _load_family_members_from_db()
    
    all_unique_steam_ids_to_check = set(current_family_members.keys())

    for user_steam_id in all_unique_steam_ids_to_check:
        user_name_for_log = current_family_members.get(user_steam_id, f"Unknown ({user_steam_id})")

        # Try to get cached wishlist first
        cached_wishlist = get_cached_wishlist(user_steam_id)
        if cached_wishlist is not None:
            logger.info(f"Using cached wishlist for {user_name_for_log} ({len(cached_wishlist)} items)")
            for app_id in cached_wishlist:
                idx = find_in_2d_list(app_id, global_wishlist)
                if idx is not None:
                    global_wishlist[idx][1].append(user_steam_id)
                else:
                    global_wishlist.append([app_id, [user_steam_id]])
            continue

        # If not cached, fetch from API
        wishlist_url = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?key={STEAMWORKS_API_KEY}&steamid={user_steam_id}"
        logger.info(f"Fetching wishlist from API for {user_name_for_log} (Steam ID: {user_steam_id})")

        wishlist_json = None
        try:
            await _rate_limit_steam_api() # Apply rate limit here
            wishlist_response = requests.get(wishlist_url, timeout=15)
            if wishlist_response.text == "{\"success\":2}":
                log_private_profile_detection(logger, user_name_for_log, user_steam_id, "wishlist")
                continue

            wishlist_json = await _handle_api_response(f"GetWishlist ({user_name_for_log})", wishlist_response)
            if not wishlist_json: continue

            wishlist_items = wishlist_json.get("response", {}).get("items", [])

            if not wishlist_items:
                logger.info(f"No items found in {user_name_for_log}'s wishlist.")
                continue

            # Extract app IDs for caching
            user_wishlist_appids = []
            for game_item in wishlist_items:
                app_id = str(game_item.get("appid"))
                if not app_id:
                    logger.warning(f"Skipping wishlist item due to missing appid: {game_item}")
                    continue

                user_wishlist_appids.append(app_id)
                idx = find_in_2d_list(app_id, global_wishlist)
                if idx is not None:
                    global_wishlist[idx][1].append(user_steam_id)
                else:
                    global_wishlist.append([app_id, [user_steam_id]])

            # Cache the wishlist for 2 hours
            cache_wishlist(user_steam_id, user_wishlist_appids, cache_hours=2)

        except Exception as e:
            logger.critical(f"An unexpected error occurred fetching/processing {user_name_for_log}'s wishlist: {e}", exc_info=True)

    # First, collect all duplicate games without fetching details
    potential_duplicate_games = []
    for item in global_wishlist:
        app_id = item[0]
        owner_steam_ids = item[1]
        if len(owner_steam_ids) > 1:
            potential_duplicate_games.append(item)

    # Sort and slice the potential duplicate games for processing
    sorted_duplicate_games = sorted(potential_duplicate_games, key=lambda x: x[0], reverse=True)
    
    MAX_WISHLIST_GAMES_TO_PROCESS = 100 # This constant should be defined centrally if possible
    if len(sorted_duplicate_games) > MAX_WISHLIST_GAMES_TO_PROCESS:
        logger.warning(f"Detected {len(sorted_duplicate_games)} common wishlist games. Processing only the latest {MAX_WISHLIST_GAMES_TO_PROCESS} to avoid rate limits.")
        games_to_process = sorted_duplicate_games[:MAX_WISHLIST_GAMES_TO_PROCESS]
        message_prefix = f"Detected {len(sorted_duplicate_games)} common wishlist games. Processing only the latest {MAX_WISHLIST_GAMES_TO_PROCESS}. More may be announced in subsequent checks.\n"
    else:
        games_to_process = sorted_duplicate_games
        message_prefix = ""

    # Now process the selected games and fetch their details
    duplicate_games_for_display = []
    saved_game_appids = {item[0] for item in get_saved_games()}  # Get saved game app IDs for comparison

    for item in games_to_process:
        app_id = item[0]
        
        game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
        logger.info(f"Fetching app details for wishlist AppID: {app_id}")

        game_info_json = None
        try:
            await _rate_limit_steam_store_api() # Apply store API rate limit
            game_info_response = requests.get(game_url, timeout=10)
            game_info_json = await _handle_api_response("AppDetails (Wishlist)", game_info_response)
            if not game_info_json: continue

            game_data = game_info_json.get(str(app_id), {}).get("data")
            if not game_data:
                logger.warning(f"No game data found for wishlist AppID {app_id} in app details response.")
                continue

            # Use cached boolean fields for faster performance
            is_family_shared = game_data.get("is_family_shared", False)

            if (game_data.get("type") == "game"
                and game_data.get("is_free") == False
                and is_family_shared
                and "recommendations" in game_data
                and app_id not in saved_game_appids
                ):
                duplicate_games_for_display.append(item)
            else:
                logger.debug(f"Skipping wishlist game {app_id}: not a paid game, not family shared category, or no recommendations, or already owned.")

        except Exception as e:
            logger.critical(f"An unexpected error occurred processing duplicate wishlist game {app_id}: {e}", exc_info=True)

    if duplicate_games_for_display:
        wishlist_message_content = format_message(duplicate_games_for_display, short=False)
        full_message = message_prefix + wishlist_message_content
        return {"success": True, "message": f"Wishlist refreshed. Details:\n{full_message}"}
    else:
        return {"success": True, "message": "Wishlist refreshed. No common wishlist games found for display."}

async def force_deals_action(target_friendly_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Forces a check for deals on wishlist games and returns results.
    If target_friendly_name is provided, checks only that user's wishlist.
    If no target_friendly_name is provided, checks all family wishlists.
    """
    logger.info("Running force_deals_action...")
    
    try:
        current_family_members = await _load_family_members_from_db()
        
        target_user_steam_ids = []
        if target_friendly_name:
            # Find the SteamID for the given friendly name
            found_steam_id = None
            for steam_id, friendly_name in current_family_members.items():
                if friendly_name.lower() == target_friendly_name.lower():
                    found_steam_id = steam_id
                    break
            
            if found_steam_id:
                target_user_steam_ids.append(found_steam_id)
                logger.info(f"Force deals: Checking deals for {target_friendly_name}'s wishlist")
            else:
                available_names = ', '.join(current_family_members.values())
                return {"success": False, "message": f"Friendly name '{target_friendly_name}' not found. Available names: {available_names}"}
        else:
            target_user_steam_ids = list(current_family_members.keys())
            logger.info("Force deals: Checking deals for all family wishlists")

        # Collect wishlist games from the target user(s)
        global_wishlist = []
        for user_steam_id in target_user_steam_ids:
            user_name_for_log = current_family_members.get(user_steam_id, f"Unknown ({user_steam_id})")
            
            # Try to get cached wishlist first
            cached_wishlist = get_cached_wishlist(user_steam_id)
            if cached_wishlist is not None:
                logger.info(f"Force deals: Using cached wishlist for {user_name_for_log} ({len(cached_wishlist)} items)")
                for app_id in cached_wishlist:
                    # Ensure app_id is added with its interested users
                    if app_id not in [item[0] for item in global_wishlist]:
                        global_wishlist.append([app_id, [user_steam_id]])
                    else:
                        for item in global_wishlist:
                            if item[0] == app_id:
                                item[1].append(user_steam_id)
                                break
            else:
                # If not cached, fetch fresh wishlist data from API
                if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY == "YOUR_STEAMWORKS_API_KEY_HERE":
                    logger.warning(f"Force deals: Cannot fetch wishlist for {user_name_for_log} - Steam API key not configured")
                    continue
                
                wishlist_url = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?key={STEAMWORKS_API_KEY}&steamid={user_steam_id}"
                logger.info(f"Force deals: Fetching fresh wishlist from API for {user_name_for_log}")
                
                try:
                    await _rate_limit_steam_api()
                    wishlist_response = requests.get(wishlist_url, timeout=15)
                    if wishlist_response.text == "{\"success\":2}":
                        log_private_profile_detection(logger, user_name_for_log, user_steam_id, "wishlist")
                        continue

                    wishlist_json = await _handle_api_response(f"GetWishlist ({user_name_for_log})", wishlist_response)
                    if not wishlist_json: 
                        continue

                    wishlist_items = wishlist_json.get("response", {}).get("items", [])
                    if not wishlist_items:
                        logger.info(f"Force deals: No items found in {user_name_for_log}'s wishlist.")
                        continue

                    # Extract app IDs and add to global wishlist
                    user_wishlist_appids = []
                    for game_item in wishlist_items:
                        app_id = str(game_item.get("appid"))
                        if not app_id:
                            logger.warning(f"Force deals: Skipping wishlist item due to missing appid: {game_item}")
                            continue

                        user_wishlist_appids.append(app_id)
                        if app_id not in [item[0] for item in global_wishlist]:
                            global_wishlist.append([app_id, [user_steam_id]])
                        else:
                            # Add user to existing entry
                            for item in global_wishlist:
                                if item[0] == app_id:
                                    item[1].append(user_steam_id)
                                    break

                    # Cache the wishlist for 2 hours
                    cache_wishlist(user_steam_id, user_wishlist_appids, cache_hours=2)
                    logger.info(f"Force deals: Fetched and cached {len(user_wishlist_appids)} wishlist items for {user_name_for_log}")

                except Exception as e:
                    logger.error(f"Force deals: Error fetching wishlist for {user_name_for_log}: {e}")
                    continue
        
        if not global_wishlist:
            return {"success": False, "message": "No wishlist games found to check for deals. This could be due to private profiles or empty wishlists."}
        
        deals_found = []
        games_checked = 0
        max_games_to_check = 100  # Higher limit for force command
        total_games = min(len(global_wishlist), max_games_to_check)

        logger.info(f"Force deals: Checking {total_games} games for deals")

        for item in global_wishlist[:max_games_to_check]:
            app_id = item[0]
            interested_users = item[1]
            games_checked += 1
            
            try:
                # Get cached game details first
                cached_game = get_cached_game_details(app_id)
                if cached_game:
                    game_data = cached_game
                else:
                    # If not cached, fetch from API
                    await _rate_limit_steam_store_api()
                    game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
                    app_info_response = requests.get(game_url, timeout=10)
                    game_info_json = await _handle_api_response("AppDetails (Force Deals)", app_info_response)
                    if not game_info_json: continue
                    
                    game_data = game_info_json.get(str(app_id), {}).get("data")
                    if not game_data: continue
                    
                    # Cache the game details
                    cache_game_details(app_id, game_data, permanent=True)
                
                game_name = game_data.get("name", f"Unknown Game ({app_id})")
                # Handle both cached data (price_data) and fresh API data (price_overview)
                price_overview = game_data.get("price_overview") or game_data.get("price_data")
                
                if not price_overview:
                    logger.debug(f"Force deals: No price data found for {app_id} ({game_name})")
                    continue
                
                # Check if game is on sale
                discount_percent = price_overview.get("discount_percent", 0)
                current_price = price_overview.get("final_formatted", "N/A")
                original_price = price_overview.get("initial_formatted", current_price)
                
                # Get historical low price
                lowest_price = get_lowest_price(int(app_id))
                
                # Determine if this is a good deal (more lenient criteria for force command)
                is_good_deal = False
                deal_reason = ""
                
                if discount_percent >= 30:  # Lower threshold for force command
                    is_good_deal = True
                    deal_reason = f"🔥 **{discount_percent}% OFF**"
                elif discount_percent >= 15 and lowest_price != "N/A":
                    # Check if current price is close to historical low
                    try:
                        current_price_num = float(price_overview.get("final", 0)) / 100
                        lowest_price_num = float(lowest_price)
                        if current_price_num <= lowest_price_num * 1.2:  # Within 20% of historical low
                            is_good_deal = True
                            deal_reason = f"💎 **Near Historical Low** ({discount_percent}% off)"
                    except (ValueError, TypeError):
                        pass
                
                if is_good_deal:
                    user_names = [current_family_members.get(uid, f"Unknown") for uid in interested_users]
                    deal_info = {
                        'name': game_name,
                        'app_id': app_id,
                        'current_price': current_price,
                        'original_price': original_price,
                        'discount_percent': discount_percent,
                        'lowest_price': lowest_price,
                        'deal_reason': deal_reason,
                        'interested_users': user_names
                    }
                    deals_found.append(deal_info)
            
            except Exception as e:
                logger.warning(f"Force deals: Error checking deals for game {app_id}: {e}")
                continue
        
        # Format results
        if deals_found:
            target_info = f" for {target_friendly_name}" if target_friendly_name else ""
            message_parts = [f"🎯 **Current Deals Alert{target_info}** (found {len(deals_found)} deals from {games_checked} games checked):\n\n"]
            
            for deal in deals_found:  # Show all deals found
                message_parts.append(f"**{deal['name']}**\n")
                message_parts.append(f"{deal['deal_reason']}\n")
                message_parts.append(f"💰 {deal['current_price']}")
                if deal['discount_percent'] > 0:
                    message_parts.append(f" ~~{deal['original_price']}~~")
                if deal['lowest_price'] != "N/A":
                    message_parts.append(f" | Lowest ever: ${deal['lowest_price']}")
                message_parts.append(f"\n👥 Wanted by: {', '.join(deal['interested_users'][:3])}")
                if len(deal['interested_users']) > 3:
                    message_parts.append(f" +{len(deal['interested_users']) - 3} more")
                message_parts.append(f"\n🔗 https://store.steampowered.com/app/{deal['app_id']}\n\n")
            
            final_message = "".join(message_parts)
            logger.info(f"Force deals: Found {len(deals_found)} deals")
            return {"success": True, "message": final_message}
        else:
            logger.info(f"Force deals: No deals found among {games_checked} games")
            return {"success": True, "message": f"📊 **Force deals complete!** No significant deals found among {games_checked} games checked."}
        
    except Exception as e:
        logger.critical(f"Force deals: Critical error during force deals check: {e}", exc_info=True)
        return {"success": False, "message": f"Critical error during force deals: {e}"}
