# In src/familybot/lib/database.py

import contextlib
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager

from familybot.config import (
    FAMILY_LIBRARY_CACHE_TTL,
    PROJECT_ROOT,
)

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

DATABASE_FILE = os.path.join(PROJECT_ROOT, "bot_data.db")

# --- Connection pool: single connection per thread with write serialization ---
_local = threading.local()
_write_lock = threading.Lock()


def get_db_connection():
    """Returns a thread-local SQLite connection, creating one if needed.

    Uses a single connection per thread to avoid repeated setup overhead.
    Writes are serialized via _write_lock to prevent concurrent write corruption.
    """
    if not hasattr(_local, "conn") or _local.conn is None:
        try:
            conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            _local.conn = conn
        except sqlite3.Error as e:
            logger.critical(f"Database connection error: {e}")
            raise
    else:
        # Check if the existing connection is still usable (not closed)
        try:
            _local.conn.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            # Connection was closed, create a new one
            try:
                conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                _local.conn = conn
            except sqlite3.Error as e:
                logger.critical(f"Database connection error: {e}")
                raise
    return _local.conn


@contextmanager
def get_write_connection():
    """Context manager that provides a connection with write lock held.

    Usage:
        with get_write_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT ...")
            conn.commit()

    If an exception is raised inside the with-block, the transaction is
    automatically rolled back to prevent leaving an open transaction on
    the reused thread-local connection.
    """
    conn = get_db_connection()
    with _write_lock:
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise


def close_db_connection():
    """Close the thread-local database connection if it exists."""
    if hasattr(_local, "conn") and _local.conn is not None:
        with contextlib.suppress(sqlite3.Error):
            _local.conn.close()
        _local.conn = None


