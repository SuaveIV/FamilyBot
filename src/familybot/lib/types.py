# In src/familybot/lib/types.py

import asyncio
from typing import Protocol, List, Union, LiteralString # Import necessary types

# Import core interactions types that might be part of the protocol's methods' signatures
from interactions import BaseChannel, User, Message, Client, GuildText # Add other types if needed

# Discord API Constants
DISCORD_MESSAGE_LIMIT = 1950  # Maximum characters allowed in a Discord message (with safety buffer)
DISCORD_EMBED_LIMIT = 6000   # Maximum characters allowed in a Discord embed

class FamilyBotClient(Protocol):
    """
    A protocol defining the expected methods and attributes on the bot client.
    This helps type checkers like Pylance understand the bot's interface,
    especially for dynamically added methods.
    """
    # Core interactions.py attributes
    token: str
    is_connected: bool
    loop: asyncio.AbstractEventLoop

    # Core interactions.py methods that plugins might call
    async def fetch_channel(self, channel_id: int) -> BaseChannel: ...
    async def fetch_user(self, user_id: int) -> User: ...
    def get_channel(self, channel_id: int) -> BaseChannel: ...
    def load_extension(self, extension: str) -> None: ...
    def start(self) -> None: ...
    
    # Dynamically added methods from FamilyBot.py
    async def send_to_channel(self, channel_id: int, message: str) -> None: ...
    async def send_log_dm(self, message: str) -> None: ...
    async def send_dm(self, discord_id: int, message: str) -> None: ...
    async def edit_msg(self, chan_id: int, msg_id: int, message: str) -> None: ...
    async def get_pinned_message(self, chan_id: int) -> List[Message]: ...
