# In src/familybot/lib/database.py

import sqlite3
import os
import logging
from familybot.config import PROJECT_ROOT # Import PROJECT_ROOT

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DATABASE_FILE = os.path.join(PROJECT_ROOT, 'bot_data.db')

def get_db_connection():
    """Establishes and returns a new SQLite database connection."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row # Allows accessing columns by name
        return conn
    except sqlite3.Error as e:
        logger.critical(f"Database connection error: {e}")
        raise # Re-raise to indicate a critical failure

def init_db():
    """Initializes the database schema by creating tables if they don't exist."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Create 'users' table for Discord ID and Steam ID registrations
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                discord_id TEXT PRIMARY KEY,
                steam_id TEXT NOT NULL UNIQUE
            )
        ''')
        logger.info("Database: 'users' table checked/created.")

        # Create 'saved_games' table for AppIDs (for new game notifications)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_games (
                appid TEXT PRIMARY KEY
            )
        ''')
        logger.info("Database: 'saved_games' table checked/created.")

        conn.commit()
    except sqlite3.Error as e:
        logger.critical(f"Database initialization error: {e}")
    finally:
        if conn:
            conn.close()