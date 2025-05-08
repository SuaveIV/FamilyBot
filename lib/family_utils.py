from config import *
from lib.utils import *
from lib.token_manager import get_token
import requests
import json


def find_in_2d_list(to_find: str, list_2d: list) -> int:
    for i in range(len(list_2d)):
        if list_2d[i][0] == to_find:
            return i

# Generate the URL for the request to get the Family Game List
def get_family_game_list_url() -> str:
    token = get_token()
    url_family_list = f"https://api.steampowered.com/IFamilyGroupsService/GetSharedLibraryApps/v1/?access_token={token}&include_own=true&include_free=false&language=french&family_groupid={FAMILY_STEAM_ID}"
    return url_family_list

def format_message(wishlist: list,short= False) -> str:
    message = "# 📝 Family Wishlist \n"
    for i in range(len(wishlist)):
        app_id = wishlist[i][0]
        message += "- "
        for user in wishlist[i][1]:
            message += FAMILY_USER_DICT[user] + ", "
        message += "want "
        app_id = wishlist[i][0]

        # Send a GET request to the Steam app details API
        game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=fr&l=fr"
        game_info = requests.get(game_url).text
        game_info = json.loads(game_info)
        game_info = game_info[app_id]["data"]
        message += f"[{game_info['name']}](<https://store.steampowered.com/app/{app_id}>)  \n "
        if game_info["price_overview"]["discount_percent"] != 0:  # Check if the game is on sale
            message += f"  **__The game is on sale at {game_info['price_overview']['final_formatted']} (-{game_info['price_overview']['discount_percent']}%)__**  \n"
            if not short:
                message += f" which is {round(game_info['price_overview']['final'] / 100 / len(wishlist[i][1]), 2)}€ per person  \n"
                message += f"   The lowest price ever was {get_lowest_price(app_id)}€  \n"
        else:
            message += f"  The game is at {game_info['price_overview']['final_formatted']}  \n"
            if not short:
                message += f" which is {round(game_info['price_overview']['final'] / 100 / len(wishlist[i][1]), 2)}€ per person  \n"
                message += f"   The lowest price ever was {get_lowest_price(app_id)}€  \n"
                
    if len(message) > 2000 and not short:
        message = format_message(wishlist,True)
    elif len(message) > 2000 and  short:
        message = "# 📝 Family Wishlist  \n Can't create a message or it will be too long"
        
    return message
