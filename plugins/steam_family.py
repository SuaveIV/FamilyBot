from config import *
from interactions import *
from interactions.ext.prefixed_commands import prefixed_command, PrefixedContext
from config import *
from lib.token_manager import *
from lib.family_utils import *
from lib.familly_game_manager import *
import requests
import json

class steam_family(Extension):
    def __init__(self,bot):
        print("Steam Familly Plugin loaded")
    """
    [help]|!coop| it returns all the family shared multiplayer games in the shared library with a given numbers of copies| !coop NUMBER_OF_COPIES | ***This command can be used in bot DM***
    """
    @prefixed_command(name="coop")
    async def coop_command(self,ctx: PrefixedContext)-> None:
        number = int(ctx.args[0])
        if number <= 1:
            await ctx.send("The number after the command must be greater than 1")
        else:
            if check_token_exp():
                loading_message = await ctx.send("search for games with " + str(number) + " copies")
                answer = requests.get(get_family_game_list_url())
                games_json = json.loads(answer.text)
                game_list = games_json["response"]["apps"]
                game_array = []
                coop_game = []
                for game in game_list:
                    if game["exclude_reason"] != 3:
                        if len(game["owner_steamids"]) >= number:
                            game_array.append(str(game["appid"]))
                for game in game_array:
                    game_url = f"https://store.steampowered.com/api/appdetails?appids={game}&cc=fr&l=fr"
                    game_info = requests.get(game_url).text
                    game_info = json.loads(game_info)
                    if game_info[str(game)]["success"]:
                        game_info = game_info[str(game)]["data"]
                        # Check if the game is a paid game and is shared with the family
                        if (game_info["type"] == "game"
                            and game_info["is_free"] == False
                            and str(game_info["categories"]).find("{'id': 62,")) != -1:
                            if (str(game_info["categories"]).find("{'id': 36,") != -1
                                or str(game_info["categories"]).find("{'id': 38,") != -1
                                or str(game_info["categories"]).find("{'id': 1,") != -1):
                                coop_game.append(game_info["name"])
                    else:
                        print(str(game))
                await loading_message.delete()
                await loading_message.edit(content='\n'.join(coop_game))
            else:
                await ctx.send('Token Expired Try Later')

        
    @prefixed_command(name="force")
    async def force_command(self,ctx: PrefixedContext)-> None:
        if ctx.author_id == ADMIN_DISCORD_ID and ctx.guild is None:
            await self.send_new_game()
            await self.bot.send_log_dm("Force Notification")
            return
    
    @prefixed_command(name="forcewishlist")
    async def force_command(self,ctx: PrefixedContext)-> None:
        if ctx.author_id == ADMIN_DISCORD_ID and ctx.guild is None:
            await self.refresh_wishlist()
            await self.bot.send_log_dm("Force Wishlist")
            return
            
    @Task.create(IntervalTrigger(hours=1))
    async def send_new_game(self) -> None:
        url_family_list = get_family_game_list_url()
        # Check if the token is expired
        if check_token_exp():
            # Send a GET request to the Steam family list API
            answer = requests.get(url_family_list)
            try:
                # Parse the JSON response
                games_json = json.loads(answer.text)
                game_list = games_json["response"]["apps"]
                game_owner_list = {}
                game_array = []
                # Loop through the games in the response
                for game in game_list:
                    if game["exclude_reason"] != 3:
                        game_array.append(str(game["appid"]))
                        if len(game["owner_steamids"]) == 1:
                            game_owner_list[str(game["appid"])] = str(game["owner_steamids"][0])

                # Get the saved games from the file
                game_file_list = get_saved_games()
                # Check if there are any new games
                new_games = set(game_array) - set(game_file_list)
                if len(new_games) > 0:
                    # Loop through the new games
                    for new in new_games:
                        # Send a GET request to the Steam app details API
                        game_url = f"https://store.steampowered.com/api/appdetails?appids={new}&cc=fr&l=fr"
                        game_info = requests.get(game_url).text
                        game_info = json.loads(game_info)
                        if game_info[str(new)]["success"]:
                            try:
                                game_info = game_info[str(new)]["data"]
                            
                            # Check if the game is a paid game and is shared with the family
                                if game_info["type"] == "game" and game_info["is_free"] == False and str(game_info["categories"]).find("{'id': 62,") != -1:
                                    # Send a message to the general channel
                                    await self.bot.send_to_channel(NEW_GAME_CHANNEL_ID,f"Thank you to {FAMILY_USER_DICT[game_owner_list[str(new)]]} for \n https://store.steampowered.com/app/{new}&cc=fr&l=fr")
                            except:
                                print(game_info[str(new)])
                        else:
                            print(new)
                    # Save the new game list to the file
                    set_saved_games(game_array)
                else:
                    print('No new games detected')
            except Exception as e:
                # Log the error and send a message to the user
                # print('Wrong API answer: \n' + answer.text)
                print(e)
                await self.bot.send_log_dm("Issue with API answer, exception:" + e)
        else:
            # Send a message to the user if the token is expired
            await self.bot.send_log_dm("Token is expired")
    
        
    @Task.create(IntervalTrigger(hours=24))
    async def refresh_wishlist(self) -> None:
        global_wishlist = []
        
        for user_steam_id, user_name in FAMILY_USER_DICT.items():
            wishlist_url = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid={user_steam_id}"
            wishlist = requests.get(wishlist_url)
            if wishlist.text == "{\"success\":2}":
                print(f"{user_name}'s wishlist is private")
            else:
                wishlist_json = json.loads(wishlist.text)
                
                for game in wishlist_json.items():
                    if not any(str(game["appid"]) in sublist for sublist in global_wishlist):
                            global_wishlist.append([game["appid"], int(user_steam_id)])
                    else:
                        global_wishlist[find_in_2d_list(game["appid"], global_wishlist)][1].append(int(user_steam_id))

        duplicate_games = []
        for i in range(len(global_wishlist)):
            if len(global_wishlist[i][1]) > 1:
                app_id = global_wishlist[i][0]

                # Send a GET request to the Steam app details API
                game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=fr&l=fr"
                game_info = requests.get(game_url).text
                game_info = json.loads(game_info)
                game_info = game_info[app_id]["data"]
                # Check if the game is a paid game and is shared with the family
                if (str(game_info["categories"]).find("{'id': 62,") != -1
                    and game_info["is_free_game"] == False 
                    and "recommendations" in game_info
                    and app_id not in get_saved_games()):
                    # Send a message to the general channel
                    duplicate_games.append(global_wishlist[i])
            # Save the new game list to the file
        wishlist_channel = await self.bot.fetch_channel(WISHLIST_CHANNEL_ID)
        pinned_messages = await wishlist_channel.fetch_pinned_messages()
        wishlist_new_message = format_message(duplicate_games)
        
        if len(pinned_messages) == 0:                                        
            help_message_id = await wishlist_channel.send(wishlist_new_message)
            await help_message_id.pin()
        else:
            await pinned_messages[len(pinned_messages)-1].edit(content=wishlist_new_message)

    @listen()
    async def on_startup(self):
        self.refresh_wishlist.start()
        self.send_new_game.start()
        print("--Steam Family Tasks Started")