# In src/familybot/web/state.py
"""
Shared mutable state for the FamilyBot web UI.

Kept in a dedicated module so every router can import the same
references without circular dependencies or duplicate globals.
"""

from datetime import datetime, timezone

from familybot.lib.types import FamilyBotClient

_bot_client: FamilyBotClient | None = None
_bot_start_time: datetime | None = None
_last_activity: datetime | None = None


def set_bot_client(client: FamilyBotClient) -> None:
    """Called from FamilyBot.py after the Discord client is created."""
    global _bot_client, _bot_start_time
    _bot_client = client
    _bot_start_time = datetime.now(timezone.utc)


def get_bot_client() -> FamilyBotClient | None:
    return _bot_client


def get_bot_start_time() -> datetime | None:
    return _bot_start_time


def update_last_activity() -> None:
    global _last_activity
    _last_activity = datetime.now(timezone.utc)


def get_last_activity() -> datetime | None:
    return _last_activity