def init_db():
    """Initializes the database schema by creating tables if they don't exist
    and adding new columns if they are missing (for schema evolution)."""
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()

            # Create 'users' table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    discord_id TEXT PRIMARY KEY,
                    steam_id TEXT NOT NULL UNIQUE
                )
            """)
            logger.info("Database: 'users' table checked/created.")

            # Create 'saved_games' table with detected_at timestamp if it doesn't exist
            # The DEFAULT (STRFTIME...) works perfectly when creating a new table.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS saved_games (
                    appid TEXT PRIMARY KEY,
                    detected_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
                )
            """)
            logger.info("Database: 'saved_games' table checked/created.")

            # Create 'family_members' table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS family_members (
                    steam_id TEXT PRIMARY KEY,
                    friendly_name TEXT NOT NULL,
                    discord_id TEXT
                )
            """)
            logger.info("Database: 'family_members' table checked/created.")

            # Create 'game_details_cache' table for Steam Store API responses
            cursor.execute("""
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
                    permanent BOOLEAN DEFAULT 1,
                    price_source TEXT DEFAULT 'store_api'
                )
            """)
            logger.info("Database: 'game_details_cache' table checked/created.")

            # Create 'user_games_cache' table for Steam GetOwnedGames responses
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_games_cache (
                    steam_id TEXT,
                    appid TEXT,
                    cached_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    PRIMARY KEY (steam_id, appid)
                )
            """)
            logger.info("Database: 'user_games_cache' table checked/created.")

            # Create 'wishlist_cache' table for Steam wishlist data
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wishlist_cache (
                    steam_id TEXT,
                    appid TEXT,
                    cached_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    PRIMARY KEY (steam_id, appid)
                )
            """)
            logger.info("Database: 'wishlist_cache' table checked/created.")

            # Create 'discord_users_cache' table for Discord user info
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS discord_users_cache (
                    discord_id TEXT PRIMARY KEY,
                    username TEXT,
                    cached_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            logger.info("Database: 'discord_users_cache' table checked/created.")

            # Create 'family_library_cache' table for family shared library
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS family_library_cache (
                    appid TEXT PRIMARY KEY,
                    owner_steamids TEXT,
                    exclude_reason INTEGER,
                    cached_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            logger.info("Database: 'family_library_cache' table checked/created.")

            # Create 'itad_price_cache' table for ITAD price data (historical prices are permanent)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS itad_price_cache (
                    appid TEXT PRIMARY KEY,
                    lowest_price TEXT,
                    lowest_price_formatted TEXT,
                    shop_name TEXT,
                    cached_at TEXT NOT NULL,
                    expires_at TEXT,
                    permanent BOOLEAN DEFAULT 1,
                    lookup_method TEXT DEFAULT 'appid',
                    steam_game_name TEXT
                )
            """)
            logger.info("Database: 'itad_price_cache' table checked/created.")

            # Create 'migrations' table for tracking applied migrations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    name TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
                )
            """)
            logger.info("Database: 'migrations' table checked/created.")

            # --- DECLARATIVE MIGRATIONS for adding columns to existing tables ---

            # List of (table_name, column_name, column_definition, default_value_for_update)
            # default_value_for_update is used to populate existing rows if not NULL.
            COLUMN_MIGRATIONS = [
                (
                    "saved_games",
                    "detected_at",
                    "TEXT",
                    "STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')",
                ),
                ("game_details_cache", "is_multiplayer", "BOOLEAN DEFAULT 0", "0"),
                ("game_details_cache", "is_coop", "BOOLEAN DEFAULT 0", "0"),
                ("game_details_cache", "is_family_shared", "BOOLEAN DEFAULT 0", "0"),
                (
                    "game_details_cache",
                    "price_source",
                    "TEXT DEFAULT 'store_api'",
                    "'store_api'",
                ),
                ("itad_price_cache", "permanent", "BOOLEAN DEFAULT 1", "1"),
                (
                    "itad_price_cache",
                    "lookup_method",
                    "TEXT DEFAULT 'appid'",
                    "'appid'",
                ),
                ("itad_price_cache", "steam_game_name", "TEXT", None),
            ]

            def _run_column_migrations(cursor: sqlite3.Cursor):
                for table, column, definition, update_val in COLUMN_MIGRATIONS:
                    cursor.execute(f"PRAGMA table_info({table})")
                    columns = [col[1] for col in cursor.fetchall()]

                    if column not in columns:
                        logger.info(
                            f"Database: Adding column '{column}' to table '{table}'."
                        )
                        try:
                            cursor.execute(
                                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                            )
                            if update_val is not None:
                                cursor.execute(
                                    f"UPDATE {table} SET {column} = {update_val} WHERE {column} IS NULL"
                                )
                            logger.info(
                                f"Database: Successfully added '{column}' to '{table}'."
                            )
                        except sqlite3.OperationalError as e:
                            logger.error(
                                f"Database: Failed to add '{column}' to '{table}': {e}"
                            )
                            raise RuntimeError(
                                f"Database migration failed: unable to add column '{column}' to table '{table}'. "
                                f"Aborting initialization to prevent partial schema migration."
                            ) from e

            _run_column_migrations(cursor)

            # --- END MIGRATIONS ---

            conn.commit()  # Final commit
    except sqlite3.Error as e:
        logger.critical(f"Database initialization error: {e}")


def _parse_family_config_entry(value) -> tuple[str, str | None]:
    """Parse a family config entry value into (friendly_name, discord_id).

    Supports two config formats:
    - Old format (flat string): "Friendly Name" -> ("Friendly Name", None)
    - New format (dict): {"name": "Friendly Name", "discord_id": 123} -> ("Friendly Name", 123)
    """
    if isinstance(value, str):
        return value, None
    discord_id = value.get("discord_id")
    return value["name"], str(discord_id) if discord_id is not None else None


def sync_family_members_from_config():
    """Synchronizes family members from config.yml into the family_members database table.
    This ensures that members defined in the configuration are always present in the DB.

    Supports two config formats:
    - Old format (flat string): "steam_id": "Friendly Name"
    - New format (dict): "steam_id": {"name": "Friendly Name", "discord_id": 123456789}

    When using the legacy string format, preserves any existing discord_id from the database
    rather than clobbering it to NULL.
    """
    try:
        from familybot.config import FAMILY_USER_DICT

        with get_write_connection() as conn:
            cursor = conn.cursor()

            for steam_id, value in FAMILY_USER_DICT.items():
                friendly_name, discord_id = _parse_family_config_entry(value)

                # For legacy string format (discord_id is None), preserve existing discord_id
                if discord_id is None:
                    cursor.execute(
                        "SELECT discord_id FROM family_members WHERE steam_id = ?",
                        (steam_id,),
                    )
                    existing = cursor.fetchone()
                    if existing and existing["discord_id"]:
                        discord_id = existing["discord_id"]

                cursor.execute(
                    "INSERT OR REPLACE INTO family_members (steam_id, friendly_name, discord_id) VALUES (?, ?, ?)",
                    (steam_id, friendly_name, discord_id),
                )
                logger.debug(
                    "Synced family member: '%s' (Steam ID: %s, Discord ID: %s).",
                    friendly_name,
                    steam_id,
                    discord_id,
                )

            conn.commit()
            logger.info("Family members synchronized from config.yml to database.")
    except Exception as e:
        logger.error(f"Error synchronizing family members from config: {e}")


# === CACHE HELPER FUNCTIONS ===


def get_cached_discord_user(discord_id: str):
    """Get cached Discord user info if not expired, returns None if not found or expired."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT username FROM discord_users_cache
            WHERE discord_id = ? AND expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
        """,
            (discord_id,),
        )
        row = cursor.fetchone()
        if row:
            return row["username"]
        return None
    except Exception as e:
        logger.error(f"Error getting cached Discord user for {discord_id}: {e}")
        return None


def cache_discord_user(discord_id: str, username: str, cache_hours: int = 1):
    """Cache Discord user info for specified hours."""
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()
            from datetime import datetime, timedelta, timezone

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=cache_hours)

            cursor.execute(
                """
                INSERT OR REPLACE INTO discord_users_cache
                (discord_id, username, cached_at, expires_at)
                VALUES (?, ?, ?, ?)
            """,
                (
                    discord_id,
                    username,
                    now.isoformat().replace("+00:00", "Z"),
                    expires_at.isoformat().replace("+00:00", "Z"),
                ),
            )
            conn.commit()
            logger.debug(f"Cached Discord user {discord_id}: {username}")
    except Exception as e:
        logger.error(f"Error caching Discord user {discord_id}: {e}")


def get_cached_family_library():
    """Get cached family library data if not expired, returns None if not found or expired."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT appid, owner_steamids, exclude_reason FROM family_library_cache
            WHERE expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
        """,
            (),
        )
        rows = cursor.fetchall()
        if rows:
            import json

            family_apps = []
            for row in rows:
                family_apps.append(
                    {
                        "appid": int(row["appid"]),
                        "owner_steamids": json.loads(row["owner_steamids"])
                        if row["owner_steamids"]
                        else [],
                        "exclude_reason": row["exclude_reason"],
                    }
                )
            return family_apps
        return None
    except Exception as e:
        logger.error(f"Error getting cached family library: {e}")
        return None


def cache_family_library(
    family_apps: list, cache_hours: int = FAMILY_LIBRARY_CACHE_TTL
):
    """Cache family library data for specified hours (updates infrequently)."""
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()
            import json
            from datetime import datetime, timedelta, timezone

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=cache_hours)

            # Clear existing cache
            cursor.execute("DELETE FROM family_library_cache")

            # Insert new cache entries
            cache_entries = []
            for app in family_apps:
                cache_entries.append(
                    (
                        str(app.get("appid")),
                        json.dumps(app.get("owner_steamids", [])),
                        app.get("exclude_reason"),
                        now.isoformat().replace("+00:00", "Z"),
                        expires_at.isoformat().replace("+00:00", "Z"),
                    )
                )

            cursor.executemany(
                """
                INSERT INTO family_library_cache (appid, owner_steamids, exclude_reason, cached_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                cache_entries,
            )
            conn.commit()
            logger.debug(
                f"Cached {len(family_apps)} family library apps for {cache_hours} hours"
            )
    except Exception as e:
        logger.error(f"Error caching family library: {e}")


