# In src/familybot/lib/database.py

import logging
import os
import sqlite3
from typing import Optional  # Import Optional

from familybot.config import PROJECT_ROOT

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DATABASE_FILE = os.path.join(PROJECT_ROOT, 'bot_data.db')

def get_db_connection():
    """Establishes and returns a new SQLite database connection."""
    try:
        # Allow the connection to be used across multiple threads, necessary for FastAPI.
        conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.critical(f"Database connection error: {e}")
        raise

def init_db():
    """Initializes the database schema by creating tables if they don't exist
       and adding new columns if they are missing (for schema evolution)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Create 'users' table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                discord_id TEXT PRIMARY KEY,
                steam_id TEXT NOT NULL UNIQUE
            )
        ''')
        logger.info("Database: 'users' table checked/created.")

        # Create 'saved_games' table with detected_at timestamp if it doesn't exist
        # The DEFAULT (STRFTIME...) works perfectly when creating a new table.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_games (
                appid TEXT PRIMARY KEY,
                detected_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
            )
        ''')
        logger.info("Database: 'saved_games' table checked/created.")

        # Create 'family_members' table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS family_members (
                steam_id TEXT PRIMARY KEY,
                friendly_name TEXT NOT NULL,
                discord_id TEXT
            )
        ''')
        logger.info("Database: 'family_members' table checked/created.")

        # Create 'game_details_cache' table for Steam Store API responses
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_details_cache (
                appid TEXT PRIMARY KEY,
                name TEXT,
                type TEXT,
                is_free BOOLEAN,
                categories TEXT,
                price_data TEXT,
                is_multiplayer BOOLEAN DEFAULT 0,
                is_coop BOOLEAN DEFAULT 0,
                is_family_shared BOOLEAN DEFAULT 0,
                cached_at TEXT NOT NULL,
                expires_at TEXT,
                permanent BOOLEAN DEFAULT 1
            )
        ''')
        logger.info("Database: 'game_details_cache' table checked/created.")

        # Create 'user_games_cache' table for Steam GetOwnedGames responses
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_games_cache (
                steam_id TEXT,
                appid TEXT,
                cached_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                PRIMARY KEY (steam_id, appid)
            )
        ''')
        logger.info("Database: 'user_games_cache' table checked/created.")

        # Create 'wishlist_cache' table for Steam wishlist data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wishlist_cache (
                steam_id TEXT,
                appid TEXT,
                cached_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                PRIMARY KEY (steam_id, appid)
            )
        ''')
        logger.info("Database: 'wishlist_cache' table checked/created.")

        # Create 'discord_users_cache' table for Discord user info
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS discord_users_cache (
                discord_id TEXT PRIMARY KEY,
                username TEXT,
                cached_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        ''')
        logger.info("Database: 'discord_users_cache' table checked/created.")

        # Create 'family_library_cache' table for family shared library
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS family_library_cache (
                appid TEXT PRIMARY KEY,
                owner_steamids TEXT,
                exclude_reason INTEGER,
                cached_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        ''')
        logger.info("Database: 'family_library_cache' table checked/created.")

        # Create 'itad_price_cache' table for ITAD price data (historical prices are permanent)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS itad_price_cache (
                appid TEXT PRIMARY KEY,
                lowest_price TEXT,
                lowest_price_formatted TEXT,
                shop_name TEXT,
                cached_at TEXT NOT NULL,
                expires_at TEXT,
                permanent BOOLEAN DEFAULT 1
            )
        ''')
        logger.info("Database: 'itad_price_cache' table checked/created.")

        # --- MIGRATION LOGIC for adding columns to existing tables ---

        # 1. Check and add 'detected_at' to saved_games
        cursor.execute("PRAGMA table_info(saved_games)")
        saved_games_columns = [col[1] for col in cursor.fetchall()]

        if 'detected_at' not in saved_games_columns:
            logger.info("Database: 'detected_at' column not found in 'saved_games'. Attempting to add.")
            try:
                cursor.execute("ALTER TABLE saved_games ADD COLUMN detected_at TEXT")
                logger.info("Database: Added 'detected_at' column to 'saved_games' table.")

                cursor.execute("UPDATE saved_games SET detected_at = STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW') WHERE detected_at IS NULL")
                conn.commit()
                logger.info("Database: Updated existing rows in 'saved_games' with timestamps.")
            except sqlite3.OperationalError as e:
                logger.error(f"Database: Failed to add/update 'detected_at' column: {e}")
            except Exception as e:
                logger.error(f"Database: Unexpected error during 'detected_at' column migration: {e}", exc_info=True)
        else:
            logger.debug("Database: 'detected_at' column already exists in 'saved_games'.")

        # 2. Check and add new columns to game_details_cache
        cursor.execute("PRAGMA table_info(game_details_cache)")
        game_cache_columns = [col[1] for col in cursor.fetchall()]

        new_columns = [
            ('is_multiplayer', 'BOOLEAN DEFAULT 0'),
            ('is_coop', 'BOOLEAN DEFAULT 0'),
            ('is_family_shared', 'BOOLEAN DEFAULT 0')
        ]

        for column_name, column_def in new_columns:
            if column_name not in game_cache_columns:
                logger.info(f"Database: '{column_name}' column not found in 'game_details_cache'. Attempting to add.")
                try:
                    cursor.execute(f"ALTER TABLE game_details_cache ADD COLUMN {column_name} {column_def}")
                    logger.info(f"Database: Added '{column_name}' column to 'game_details_cache' table.")
                except sqlite3.OperationalError as e:
                    logger.error(f"Database: Failed to add '{column_name}' column: {e}")
                except Exception as e:
                    logger.error(f"Database: Unexpected error during '{column_name}' column migration: {e}", exc_info=True)
            else:
                logger.debug(f"Database: '{column_name}' column already exists in 'game_details_cache'.")

        # 3. Check and add 'permanent' column to itad_price_cache
        cursor.execute("PRAGMA table_info(itad_price_cache)")
        itad_cache_columns = [col[1] for col in cursor.fetchall()]

        if 'permanent' not in itad_cache_columns:
            logger.info("Database: 'permanent' column not found in 'itad_price_cache'. Attempting to add.")
            try:
                cursor.execute("ALTER TABLE itad_price_cache ADD COLUMN permanent BOOLEAN DEFAULT 1")
                logger.info("Database: Added 'permanent' column to 'itad_price_cache' table.")

                # Update existing rows to have permanent=1 (historical prices are permanent by default)
                cursor.execute("UPDATE itad_price_cache SET permanent = 1 WHERE permanent IS NULL")
                conn.commit()
                logger.info("Database: Updated existing ITAD price cache entries to permanent=1.")
            except sqlite3.OperationalError as e:
                logger.error(f"Database: Failed to add 'permanent' column to itad_price_cache: {e}")
            except Exception as e:
                logger.error(f"Database: Unexpected error during 'permanent' column migration: {e}", exc_info=True)
        else:
            logger.debug("Database: 'permanent' column already exists in 'itad_price_cache'.")

        # --- END MIGRATION LOGIC ---

        conn.commit() # Final commit
    except sqlite3.Error as e:
        logger.critical(f"Database initialization error: {e}")
    finally:
        if conn:
            conn.close()

def sync_family_members_from_config():
    """Synchronizes family members from config.yml into the family_members database table.
    This ensures that members defined in the configuration are always present in the DB."""
    conn = None
    try:
        from familybot.config import FAMILY_USER_DICT
        conn = get_db_connection()
        cursor = conn.cursor()

        for steam_id, friendly_name in FAMILY_USER_DICT.items():
            # Check if the member already exists
            cursor.execute("SELECT friendly_name FROM family_members WHERE steam_id = ?", (steam_id,))
            existing_member = cursor.fetchone()

            if existing_member:
                # Update friendly_name if it has changed
                if existing_member['friendly_name'] != friendly_name:
                    cursor.execute(
                        "UPDATE family_members SET friendly_name = ? WHERE steam_id = ?",
                        (friendly_name, steam_id)
                    )
                    logger.info(f"Updated friendly name for Steam ID {steam_id} to '{friendly_name}'.")
            else:
                # Insert new member
                cursor.execute(
                    "INSERT INTO family_members (steam_id, friendly_name, discord_id) VALUES (?, ?, ?)",
                    (steam_id, friendly_name, None) # Discord ID can be added later
                )
                logger.info(f"Added new family member: '{friendly_name}' (Steam ID: {steam_id}).")

        conn.commit()
        logger.info("Family members synchronized from config.yml to database.")
    except Exception as e:
        logger.error(f"Error synchronizing family members from config: {e}")
    finally:
        if conn:
            conn.close()


# === CACHE HELPER FUNCTIONS ===

def get_cached_game_details(appid: str):
    """Get cached game details. Returns None if not found. Permanent cache never expires."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, type, is_free, categories, price_data, permanent,
                   is_multiplayer, is_coop, is_family_shared
            FROM game_details_cache
            WHERE appid = ? AND (permanent = 1 OR expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
        """, (appid,))
        row = cursor.fetchone()
        if row:
            import json
            return {
                'name': row['name'],
                'type': row['type'],
                'is_free': bool(row['is_free']),
                'categories': json.loads(row['categories']) if row['categories'] else [],
                'price_data': json.loads(row['price_data']) if row['price_data'] else None,
                'is_multiplayer': bool(row['is_multiplayer']) if row['is_multiplayer'] is not None else False,
                'is_coop': bool(row['is_coop']) if row['is_coop'] is not None else False,
                'is_family_shared': bool(row['is_family_shared']) if row['is_family_shared'] is not None else False
            }
        return None
    except Exception as e:
        logger.error(f"Error getting cached game details for {appid}: {e}")
        return None
    finally:
        if conn:
            conn.close()


def _analyze_game_categories(categories: list) -> tuple[bool, bool, bool]:
    """Analyze Steam categories to determine multiplayer, co-op, and family sharing status."""
    is_multiplayer = False
    is_coop = False
    is_family_shared = False

    for cat in categories:
        cat_id = cat.get("id")
        if cat_id == 1:  # Multi-player
            is_multiplayer = True
        elif cat_id == 36:  # Online Multi-Player
            is_multiplayer = True
        elif cat_id == 38:  # Online Co-op
            is_multiplayer = True
            is_coop = True
        elif cat_id == 62:  # Family Sharing
            is_family_shared = True

    return is_multiplayer, is_coop, is_family_shared


def cache_game_details(appid: str, game_data: dict, permanent: bool = True, cache_hours: int | None = None):
    """Cache game details permanently by default, or for specified hours if permanent=False."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        import json
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        expires_at = None

        if not permanent and cache_hours:
            expires_at = now + timedelta(hours=cache_hours)
            expires_at_str = expires_at.isoformat() + 'Z'
        else:
            expires_at_str = None  # NULL for permanent cache

        # Analyze categories to determine multiplayer/co-op/family sharing status
        categories = game_data.get('categories', [])
        is_multiplayer, is_coop, is_family_shared = _analyze_game_categories(categories)

        cursor.execute("""
            INSERT OR REPLACE INTO game_details_cache
            (appid, name, type, is_free, categories, price_data, is_multiplayer, is_coop, is_family_shared, cached_at, expires_at, permanent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            appid,
            game_data.get('name'),
            game_data.get('type'),
            game_data.get('is_free', False),
            json.dumps(categories),
            json.dumps(game_data.get('price_overview')) if game_data.get('price_overview') else None,
            1 if is_multiplayer else 0,
            1 if is_coop else 0,
            1 if is_family_shared else 0,
            now.isoformat() + 'Z',
            expires_at_str,
            1 if permanent else 0
        ))
        conn.commit()
        cache_type = "permanently" if permanent else f"for {cache_hours} hours"
        logger.debug(f"Cached game details for {appid} {cache_type} (MP:{is_multiplayer}, Coop:{is_coop}, FS:{is_family_shared})")
    except Exception as e:
        logger.error(f"Error caching game details for {appid}: {e}")
    finally:
        if conn:
            conn.close()


def force_update_game_cache(appid: str, game_data: dict):
    """Force update cached game details even if they already exist."""
    cache_game_details(appid, game_data, permanent=True)
    logger.info(f"Force updated cache for game {appid}")


def get_cached_user_games(steam_id: str):
    """Get cached user games if not expired, returns None if not found or expired."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT appid FROM user_games_cache
            WHERE steam_id = ? AND expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
        """, (steam_id,))
        rows = cursor.fetchall()
        if rows:
            return [row['appid'] for row in rows]
        return None
    except Exception as e:
        logger.error(f"Error getting cached user games for {steam_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()


def cache_user_games(steam_id: str, appids: list, cache_hours: int = 6):
    """Cache user's game list for specified hours."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        expires_at = now + timedelta(hours=cache_hours)

        # Clear existing cache for this user
        cursor.execute("DELETE FROM user_games_cache WHERE steam_id = ?", (steam_id,))

        # Insert new cache entries
        cache_entries = [
            (steam_id, str(appid), now.isoformat() + 'Z', expires_at.isoformat() + 'Z')
            for appid in appids
        ]
        cursor.executemany("""
            INSERT INTO user_games_cache (steam_id, appid, cached_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, cache_entries)
        conn.commit()
        logger.debug(f"Cached {len(appids)} games for user {steam_id}")
    except Exception as e:
        logger.error(f"Error caching user games for {steam_id}: {e}")
    finally:
        if conn:
            conn.close()


def get_cached_discord_user(discord_id: str):
    """Get cached Discord user info if not expired, returns None if not found or expired."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT username FROM discord_users_cache
            WHERE discord_id = ? AND expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
        """, (discord_id,))
        row = cursor.fetchone()
        if row:
            return row['username']
        return None
    except Exception as e:
        logger.error(f"Error getting cached Discord user for {discord_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()


def cache_discord_user(discord_id: str, username: str, cache_hours: int = 1):
    """Cache Discord user info for specified hours."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        expires_at = now + timedelta(hours=cache_hours)

        cursor.execute("""
            INSERT OR REPLACE INTO discord_users_cache
            (discord_id, username, cached_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, (discord_id, username, now.isoformat() + 'Z', expires_at.isoformat() + 'Z'))
        conn.commit()
        logger.debug(f"Cached Discord user {discord_id}: {username}")
    except Exception as e:
        logger.error(f"Error caching Discord user {discord_id}: {e}")
    finally:
        if conn:
            conn.close()


def get_cached_itad_price(appid: str):
    """Get cached ITAD price data. Returns None if not found. Permanent cache never expires."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT lowest_price, lowest_price_formatted, shop_name, permanent
            FROM itad_price_cache
            WHERE appid = ? AND (permanent = 1 OR expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
        """, (appid,))
        row = cursor.fetchone()
        if row:
            return {
                'lowest_price': row['lowest_price'],
                'lowest_price_formatted': row['lowest_price_formatted'],
                'shop_name': row['shop_name'],
                'permanent': bool(row['permanent']) if row['permanent'] is not None else False
            }
        return None
    except Exception as e:
        logger.error(f"Error getting cached ITAD price for {appid}: {e}")
        return None
    finally:
        if conn:
            conn.close()


def cache_itad_price(appid: str, price_data: dict, permanent: bool = False, cache_hours: int = 6):
    """Cache ITAD price data. If permanent=True, cache never expires (expires_at=NULL, permanent=1)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        if permanent:
            expires_at_str = None
            permanent_val = 1
        else:
            expires_at = now + timedelta(hours=cache_hours)
            expires_at_str = expires_at.isoformat() + 'Z'
            permanent_val = 0

        cursor.execute("""
            INSERT OR REPLACE INTO itad_price_cache
            (appid, lowest_price, lowest_price_formatted, shop_name, cached_at, expires_at, permanent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            appid,
            price_data.get('lowest_price'),
            price_data.get('lowest_price_formatted'),
            price_data.get('shop_name'),
            now.isoformat() + 'Z',
            expires_at_str,
            permanent_val
        ))
        conn.commit()
        cache_type = "permanently" if permanent else f"for {cache_hours} hours"
        logger.debug(f"Cached ITAD price for {appid} {cache_type}")
    except Exception as e:
        logger.error(f"Error caching ITAD price for {appid}: {e}")
    finally:
        if conn:
            conn.close()

def cache_itad_price_enhanced(appid: str, price_data: dict, lookup_method: str = 'appid', steam_game_name: Optional[str] = None, permanent: bool = True, cache_hours: int = 6):
    """Enhanced ITAD price caching with lookup method tracking for Phase 2."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        if permanent:
            expires_at_str = None
            permanent_val = 1
        else:
            expires_at = now + timedelta(hours=cache_hours)
            expires_at_str = expires_at.isoformat() + 'Z'
            permanent_val = 0

        cursor.execute("""
            INSERT OR REPLACE INTO itad_price_cache
            (appid, lowest_price, lowest_price_formatted, shop_name, lookup_method, steam_game_name, cached_at, expires_at, permanent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            appid,
            price_data.get('lowest_price'),
            price_data.get('lowest_price_formatted'),
            price_data.get('shop_name'),
            lookup_method,
            steam_game_name,
            now.isoformat() + 'Z',
            expires_at_str,
            permanent_val
        ))
        conn.commit()
        cache_type = "permanently" if permanent else f"for {cache_hours} hours"
        logger.debug(f"Cached ITAD price for {appid} {cache_type} (method: {lookup_method}, name: {steam_game_name})")
    except Exception as e:
        logger.error(f"Error caching enhanced ITAD price for {appid}: {e}")
    finally:
        if conn:
            conn.close()


def get_cached_wishlist(steam_id: str):
    """Get cached wishlist data if not expired, returns None if not found or expired."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT appid FROM wishlist_cache
            WHERE steam_id = ? AND expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
        """, (steam_id,))
        rows = cursor.fetchall()
        if rows:
            return [row['appid'] for row in rows]
        return None
    except Exception as e:
        logger.error(f"Error getting cached wishlist for {steam_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()


def cache_wishlist(steam_id: str, appids: list, cache_hours: int = 168):
    """Cache user's wishlist for specified hours (wishlists change moderately)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        expires_at = now + timedelta(hours=cache_hours)

        # Clear existing cache for this user
        cursor.execute("DELETE FROM wishlist_cache WHERE steam_id = ?", (steam_id,))

        # Insert new cache entries
        cache_entries = [
            (steam_id, str(appid), now.isoformat() + 'Z', expires_at.isoformat() + 'Z')
            for appid in appids
        ]
        cursor.executemany("""
            INSERT INTO wishlist_cache (steam_id, appid, cached_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, cache_entries)
        conn.commit()
        logger.debug(f"Cached {len(appids)} wishlist items for user {steam_id}")
    except Exception as e:
        logger.error(f"Error caching wishlist for {steam_id}: {e}")
    finally:
        if conn:
            conn.close()


def get_cached_family_library():
    """Get cached family library data if not expired, returns None if not found or expired."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT appid, owner_steamids, exclude_reason FROM family_library_cache
            WHERE expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
        """, ())
        rows = cursor.fetchall()
        if rows:
            import json
            family_apps = []
            for row in rows:
                family_apps.append({
                    'appid': int(row['appid']),
                    'owner_steamids': json.loads(row['owner_steamids']) if row['owner_steamids'] else [],
                    'exclude_reason': row['exclude_reason']
                })
            return family_apps
        return None
    except Exception as e:
        logger.error(f"Error getting cached family library: {e}")
        return None
    finally:
        if conn:
            conn.close()


def cache_family_library(family_apps: list, cache_minutes: int = 30):
    """Cache family library data for specified minutes (updates frequently)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        import json
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=cache_minutes)

        # Clear existing cache
        cursor.execute("DELETE FROM family_library_cache")

        # Insert new cache entries
        cache_entries = []
        for app in family_apps:
            cache_entries.append((
                str(app.get('appid')),
                json.dumps(app.get('owner_steamids', [])),
                app.get('exclude_reason'),
                now.isoformat() + 'Z',
                expires_at.isoformat() + 'Z'
            ))

        cursor.executemany("""
            INSERT INTO family_library_cache (appid, owner_steamids, exclude_reason, cached_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, cache_entries)
        conn.commit()
        logger.debug(f"Cached {len(family_apps)} family library apps for {cache_minutes} minutes")
    except Exception as e:
        logger.error(f"Error caching family library: {e}")
    finally:
        if conn:
            conn.close()

def purge_wishlist_cache():
    """Purge all entries from the wishlist_cache table."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM wishlist_cache")
        conn.commit()
        logger.info("Purged all entries from wishlist_cache.")
    except Exception as e:
        logger.error(f"Error purging wishlist_cache: {e}")
    finally:
        if conn:
            conn.close()

def purge_family_library_cache():
    """Purge all entries from the family_library_cache table."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM family_library_cache")
        conn.commit()
        logger.info("Purged all entries from family_library_cache.")
    except Exception as e:
        logger.error(f"Error purging family_library_cache: {e}")
    finally:
        if conn:
            conn.close()

def get_steam_id_from_friendly_name(friendly_name: str) -> Optional[str]:
    """Retrieves the SteamID associated with a given friendly name from the family_members table."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT steam_id FROM family_members WHERE friendly_name = ?", (friendly_name,))
        result = cursor.fetchone()
        if result:
            return result['steam_id']
        return None
    except Exception as e:
        logger.error(f"Error retrieving SteamID for friendly name {friendly_name}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_steam_id_from_discord_id(discord_id: str) -> Optional[str]:
    """Retrieves the SteamID associated with a given Discord ID from the users table."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT steam_id FROM users WHERE discord_id = ?", (discord_id,))
        result = cursor.fetchone()
        if result:
            return result['steam_id']
        return None
    except Exception as e:
        logger.error(f"Error retrieving SteamID for Discord ID {discord_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def cache_game_details_with_source(app_id: str, game_data: dict, source: str):
    """Enhanced cache_game_details with source tracking."""
    # Call existing cache_game_details but with source parameter
    cache_game_details(app_id, game_data, permanent=True)

    # Update the price_source field
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE game_details_cache SET price_source = ? WHERE appid = ?",
            (source, app_id)
        )
        conn.commit()
        logger.debug(f"Updated price source for {app_id}: {source}")
    except Exception as e:
        logger.error(f"Failed to update price source for {app_id}: {e}")
    finally:
        if conn:
            conn.close()

def cleanup_expired_cache():
    """Remove expired cache entries from all cache tables."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        tables = ['game_details_cache', 'user_games_cache', 'wishlist_cache',
                 'discord_users_cache', 'family_library_cache', 'itad_price_cache']

        total_deleted = 0
        for table in tables:
            cursor.execute(f"""
                DELETE FROM {table}
                WHERE expires_at <= STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
            """)
            deleted = cursor.rowcount
            total_deleted += deleted
            if deleted > 0:
                logger.debug(f"Cleaned up {deleted} expired entries from {table}")

        conn.commit()
        if total_deleted > 0:
            logger.info(f"Cache cleanup: removed {total_deleted} expired entries")
    except Exception as e:
        logger.error(f"Error during cache cleanup: {e}")
    finally:
        if conn:
            conn.close()

def migrate_database_phase1():
    """Add price_source column to game_details_cache table."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(game_details_cache)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'price_source' not in columns:
            cursor.execute("ALTER TABLE game_details_cache ADD COLUMN price_source TEXT DEFAULT 'store_api'")

            # Update existing entries to have 'store_api' as source
            cursor.execute("UPDATE game_details_cache SET price_source = 'store_api' WHERE price_source IS NULL")

            conn.commit()
            logger.info("Phase 1 database migration completed: Added price_source column")
        else:
            logger.info("Phase 1 database migration skipped: price_source column already exists")

    except Exception as e:
        logger.error(f"Phase 1 database migration failed: {e}")
        raise
    finally:
        if conn:
            conn.close()

def migrate_database_phase2():
    """Add ITAD lookup method tracking columns to itad_price_cache table."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(itad_price_cache)")
        columns = [col[1] for col in cursor.fetchall()]

        migrations_needed = []
        if 'lookup_method' not in columns:
            migrations_needed.append(('lookup_method', "TEXT DEFAULT 'appid'"))
        if 'steam_game_name' not in columns:
            migrations_needed.append(('steam_game_name', "TEXT"))

        for column_name, column_def in migrations_needed:
            cursor.execute(f"ALTER TABLE itad_price_cache ADD COLUMN {column_name} {column_def}")
            logger.info(f"Phase 2 database migration: Added {column_name} column to itad_price_cache")

        if migrations_needed:
            # Update existing entries to have 'appid' as default lookup method
            cursor.execute("UPDATE itad_price_cache SET lookup_method = 'appid' WHERE lookup_method IS NULL")
            conn.commit()
            logger.info("Phase 2 database migration completed: Added ITAD lookup method tracking columns")
        else:
            logger.info("Phase 2 database migration skipped: All columns already exist")

    except Exception as e:
        logger.error(f"Phase 2 database migration failed: {e}")
        raise
    finally:
        if conn:
            conn.close()
