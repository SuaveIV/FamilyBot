# Pydantic models for FamilyBot Web API

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BotStatus(BaseModel):
    """Bot status information"""

    online: bool
    uptime: str | None = None
    last_activity: datetime | None = None
    discord_connected: bool
    websocket_active: bool
    token_valid: bool = False  # New field for token status


class GameDetails(BaseModel):
    """Game details from cache"""

    appid: str
    name: str | None = None
    type: str | None = None
    is_free: bool = False
    categories: list[dict[str, Any]] = []
    price_data: dict[str, Any] | None = None
    is_multiplayer: bool = False
    is_coop: bool = False
    is_family_shared: bool = False


class FamilyMember(BaseModel):
    """Family member information"""

    steam_id: str
    friendly_name: str
    discord_id: str | None = None


class LogEntry(BaseModel):
    """Log entry for web UI"""

    timestamp: datetime
    level: str
    message: str
    module: str | None = None


class CacheStats(BaseModel):
    """Cache statistics"""

    game_details: int
    user_games: int
    wishlist: int
    family_library: int
    itad_prices: int
    discord_users: int


class CommandRequest(BaseModel):
    """Request to execute a bot command"""

    command: str
    parameters: dict[str, Any] | None = None


class CommandResponse(BaseModel):
    """Response from bot command execution"""

    success: bool
    message: str
    data: dict[str, Any] | None = None


class ConfigData(BaseModel):
    """Sanitized configuration data for web UI"""

    discord_configured: bool
    steam_family_configured: bool
    free_epicgames_configured: bool
    help_message_configured: bool
    family_members_count: int
    websocket_ip: str


class WishlistItem(BaseModel):
    """Wishlist item with game details"""

    appid: str
    steam_id: str
    game_name: str | None = None
    price_data: dict[str, Any] | None = None


class RecentActivity(BaseModel):
    """Recent bot activity"""

    timestamp: datetime
    activity_type: str  # 'game_added', 'wishlist_update', 'command_executed', etc.
    description: str
    details: dict[str, Any] | None = None
