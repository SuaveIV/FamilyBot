from config import *
import requests

# Function to send a log message to a specific Discord user

def get_lowest_price(steam_app_id: int) -> str:
    url = f"https://api.isthereanydeal.com/games/lookup/v1?key={ITAD_API_KEY}&appid={steam_app_id}"
    answer = requests.get(url).json()

    game_id = answer["game"]["id"]

    data = [game_id]
    url = f"https://api.isthereanydeal.com/games/storelow/v2?key={ITAD_API_KEY}&country=FR&shops=61"
    answer = requests.post(url, json=data).json()
    return str(answer[0]["lows"][0]["price"]["amount"])

def get_common_elements_in_lists(list_of_lists):
    # Trouver les éléments communs pour chaque paire de sublist
    common_element = set()
    for i in range(len(list_of_lists)):
        for j in range(i+1, len(list_of_lists)):
            common_element = set(list_of_lists[i]).intersection(set(list_of_lists[j]))
            
            # Mélanger les deux ensembles pour trouver les éléments communs aux trois listes
            common_element = common_element.intersection(set(list_of_lists[0]))
    
    return sorted(list(common_element))

# async def send_log_dm(client,message: str) -> None:
#     # Fetch the user to send the message to
#     user = await client.fetch_user(ADMIN_DISCORD_ID)
#     # Get the current date and time
#     now = datetime.now()
#     now = now.strftime("%d/%m/%y %H:%M:%S")
#     # Send the message with the current date and time
#     await user.send(now + " -> " + message)