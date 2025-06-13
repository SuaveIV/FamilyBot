# In src/familybot/lib/familly_game_manager.py

import os
import logging
import sqlite3 # Import sqlite3 for specific error handling
from familybot.config import PROJECT_ROOT
from familybot.lib.database import get_db_connection # <<< Import get_db_connection

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the path for the OLD gamelist.txt file for migration (if it exists)
OLD_GAME_LIST_FILE_PATH = os.path.join(PROJECT_ROOT, 'data', 'gamelist.txt')

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
                        appids_to_insert.append((appid,)) # Tuple for executemany

                if appids_to_insert:
                    cursor = conn.cursor()
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
        cursor.execute("SELECT appid FROM saved_games")
        appids = [row[0] for row in cursor.fetchall()]
        logger.debug(f"Loaded {len(appids)} games from database.")
    except sqlite3.Error as e:
        logger.error(f"Error reading saved games from DB: {e}")
    finally:
        if conn:
            conn.close()
    return appids


def set_saved_games(game_list: list) -> None:
    """Writes the list of game AppIDs to the database (overwriting previous list)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM saved_games") # Clear existing games

        appids_to_insert = [(str(appid),) for appid in game_list]
        if appids_to_insert:
            cursor.executemany("INSERT INTO saved_games (appid) VALUES (?)", appids_to_insert)
        conn.commit()
        logger.info(f"Saved {len(game_list)} games to database.")
    except sqlite3.Error as e:
        logger.error(f"Error writing saved games to DB: {e}")
    finally:
        if conn:
            conn.close()