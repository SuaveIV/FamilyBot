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
