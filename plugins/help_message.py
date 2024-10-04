from interactions import *
from string import Template
import os
from lib.token_manager import *
from lib.utils import *
from config import *

class help_message(Extension):
    def __init__(self,bot):
        print("Help Message Plugin loaded")
    
    async def write_help(self):
        help_channel = await self.bot.fetch_channel(HELP_CHANNEL_ID)
        pinned_messages = await help_channel.fetch_pinned_messages()
        full_help_message = "# __Command Usage__ \n"
        command_template = Template("""
### ${name}
${description}
```${usage}```  
${comment}
""")
        for file in os.listdir(PLUGIN_PATH):
            if ".py" in file:
                filename_added = False
                with open(PLUGIN_PATH+file,"r") as f:
                    for lines in f.readlines():
                        if "[help]" in lines and "if \"[help]\"" not in lines:
                            if not filename_added:
                                full_help_message += f"## __{file}__"
                                filename_added = True
                            help = lines.split("|")
                            data = {
                            'name' : help[1],
                            'description' : help[2],
                            'usage' : help[3],
                            'comment' : help[4]
                            }
                            full_help_message += command_template.substitute(data)

        if len(pinned_messages) == 0:                                        
            help_message_id = await help_channel.send(full_help_message)
            await help_message_id.pin()
        else:
            await pinned_messages[len(pinned_messages)-1].edit(content=full_help_message)
        
    @listen()
    async def on_startup(self):
        await self.write_help()
        print("--Help Message created/modified")
        