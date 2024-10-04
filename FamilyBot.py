# Import necessary libraries
import os
# from interactions.models.discord import user
from interactions import *
from interactions.ext import prefixed_commands
from interactions.ext import *
from config import *
from lib.token_manager import *

# replace "exts" with your folder name
def get_plugins(directory: str) -> list:
    plugin_list = []
    dir_name = directory.split("/")[len(directory.split("/"))-2]
    try:
        for file in os.listdir(directory):
            if ".py" in file:
                plugin_name = dir_name + "." + file.replace(".py","")
                plugin_list.append(plugin_name)
        return plugin_list
    except FileNotFoundError:
        print(f"Dossier {directory} non trouvé")
        return None
    except Exception as e:
        print(f"Erreur lors du lecture du dossier : {e}")
        return None

# Exemple de utilisation
plugin_list = get_plugins(PLUGIN_PATH)

client = Client(token=DISCORD_API_KEY,intents=Intents.ALL,)
prefixed_commands.setup(client,default_prefix="!")

# client.load_extension("exts.epicgames")
for plugin in plugin_list :
    client.load_extension(plugin)

async def send_to_channel(channel_id: int,message:str) -> None:
    channel = await client.fetch_channel(channel_id)
    await channel.send(message)

async def send_log_dm(message: str) -> None:
    # Fetch the user to send the message to
    user = await client.fetch_user(ADMIN_DISCORD_ID)
    # Get the current date and time
    now = datetime.now()
    now = now.strftime("%d/%m/%y %H:%M:%S")
    # Send the message with the current date and time
    await user.send(now + " -> " + message)

async def send_dm(discord_id: int,message: str) -> None:
    user = await client.fetch_user(discord_id)
    await user.send(message)

async def edit_msg(chan_id:int, msg_id: int, message: str) -> None:
    channel = client.get_channel(chan_id)
    msg = await channel.fetch_message(msg_id)
       
    await msg.edit(content=message)
     
async def get_pinned_message(chan_id) -> list:
    channel = client.get_channel(chan_id)
    pinned_messages = await channel.fetch_pinned_messages()
    return pinned_messages
    
    
client.send_log_dm = send_log_dm
client.send_to_channel = send_to_channel
client.send_dm = send_dm
client.edit_msg = edit_msg
client.get_pinned_message = get_pinned_message


@listen()
async def on_startup():
    print("Bot is ready!")
    start_webSocket_Server()
    await send_log_dm("bot ready")
        
# Run the bot
client.start()