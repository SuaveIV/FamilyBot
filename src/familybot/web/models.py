# Pydantic models for FamilyBot Web API

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class BotStatus(BaseModel):
    """Bot status information"""
    online: bool
    uptime: Optional[str] = None
    last_activity: Optional[datetime] = None
    discord_connected: bool
    websocket_active: bool
    token_valid: bool = False # New field for token status

class GameDetails(BaseModel):
    """Game details from cache"""
    appid: str
    name: Optional[str] = None
    type: Optional[str] = None
    is_free: bool = False
    categories: List[Dict[str, Any]] = []
    price_data: Optional[Dict[str, Any]] = None
    is_multiplayer: bool = False
    is_coop: bool = False
    is_family_shared: bool = False

class FamilyMember(BaseModel):
    """Family member information"""
    steam_id: str
    friendly_name: str
    discord_id: Optional[str] = None

class LogEntry(BaseModel):
    """Log entry for web UI"""
    timestamp: datetime
    level: str
    message: str
    module: Optional[str] = None

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
    parameters: Optional[Dict[str, Any]] = None

class CommandResponse(BaseModel):
    """Response from bot command execution"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

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
    game_name: Optional[str] = None
    price_data: Optional[Dict[str, Any]] = None

class RecentActivity(BaseModel):
    """Recent bot activity"""
    timestamp: datetime
    activity_type: str  # 'game_added', 'wishlist_update', 'command_executed', etc.
    description: str
    details: Optional[Dict[str, Any]] = None
