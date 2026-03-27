# In src/familybot/lib/database.py

import contextlib
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager

from familybot.config import PROJECT_ROOT

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


def _create_tables(cursor: sqlite3.Cursor):
    """Creates all necessary database tables if they do not already exist."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            discord_id TEXT PRIMARY KEY,
            steam_id TEXT NOT NULL UNIQUE
        )
    """)
    logger.info("Database: 'users' table checked/created.")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_games (
            appid TEXT PRIMARY KEY,
            detected_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
        )
    """)
    logger.info("Database: 'saved_games' table checked/created.")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS family_members (
            steam_id TEXT PRIMARY KEY,
            friendly_name TEXT NOT NULL,
            discord_id TEXT
        )
    """)
    logger.info("Database: 'family_members' table checked/created.")

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS discord_users_cache (
            discord_id TEXT PRIMARY KEY,
            username TEXT,
            cached_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)
    logger.info("Database: 'discord_users_cache' table checked/created.")

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS steam_itad_mapping (
            appid TEXT PRIMARY KEY,
            itad_id TEXT NOT NULL,
            mapped_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
        )
    """)
    logger.info("Database: 'steam_itad_mapping' table checked/created.")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
        )
    """)
    logger.info("Database: 'migrations' table checked/created.")


def _run_column_migrations(cursor: sqlite3.Cursor):
    """Applies declarative column migrations to existing tables."""
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

    for table, column, definition, update_val in COLUMN_MIGRATIONS:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cursor.fetchall()]

        if column not in columns:
            logger.info(f"Database: Adding column '{column}' to table '{table}'.")
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                if update_val is not None:
                    cursor.execute(
                        f"UPDATE {table} SET {column} = {update_val} WHERE {column} IS NULL"
                    )
                logger.info(f"Database: Successfully added '{column}' to '{table}'.")
            except sqlite3.OperationalError as e:
                logger.error(f"Database: Failed to add '{column}' to '{table}': {e}")
                raise RuntimeError(
                    f"Database migration failed: unable to add column '{column}' to table '{table}'. "
                    f"Aborting initialization to prevent partial schema migration."
                ) from e


def init_db():
    """Initializes the database schema by creating tables if they don't exist
    and adding new columns if they are missing (for schema evolution)."""
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()

            _create_tables(cursor)
            _run_column_migrations(cursor)

            conn.commit()  # Final commit
    except sqlite3.Error as e:
        logger.critical(f"Database initialization error: {e}")


# === CACHE HELPER FUNCTIONS ===


def cleanup_expired_cache():
    """Remove expired cache entries from all cache tables."""
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()

            tables = [
                "game_details_cache",
                "user_games_cache",
                "wishlist_cache",
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
