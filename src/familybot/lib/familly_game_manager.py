# In src/familybot/lib/familly_game_manager.py

import logging
import os
import sqlite3
from datetime import datetime  # Import datetime to get current time

from familybot.config import PROJECT_ROOT
from familybot.lib.database import get_db_connection

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

OLD_GAME_LIST_FILE_PATH = os.path.join(PROJECT_ROOT, 'data', 'gamelist.txt')
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')

# Ensure the data directory exists when the module is loaded
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info(f"Ensured data directory exists: {DATA_DIR}")
except Exception as e:
    logger.critical(f"Failed to create data directory {DATA_DIR}: {e}")

def _migrate_gamelist_to_db(conn: sqlite3.Connection):
    """Internal function to migrate existing gamelist.txt data to the database."""
    if os.path.exists(OLD_GAME_LIST_FILE_PATH):
        logger.info(f"Attempting to migrate games from old file: {OLD_GAME_LIST_FILE_PATH}")
        try:
            with open(OLD_GAME_LIST_FILE_PATH, 'r') as f:
                appids_to_insert = []
                for line in f:
                    appid = line.strip()
                    if appid:
                        # For old games, use 'NOW' for detected_at, as we don't have historical data
                        appids_to_insert.append((appid,)) # Only appid for default timestamp
                
                if appids_to_insert:
                    cursor = conn.cursor()
                    # Use INSERT OR IGNORE in case some games already exist from a partial run
                    cursor.executemany("INSERT OR IGNORE INTO saved_games (appid) VALUES (?)", appids_to_insert)
                    conn.commit()
                    logger.info(f"Migrated {len(appids_to_insert)} games from {OLD_GAME_LIST_FILE_PATH} to database.")
                    # Optionally, remove the old file after successful migration
                    # os.remove(OLD_GAME_LIST_FILE_PATH)
                    # logger.info(f"Removed old gamelist file: {OLD_GAME_LIST_FILE_PATH}")
                else:
                    logger.info("No games found in old gamelist.txt for migration.")
        except Exception as e:
            logger.error(f"Error during gamelist.txt migration to DB: {e}", exc_info=True)
    else:
        logger.info("No old gamelist.txt found for migration. Skipping.")


def get_saved_games() -> list:
    """Reads the list of saved game AppIDs from the database."""
    appids = []
    conn = None
    try:
        conn = get_db_connection()
        _migrate_gamelist_to_db(conn) # Attempt migration if file exists on first read
        cursor = conn.cursor()
        # Select both appid and detected_at for sorting later
        cursor.execute("SELECT appid, detected_at FROM saved_games")
        # Return a list of tuples or dicts, depending on how steam_family expects it.
        # For sorting, we'll return tuples (appid, detected_at)
        appids = [(row["appid"], row["detected_at"]) for row in cursor.fetchall()]
        logger.debug(f"Loaded {len(appids)} games from database.")
    except sqlite3.Error as e:
        logger.error(f"Error reading saved games from DB: {e}")
    finally:
        if conn:
            conn.close()
    return appids


def set_saved_games(game_data_list: list) -> None: # Renamed parameter for clarity
    """Writes the list of game AppIDs to the database (overwriting previous list).
       game_data_list should be a list of (appid, detected_at_timestamp_str) tuples."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM saved_games") # Clear existing games

        # Prepare data for insertion: (appid, detected_at)
        # If detected_at is not provided, use current timestamp
        appids_to_insert = []
        for item in game_data_list:
            if isinstance(item, tuple) and len(item) == 2:
                appids_to_insert.append((str(item[0]), str(item[1])))
            else: # Assume it's just an appid string, use current time
                appids_to_insert.append((str(item), datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'))

        if appids_to_insert:
            cursor.executemany("INSERT INTO saved_games (appid, detected_at) VALUES (?, ?)", appids_to_insert)
        conn.commit()
        logger.info(f"Saved {len(game_data_list)} games to database.")
    except sqlite3.Error as e:
        logger.error(f"Error writing saved games to DB: {e}")
    finally:
        if conn:
            conn.close()