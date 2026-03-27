# In src/familybot/config.py

import os  # Import os for path manipulation
import sys
from pathlib import Path

import yaml

# Get the path to the current script (config.py)
current_script_path = Path(__file__)

# Navigate up to the project root 'FamilyBot/'
# .parent -> src/familybot/
# .parent.parent -> src/
# .parent.parent.parent -> FamilyBot/ (the project root)
PROJECT_ROOT = current_script_path.parent.parent.parent.as_posix()

# Now use this PROJECT_ROOT to open config.yml
CONFIG_FILE_PATH = Path(PROJECT_ROOT) / "config.yml"

try:
    with open(CONFIG_FILE_PATH, "r") as file:
        config = yaml.safe_load(file)
except FileNotFoundError:
    print(
        f"Error: config.yml not found at {CONFIG_FILE_PATH}. Please ensure it's in the project root."
    )
    # In a real application, you might want to raise a custom exception here or use logging
    exit(1)
except yaml.YAMLError as e:
    print(f"Error parsing config.yml at {CONFIG_FILE_PATH}: {e}")
    exit(1)


# SCRIPT_PATH for internal package paths (e.g., if plugins are relative to src/familybot)
# This points to 'src/familybot/'
SCRIPT_PATH = current_script_path.parent.as_posix()


# -_-_-_-_-_-_-_-_ CONFIGURATION _-_-_-_-_-_-_-_-

DISCORD_API_KEY = config["discord"]["api_key"]
ADMIN_DISCORD_ID = config["discord"]["admin_id"]

# PLUGIN_PATH points to the 'plugins' directory *within* the 'familybot' package
PLUGIN_PATH = os.path.join(SCRIPT_PATH, "plugins")


# ------------Steam_Family--------------
NEW_GAME_CHANNEL_ID = config["steam_family"]["channel_id"]["new_game"]
WISHLIST_CHANNEL_ID = config["steam_family"]["channel_id"]["wishlist"]

FAMILY_STEAM_ID = config["steam_family"]["family_id"]
FAMILY_USER_DICT = config["steam_family"]["user_id"]

IP_ADDRESS = config["steam_family"]["websocket_server_ip"]

ITAD_API_KEY = config["steam_family"]["itad_api_key"]
STEAMWORKS_API_KEY = config["steam_family"]["steamworks_api_key"]

# --------------free_epicgames------------
EPIC_CHANNEL_ID = config["free_epicgames"]["channel_id"]

# -------------Help_message---------------
HELP_CHANNEL_ID = config["help_message"]["channel_id"]

# -------------Token_Sender---------------
TOKEN_SAVE_PATH = config["token_sender"]["token_save_path"]
BROWSER_PROFILE_PATH = config["token_sender"]["browser_profile_path"]
UPDATE_BUFFER_HOURS = config["token_sender"]["update_buffer_hours"]

# -------------Web_UI---------------
WEB_UI_ENABLED = config.get("web_ui", {}).get("enabled", True)
WEB_UI_HOST = config.get("web_ui", {}).get("host", "127.0.0.1")
WEB_UI_PORT = config.get("web_ui", {}).get("port", 8080)
WEB_UI_DEFAULT_THEME = config.get("web_ui", {}).get("default_theme", "default")

# -------------Cache TTLs (Hours)---------------
FAMILY_LIBRARY_CACHE_TTL = (
    config.get("steam_family", {}).get("cache_ttl_hours", {}).get("family_library", 1)
)
WISHLIST_CACHE_TTL = (
    config.get("steam_family", {}).get("cache_ttl_hours", {}).get("wishlist", 2)
)
GAME_DETAILS_CACHE_TTL = (
    config.get("steam_family", {}).get("cache_ttl_hours", {}).get("game_details", 168)
)  # 1 week
ITAD_CACHE_TTL = (
    config.get("steam_family", {}).get("cache_ttl_hours", {}).get("itad_prices", 336)
)  # 14 days


# -------------Config Validation---------------
class ConfigurationError(Exception):
    """Raised when config.yml has invalid or missing required values."""

    pass


def validate_config() -> None:
    """Validate configuration values at startup.

    Raises ConfigurationError with a clear message if any required
    values are missing, contain placeholders, or have invalid types.
    """
    errors: list[str] = []

    # --- Discord ---
    if not DISCORD_API_KEY or DISCORD_API_KEY.strip() == "":
        errors.append("discord.api_key is empty. Set your Discord bot token.")
    if not isinstance(ADMIN_DISCORD_ID, int) or ADMIN_DISCORD_ID == 0:
        errors.append(
            "discord.admin_id must be a non-zero integer (your Discord user ID)."
        )

    # --- Steam Family ---
    if not STEAMWORKS_API_KEY or STEAMWORKS_API_KEY.strip() == "":
        errors.append(
            "steam_family.steamworks_api_key is empty. Get one from steamcommunity.com/dev/apikey."
        )
    if not ITAD_API_KEY or ITAD_API_KEY.strip() == "":
        errors.append(
            "steam_family.itad_api_key is empty. Get one from isthereanydeal.com/apps/my/."
        )
    if not isinstance(FAMILY_STEAM_ID, int) or FAMILY_STEAM_ID == 0:
        errors.append(
            "steam_family.family_id must be a non-zero integer (your Steam Family Group ID)."
        )

    # --- Channel IDs ---
    for name, value in [
        ("steam_family.channel_id.new_game", NEW_GAME_CHANNEL_ID),
        ("steam_family.channel_id.wishlist", WISHLIST_CHANNEL_ID),
        ("free_epicgames.channel_id", EPIC_CHANNEL_ID),
        ("help_message.channel_id", HELP_CHANNEL_ID),
    ]:
        if not isinstance(value, int) or value == 0:
            errors.append(f"{name} must be a non-zero integer (Discord channel ID).")

    # --- Token sender paths ---
    if not TOKEN_SAVE_PATH:
        errors.append("token_sender.token_save_path is empty.")

    # --- Web UI ---
    if WEB_UI_ENABLED:
        if not isinstance(WEB_UI_PORT, int) or not (1 <= WEB_UI_PORT <= 65535):
            errors.append(
                f"web_ui.port must be an integer between 1 and 65535, got {WEB_UI_PORT!r}."
            )

    if errors:
        error_list = "\n  - ".join(errors)
        raise ConfigurationError(
            f"Configuration validation failed with {len(errors)} error(s):\n  - {error_list}"
        )


# Run validation at import time
try:
    validate_config()
except ConfigurationError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
