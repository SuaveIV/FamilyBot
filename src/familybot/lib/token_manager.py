# In src/familybot/lib/token_manager.py

import logging
import os
from datetime import datetime

from familybot.config import PROJECT_ROOT  # Import PROJECT_ROOT

# Setup logging for this specific module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

# Define paths for token files at the project root 'tokens' directory
TOKEN_SAVE_DIR = os.path.join(PROJECT_ROOT, "tokens")
TOKEN_FILE_PATH = os.path.join(TOKEN_SAVE_DIR, "token")
TOKEN_EXP_FILE_PATH = os.path.join(TOKEN_SAVE_DIR, "token_exp")

# Ensure the 'tokens' directory exists when the module is loaded
try:
    os.makedirs(TOKEN_SAVE_DIR, exist_ok=True)
    logger.info(f"Ensured token directory exists: {TOKEN_SAVE_DIR}")
except Exception as e:
    logger.critical(f"Failed to create token directory {TOKEN_SAVE_DIR}: {e}")
    # In a real application, you might want to raise an error or exit here.


def check_token_exp() -> bool:
    """Checks if the webapi_token is expired."""
    try:
        with open(TOKEN_EXP_FILE_PATH, "r") as token_exp_file:
            token_exp_str = token_exp_file.readline().strip()
            if not token_exp_str:
                logger.warning(
                    f"Token expiration file {TOKEN_EXP_FILE_PATH} is empty. Assuming expired."
                )
                return False
            token_exp_timestamp = int(token_exp_str)

        now_timestamp = int(datetime.now().timestamp())
        is_expired = now_timestamp > token_exp_timestamp
        if is_expired:
            logger.info("webapi_token is expired.")
        else:
            logger.debug(
                f"webapi_token is valid. Expires at {datetime.fromtimestamp(token_exp_timestamp)}"
            )
        return not is_expired
    except FileNotFoundError:
        logger.warning(
            f"Token expiration file not found at {TOKEN_EXP_FILE_PATH}. Assuming expired."
        )
        return False
    except ValueError as e:
        logger.error(
            f"Invalid timestamp in {TOKEN_EXP_FILE_PATH}: '{token_exp_str}'. Error: {e}. Assuming expired."
        )
        return False
    except Exception as e:
        logger.error(
            f"Error checking token expiration from {TOKEN_EXP_FILE_PATH}: {e}. Assuming expired."
        )
        return False


def get_token() -> str:
    """Retrieves the webapi_token from file."""
    try:
        with open(TOKEN_FILE_PATH, "r") as token_file:
            token = token_file.readline().strip()
            logger.debug(f"Loaded webapi_token (length {len(token)}).")
            return token
    except FileNotFoundError:
        logger.warning(
            f"Token file not found at {TOKEN_FILE_PATH}. Returning empty token."
        )
        return ""
    except Exception as e:
        logger.error(f"Error reading token from {TOKEN_FILE_PATH}: {e}.")
        return ""


# All subprocess management of WebSocketServer has been removed from this file.