def purge_family_library_cache():
    """Purge all entries from the family_library_cache table."""
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM family_library_cache")
            conn.commit()
            logger.info("Purged all entries from family_library_cache.")
    except Exception as e:
        logger.error(f"Error purging family_library_cache: {e}")


def get_steam_id_from_friendly_name(friendly_name: str) -> str | None:
    """Retrieves the SteamID associated with a given friendly name from the family_members table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT steam_id FROM family_members WHERE friendly_name = ?",
            (friendly_name,),
        )
        result = cursor.fetchone()
        if result:
            return result["steam_id"]
        return None
    except Exception as e:
        logger.error(f"Error retrieving SteamID for friendly name {friendly_name}: {e}")
        return None


def get_steam_id_from_discord_id(discord_id: str) -> str | None:
    """Retrieves the SteamID associated with a given Discord ID.
    Checks family_members table first (for config-driven members with discord_id set),
    then falls back to users table (for !register users)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # First check family_members table (config-driven members with discord_id)
        cursor.execute(
            "SELECT steam_id FROM family_members WHERE discord_id = ?", (discord_id,)
        )
        result = cursor.fetchone()
        if result:
            return result["steam_id"]

        # Fall back to users table (!register users)
        cursor.execute("SELECT steam_id FROM users WHERE discord_id = ?", (discord_id,))
        result = cursor.fetchone()
        if result:
            return result["steam_id"]

        return None
    except Exception as e:
        logger.error(f"Error retrieving SteamID for Discord ID {discord_id}: {e}")
        return None


