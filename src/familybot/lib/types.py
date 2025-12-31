# In src/familybot/lib/types.py

from typing import List

# Import core interactions types that might be part of the protocol's methods' signatures
from interactions import Client, Message

# Discord API Constants
DISCORD_MESSAGE_LIMIT = (
    1950  # Maximum characters allowed in a Discord message (with safety buffer)
)
DISCORD_EMBED_LIMIT = 6000  # Maximum characters allowed in a Discord embed


class FamilyBotClient(Client):
    """
    A custom client class that extends interactions.Client with application-specific methods
    that are dynamically added at runtime. This provides type hinting for static analysis.
    """

    # Dynamically added methods from FamilyBot.py
    async def send_to_channel(self, channel_id: int, message: str) -> None:
        raise NotImplementedError

    async def send_log_dm(self, message: str) -> None:
        raise NotImplementedError

    async def send_dm(self, discord_id: int, message: str) -> None:
        raise NotImplementedError

    async def edit_msg(self, chan_id: int, msg_id: int, message: str) -> None:
        raise NotImplementedError

    async def get_pinned_message(self, chan_id: int) -> List[Message]:
        raise NotImplementedError
