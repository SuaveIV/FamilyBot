from interactions import *
from interactions.ext.prefixed_commands import prefixed_command, PrefixedContext
import json
from lib.token_manager import *
from lib.utils import *
import requests
from config import *

class common_games(Extension):
    def __init__(self,bot):
        print("common Games Plugin loaded")
        
    #function to link discord id to Steam ID
    # uses https://steamid.pro/fr/ to get the steam id
    """
        [help]|!register|make the link beetween a discord account and a steam one| !register YOUR_STEAM_ID | to get your steam id you cans go on this page an put the url of your steam profile page: https://steamid.pro/fr/. ***This command can be used in bot DM*** 
    """
    @prefixed_command(name="register")
    async def regiser(self,ctx: PrefixedContext):
        registered = False
        print(ctx.author_id)
        discord_id = ctx.author_id
        steam_id = ctx.args[0]
        if len(steam_id) == 17:
            print("steam_id ok")
            with open(SCRIPT_PATH + '/register.csv', 'r') as f:
                for line in f.readlines():
                    if steam_id in line:
                        await ctx.send("you are alredy registered")
                        registered = True
            if not registered:
                with open(SCRIPT_PATH + '/register.csv', 'a') as f:
                    f.write(str(discord_id)+","+steam_id+"\n")
        else:
            print("steam_id not ok")
            await ctx.send("you've made a mistake on your steam id please check again or contact an admin")
        pass
    
    
    """
    [help]|!common_games|get the multiplayer games that the given person have in common and send the result in dm| !common_games @user1 @user2 ... | the users put in the command needs to be registered before. ***This command can be used in bot DM***
    """
    @prefixed_command(name="common_games")
    async def get_common_games(self,ctx: PrefixedContext):
        user_list = []
        if check_token_exp():
            token = get_token()
            # print(ctx.args)
            user_list.append(str(ctx.author_id))
            for arg in ctx.args:
                if "<@" not in arg:
                    await ctx.send("wrong arguments")
                    break
                else:
                    clean_id = arg.replace("<@","")
                    clean_id = clean_id.replace(">","")
                    if clean_id not in user_list:
                        user_list.append(clean_id)
            # print(user_list)
            #check if user in csv
            user_found = 0
            with open(SCRIPT_PATH + '/register.csv',"r") as f:
                for line in f.readlines():
                    for user in user_list:
                        if user in line:
                            user_found += 1
            if user_found == len(user_list):
                game_lists = []
                with open(SCRIPT_PATH + '/register.csv',"r") as f:
                    for line in f.readlines():
                        for user in user_list:
                            if user in line:
                                temp_game_list = []
                                steam_id = line.split(',')[1]
                                steam_get_games_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?access_token={token}&steamid={steam_id}"
                                answer = requests.get(steam_get_games_url)
                                user_game_list_json = json.loads(answer.text)["response"]["games"]
                                for game in user_game_list_json:
                                    temp_game_list.append(game["appid"])
                                game_lists.append(temp_game_list)
                message = ""
                common_games_list = get_common_elements_in_lists(game_lists)
                for game in common_games_list:
                    game_url = f"https://store.steampowered.com/api/appdetails?appids={game}&cc=fr&l=fr"
                    game_info = requests.get(game_url).text
                    game_info = json.loads(game_info)
                    try:
                        game_info = game_info[str(game)]["data"]
                        if game_info["type"] == "game": 
                            if (str(game_info["categories"]).find("{'id': 36,") != -1
                                or str(game_info["categories"]).find("{'id': 38,") != -1
                                or str(game_info["categories"]).find("{'id': 1,") != -1):
                                
                                message += f"{game_info['name']}  \n "
                    except:
                        print(game)
                        
                await self.bot.send_dm(ctx.author_id,message)
                    
            else:
                await self.bot.send_dm(ctx.author_id,"Not All users listed are registered, use !list_users to get the list of registered users")
        else:
            # Send a message to the user if the token is expired
            await self.bot.send_dm(ctx.author_id,"Token is expired contact an admin if urgent")

    """
    [help]|!list_users|list the registered users|!list_users | the list of registered user will be sent to you in dm. ***This command can be used in bot DM***
    """
    @prefixed_command(name="list_users")
    async def list_users(self,ctx: PrefixedContext):
        list_message = "here is the users curently registered\n"
        with open(SCRIPT_PATH + '/register.csv',"r") as f:
            for line in f.readlines():
                list_message += "<@" + line.split(",")[0] + ">\n"
        await self.bot.send_dm(ctx.author_id,list_message)
        
        