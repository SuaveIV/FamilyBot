# In src/familybot/config.py

import yaml
from pathlib import Path
import os # Import os for path manipulation

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
    with open(CONFIG_FILE_PATH, 'r') as file:
        config = yaml.safe_load(file)
except FileNotFoundError:
    print(f"Error: config.yml not found at {CONFIG_FILE_PATH}. Please ensure it's in the project root.")
    # In a real application, you might want to raise a custom exception here or use logging
    exit(1)
except yaml.YAMLError as e:
    print(f"Error parsing config.yml at {CONFIG_FILE_PATH}: {e}")
    exit(1)


# SCRIPT_PATH for internal package paths (e.g., if plugins are relative to src/familybot)
# This points to 'src/familybot/'
SCRIPT_PATH = current_script_path.parent.as_posix()


#-_-_-_-_-_-_-_-_ CONFIGURATION _-_-_-_-_-_-_-_-

DISCORD_API_KEY = config["discord"]["api_key"]
ADMIN_DISCORD_ID = config["discord"]["admin_id"]

# PLUGIN_PATH points to the 'plugins' directory *within* the 'familybot' package
PLUGIN_PATH = os.path.join(SCRIPT_PATH, 'plugins')


#------------Steam_Family--------------
NEW_GAME_CHANNEL_ID = config["steam_family"]["channel_id"]["new_game"]
WISHLIST_CHANNEL_ID = config["steam_family"]["channel_id"]["wishlist"]

FAMILY_STEAM_ID = config["steam_family"]["family_id"]
FAMILY_USER_DICT = config["steam_family"]["user_id"]

IP_ADDRESS = config["steam_family"]["websocket_server_ip"]

ITAD_API_KEY = config["steam_family"]["itad_api_key"]
STEAMWORKS_API_KEY = config["steam_family"]["steamworks_api_key"]

#--------------free_epicgames------------
EPIC_CHANNEL_ID = config["free_epicgames"]["channel_id"]

#-------------Help_message---------------
HELP_CHANNEL_ID = config["help_message"]["channel_id"]

#-------------Token_Sender---------------
TOKEN_SAVE_PATH = config["token_sender"]["token_save_path"]
BROWSER_PROFILE_PATH = config["token_sender"]["browser_profile_path"]
UPDATE_BUFFER_HOURS = config["token_sender"]["update_buffer_hours"]

#-------------Web_UI---------------
WEB_UI_ENABLED = config.get("web_ui", {}).get("enabled", True)
WEB_UI_HOST = config.get("web_ui", {}).get("host", "127.0.0.1")
WEB_UI_PORT = config.get("web_ui", {}).get("port", 8080)
WEB_UI_DEFAULT_THEME = config.get("web_ui", {}).get("default_theme", "default")
