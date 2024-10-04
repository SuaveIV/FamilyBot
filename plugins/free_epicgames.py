from interactions import *
from datetime import datetime
import requests
import json
from config import *

class free_epicgames(Extension):
    def __init__(self,bot):
        print("Epic Games Plugin loaded")

    @Task.create(IntervalTrigger(seconds=10))
    async def send_epic_free_games(self) -> None:
        now = datetime.now()
        if now.weekday() == 3 and now.hour == 17 and now.minute == 15:
            epic_games_channel = self.bot.fetch_channel(EPIC_CHANNEL_ID)
            epic_url = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions?locale=fr&country=FR&allowCountries=FR"
            base_shop_url = "https://store.epicgames.com/fr/p/"

            answer = requests.get(epic_url)

            json_answer = json.loads(answer.text)

            game_list = json_answer["data"]["Catalog"]["searchStore"]["elements"]
            await epic_games_channel.send("The free games on the Epic Game Store this week are:")
            for game in game_list:
                if (game["offerType"] == 'BASE_GAME'
                    and game["price"]["totalPrice"]["discountPrice"] == 0
                    and game["status"] == "ACTIVE"
                    and len(game["promotions"]["promotionalOffers"]) == 1):
                    try:
                        game_epic_id = game["offerMappings"][0]["pageSlug"]
                    except:
                        game_epic_id = game["urlSlug"]
                    await epic_games_channel.send(base_shop_url + game_epic_id)

    @listen()
    async def on_startup(self):
        self.send_epic_free_games.start()
        print("--Epic Games Task Started")