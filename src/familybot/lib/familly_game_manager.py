# In src/familybot/lib/familly_game_manager.py

import os
import logging

# Import PROJECT_ROOT from familybot.config
from familybot.config import PROJECT_ROOT

# Setup logging for this specific module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the path for the game list file (e.g., in a 'data' subfolder at the project root)
DATA_DIR = os.path.join(PROJECT_ROOT, 'data') # Dedicated folder for data files
GAME_LIST_FILE_PATH = os.path.join(DATA_DIR, 'gamelist.txt')

# Ensure the data directory exists when the module is loaded
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info(f"Ensured data directory exists: {DATA_DIR}")
except Exception as e:
    logger.critical(f"Failed to create data directory {DATA_DIR}: {e}")
    # This is a critical error, file operations will likely fail.

def get_saved_games() -> list:
    """Reads the list of saved game AppIDs from gamelist.txt."""
    game_file_list = []
    try:
        with open(GAME_LIST_FILE_PATH, 'r') as game_file:
            for line in game_file:
                cleaned_line = line.strip()
                if cleaned_line:
                    game_file_list.append(cleaned_line)
        logger.debug(f"Loaded {len(game_file_list)} games from {GAME_LIST_FILE_PATH}")
        return game_file_list
    except FileNotFoundError:
        logger.warning(f"Game list file not found at {GAME_LIST_FILE_PATH}. Returning empty list.")
        return []
    except Exception as e:
        logger.error(f"Error reading game list file {GAME_LIST_FILE_PATH}: {e}")
        return []


def set_saved_games(game_list: list) -> None:
    """Writes the list of game AppIDs to gamelist.txt."""
    try:
        # Ensure the directory exists (redundant with initial check but good for safety if called standalone)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(GAME_LIST_FILE_PATH, 'w') as save_file:
            save_file.write('\n'.join(str(i) for i in game_list))
        logger.info(f"Saved {len(game_list)} games to {GAME_LIST_FILE_PATH}")
    except Exception as e:
        logger.error(f"Error writing game list to file {GAME_LIST_FILE_PATH}: {e}")