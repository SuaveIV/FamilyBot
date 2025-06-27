# In src/familybot/lib/types.py

import asyncio
from typing import Protocol, List, Union, LiteralString, TYPE_CHECKING # Import necessary types

# Import core interactions types that might be part of the protocol's methods' signatures
from interactions import BaseChannel, User, Message, Client, GuildText # Add other types if needed

# Discord API Constants
DISCORD_MESSAGE_LIMIT = 1950  # Maximum characters allowed in a Discord message (with safety buffer)
DISCORD_EMBED_LIMIT = 6000   # Maximum characters allowed in a Discord embed

class FamilyBotClientProtocol(Protocol):
    """
    A protocol defining the additional methods that are dynamically added to the bot client.
    This helps type checkers like Pylance understand the bot's extended interface.
    """
    # Dynamically added methods from FamilyBot.py
    async def send_to_channel(self, channel_id: int, message: str) -> None: ...
    async def send_log_dm(self, message: str) -> None: ...
    async def send_dm(self, discord_id: int, message: str) -> None: ...
    async def edit_msg(self, chan_id: int, msg_id: int, message: str) -> None: ...
    async def get_pinned_message(self, chan_id: int) -> List[Message]: ...

# Type alias that represents a Client with the additional FamilyBot methods
# This allows the client to be used wherever a Client is expected while also
# providing type hints for the additional methods
FamilyBotClient = Client
