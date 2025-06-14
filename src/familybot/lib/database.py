# In src/familybot/lib/database.py

import sqlite3
import os
import logging
from familybot.config import PROJECT_ROOT

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DATABASE_FILE = os.path.join(PROJECT_ROOT, 'bot_data.db')

def get_db_connection():
    """Establishes and returns a new SQLite database connection."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
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

        # Create 'itad_price_cache' table for ITAD price data (changes frequently)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS itad_price_cache (
                appid TEXT PRIMARY KEY,
                lowest_price TEXT,
                lowest_price_formatted TEXT,
                shop_name TEXT,
                cached_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        ''')
        logger.info("Database: 'itad_price_cache' table checked/created.")

        # --- NEW LOGIC for adding 'detected_at' to existing tables ---
        # 1. Check if the column exists
        cursor.execute("PRAGMA table_info(saved_games)")
        columns = [col[1] for col in cursor.fetchall()] # col[1] is the column name
        
        if 'detected_at' not in columns:
            logger.info("Database: 'detected_at' column not found in 'saved_games'. Attempting to add.")
            try:
                # Add the column as NULLable first (this is allowed in SQLite ALTER TABLE)
                cursor.execute("ALTER TABLE saved_games ADD COLUMN detected_at TEXT")
                logger.info("Database: Added 'detected_at' column as NULLable to 'saved_games' table.")
                
                # Update existing rows with the current timestamp
                cursor.execute("UPDATE saved_games SET detected_at = STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW') WHERE detected_at IS NULL")
                conn.commit() # Commit the update before setting NOT NULL
                logger.info("Database: Updated existing rows in 'saved_games' with timestamps.")

                # If you absolutely need it NOT NULL, you'd then try to make it NOT NULL.
                # However, SQLite doesn't easily convert NULLable to NOT NULL without a full table rebuild.
                # For this case, it's often sufficient to ensure future inserts always provide it,
                # and you've already populated existing ones.
                # If a true NOT NULL constraint is needed, a more complex migration (rename, create new, copy data) is required.
                # For simplicity here, we'll leave it as NULLable if added this way, and rely on INSERTs.
                
            except sqlite3.OperationalError as e:
                logger.error(f"Database: Failed to add/update 'detected_at' column: {e}")
            except Exception as e:
                logger.error(f"Database: Unexpected error during 'detected_at' column migration: {e}", exc_info=True)
        else:
            logger.debug("Database: 'detected_at' column already exists in 'saved_games'.")
        # --- END NEW LOGIC ---

        conn.commit() # Final commit
    except sqlite3.Error as e:
        logger.critical(f"Database initialization error: {e}")
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
            SELECT name, type, is_free, categories, price_data, permanent
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
                'price_data': json.loads(row['price_data']) if row['price_data'] else None
            }
        return None
    except Exception as e:
        logger.error(f"Error getting cached game details for {appid}: {e}")
        return None
    finally:
        if conn:
            conn.close()


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
        
        cursor.execute("""
            INSERT OR REPLACE INTO game_details_cache 
            (appid, name, type, is_free, categories, price_data, cached_at, expires_at, permanent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            appid,
            game_data.get('name'),
            game_data.get('type'),
            game_data.get('is_free', False),
            json.dumps(game_data.get('categories', [])),
            json.dumps(game_data.get('price_overview')) if game_data.get('price_overview') else None,
            now.isoformat() + 'Z',
            expires_at_str,
            1 if permanent else 0
        ))
        conn.commit()
        cache_type = "permanently" if permanent else f"for {cache_hours} hours"
        logger.debug(f"Cached game details for {appid} {cache_type}")
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
    """Get cached ITAD price data if not expired, returns None if not found or expired."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT lowest_price, lowest_price_formatted, shop_name 
            FROM itad_price_cache 
            WHERE appid = ? AND expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
        """, (appid,))
        row = cursor.fetchone()
        if row:
            return {
                'lowest_price': row['lowest_price'],
                'lowest_price_formatted': row['lowest_price_formatted'],
                'shop_name': row['shop_name']
            }
        return None
    except Exception as e:
        logger.error(f"Error getting cached ITAD price for {appid}: {e}")
        return None
    finally:
        if conn:
            conn.close()


def cache_itad_price(appid: str, price_data: dict, cache_hours: int = 6):
    """Cache ITAD price data for specified hours (prices change frequently)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        from datetime import datetime, timedelta
        
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=cache_hours)
        
        cursor.execute("""
            INSERT OR REPLACE INTO itad_price_cache 
            (appid, lowest_price, lowest_price_formatted, shop_name, cached_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            appid,
            price_data.get('lowest_price'),
            price_data.get('lowest_price_formatted'),
            price_data.get('shop_name'),
            now.isoformat() + 'Z',
            expires_at.isoformat() + 'Z'
        ))
        conn.commit()
        logger.debug(f"Cached ITAD price for {appid} for {cache_hours} hours")
    except Exception as e:
        logger.error(f"Error caching ITAD price for {appid}: {e}")
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


def cache_wishlist(steam_id: str, appids: list, cache_hours: int = 2):
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
