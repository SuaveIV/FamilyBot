import yaml
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent.as_posix()
with open(SCRIPT_PATH + "/config.yml", 'r') as file:
    config = yaml.safe_load(file)

#-_-_-_-_-_-_-_-_ CONFIGURATION _-_-_-_-_-_-_-_-

DISCORD_API_KEY = config["discord"]["api_key"]
ADMIN_DISCORD_ID = config["discord"]["admin_id"]
PLUGIN_PATH = SCRIPT_PATH + '/plugins/'

#------------Steam_Family--------------
NEW_GAME_CHANNEL_ID = config["steam_family"]["channel_id"]["new_game"]
WISHLIST_CHANNEL_ID = config["steam_family"]["channel_id"]["wishlist"]

FAMILY_STEAM_ID = config["steam_family"]["family_id"]
FAMILY_USER_DICT = config["steam_family"]["user_id"]

IP_ADDRESS = config["steam_family"]["websocket_server_ip"]

ITAD_API_KEY = config["steam_family"]["itad_api_key"]

#--------------free_epicgames------------
EPIC_CHANNEL_ID = config["free_epicgames"]["channel_id"]

#-------------Help_message---------------
HELP_CHANNEL_ID = config["help_message"]["channel_id"]