def cleanup_expired_cache():
    """Remove expired cache entries from all cache tables."""
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()

            tables = [
                "game_details_cache",
                "user_games_cache",
                "wishlist_cache",
                "discord_users_cache",
                "family_library_cache",
                "itad_price_cache",
            ]

            total_deleted = 0
            for table in tables:
                # Check if table has 'permanent' column
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [col[1] for col in cursor.fetchall()]

                query = f"DELETE FROM {table} WHERE expires_at <= STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')"

                if "permanent" in columns:
                    # Protect permanent entries from deletion regardless of expires_at
                    query += " AND (permanent != 1 OR permanent IS NULL)"

                cursor.execute(query)
                deleted = cursor.rowcount
                total_deleted += deleted
                if deleted > 0:
                    logger.debug(f"Cleaned up {deleted} expired entries from {table}")

            conn.commit()
            if total_deleted > 0:
                logger.info(f"Cache cleanup: removed {total_deleted} expired entries")
    except Exception as e:
        logger.error(f"Error during cache cleanup: {e}")


# --- Database-backed migrations ---


def _has_migration_run(migration_name: str) -> bool:
    """Check if a named migration has already been applied."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM migrations WHERE name = ?", (migration_name,))
        return cursor.fetchone() is not None
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return False
    except Exception:
        return False


def _mark_migration_run(migration_name: str) -> None:
    """Record that a named migration has been applied."""
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO migrations (name, applied_at) VALUES (?, STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))",
                (migration_name,),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Error marking migration '{migration_name}': {e}")


def _migrate_family_members_from_config(conn: sqlite3.Connection) -> None:
    """Helper: migrate family members from config.yml under an existing write connection."""
    from familybot.config import FAMILY_USER_DICT

    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM migrations WHERE name = ?",
        ("family_members_from_config",),
    )
    if cursor.fetchone() is not None:
        logger.debug(
            "Database: Migration 'family_members_from_config' already applied. Skipping."
        )
        return

    if FAMILY_USER_DICT:
        logger.info(
            "Database: Migration 'family_members_from_config' not found. Migrating from config.yml."
        )
        config_members_to_insert = []
        for steam_id, value in FAMILY_USER_DICT.items():
            friendly_name, discord_id = _parse_family_config_entry(value)
            config_members_to_insert.append((steam_id, friendly_name, discord_id))

        if config_members_to_insert:
            cursor.executemany(
                "INSERT OR IGNORE INTO family_members (steam_id, friendly_name, discord_id) VALUES (?, ?, ?)",
                config_members_to_insert,
            )
            conn.commit()
            logger.info(
                f"Database: Migrated {len(config_members_to_insert)} family members from config.yml."
            )
        else:
            logger.info(
                "Database: No family members found in config.yml for migration."
            )
    else:
        logger.debug(
            "Database: config.yml is empty. Skipping family members migration."
        )

    cursor.execute(
        "INSERT OR IGNORE INTO migrations (name, applied_at) VALUES (?, STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))",
        ("family_members_from_config",),
    )
    conn.commit()


def load_family_members_from_db() -> dict:
    """
    Loads family member data (steam_id: friendly_name) from the database,
    performing a one-time migration from config.yml if necessary.
    """
    from steam.steamid import SteamID

    members = {}

    # Check and run migration in a single write transaction to avoid TOCTOU race
    if not _has_migration_run("family_members_from_config"):
        with get_write_connection() as write_conn:
            # Re-check under the write lock to handle concurrent startup
            cursor = write_conn.cursor()
            cursor.execute(
                "SELECT 1 FROM migrations WHERE name = ?",
                ("family_members_from_config",),
            )
            if cursor.fetchone() is None:
                _migrate_family_members_from_config(write_conn)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT steam_id, friendly_name FROM family_members")
        for row in cursor.fetchall():
            steam_id = row["steam_id"]
            friendly_name = row["friendly_name"]
            # Basic validation for SteamID64: must be 17 digits and start with '7656119'
            try:
                sid = SteamID(steam_id)
                if sid.is_valid():
                    members[str(sid.as_64)] = friendly_name
                else:
                    logger.warning(
                        f"Database: Invalid SteamID '{steam_id}' found for user '{friendly_name}'. Skipping this entry."
                    )
            except Exception:
                logger.warning(
                    f"Database: Invalid SteamID format '{steam_id}' for user '{friendly_name}'. Skipping this entry."
                )
        logger.debug(f"Loaded {len(members)} valid family members from database.")
    except sqlite3.Error as e:
        logger.error(f"Error reading family members from DB: {e}")

    return members


def load_all_registered_users_from_db() -> dict:
    """Loads all registered users (discord_id: steam_id) from the database."""
    users = {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT discord_id, steam_id FROM users")
        for row in cursor.fetchall():
            users[row["discord_id"]] = row["steam_id"]
        logger.debug(f"Loaded {len(users)} registered users from database.")
    except sqlite3.Error as e:
        logger.error(f"Error reading all registered users from DB: {e}")

    return users
