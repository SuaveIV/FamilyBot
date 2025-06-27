# FastAPI application for FamilyBot Web UI

import os
import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from familybot.config import PROJECT_ROOT, WEB_UI_HOST, WEB_UI_PORT
from familybot.lib.database import (
    get_db_connection, get_cached_game_details, get_cached_family_library,
    get_cached_wishlist, cleanup_expired_cache
)
from familybot.web.models import (
    BotStatus, GameDetails, FamilyMember, LogEntry, CacheStats,
    CommandRequest, CommandResponse, ConfigData, WishlistItem, RecentActivity
)

logger = logging.getLogger(__name__)

# Global variables to track bot state
_bot_client = None
_bot_start_time = None
_last_activity = None

def set_bot_client(client):
    """Set the bot client reference for the web API"""
    global _bot_client, _bot_start_time
    _bot_client = client
    _bot_start_time = datetime.utcnow()

def update_last_activity():
    """Update the last activity timestamp"""
    global _last_activity
    _last_activity = datetime.utcnow()

# Create FastAPI app
app = FastAPI(
    title="FamilyBot Web UI",
    description="Web interface for FamilyBot Discord bot",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://{WEB_UI_HOST}:{WEB_UI_PORT}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup static files and templates
web_dir = Path(__file__).parent
static_dir = web_dir / "static"
templates_dir = web_dir / "templates"

# Create directories if they don't exist
static_dir.mkdir(exist_ok=True)
templates_dir.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))

# Dependency to get database connection
def get_db():
    """Get database connection with thread safety for FastAPI, using the main bot's connection logic.
    
    This function now uses `get_db_connection()` from `familybot.lib.database`, which
    is configured to connect to `bot_data.db` (located in the project root), ensuring
    consistency across the application.
    """
    from familybot.lib.database import get_db_connection
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

# API Routes

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    """Logs viewer page"""
    return templates.TemplateResponse("logs.html", {"request": request})

@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    """Configuration page"""
    return templates.TemplateResponse("config.html", {"request": request})

@app.get("/api/status", response_model=BotStatus)
async def get_bot_status():
    """Get bot status information"""
    global _bot_client, _bot_start_time, _last_activity
    
    uptime = None
    if _bot_start_time:
        uptime_delta = datetime.utcnow() - _bot_start_time
        uptime = str(uptime_delta).split('.')[0]  # Remove microseconds
    
    return BotStatus(
        online=_bot_client is not None,
        uptime=uptime,
        last_activity=_last_activity,
        discord_connected=_bot_client is not None and hasattr(_bot_client, 'is_ready') and _bot_client.is_ready,
        websocket_active=True  # Assume WebSocket is active if bot is running
    )

@app.get("/api/cache/stats", response_model=CacheStats)
async def get_cache_stats(conn=Depends(get_db)):
    """Get cache statistics"""
    cursor = conn.cursor()
    
    stats = {}
    tables = {
        'game_details': 'game_details_cache',
        'user_games': 'user_games_cache',
        'wishlist': 'wishlist_cache',
        'family_library': 'family_library_cache',
        'itad_prices': 'itad_price_cache',
        'discord_users': 'discord_users_cache'
    }
    
    for key, table in tables.items():
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            stats[key] = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            stats[key] = 0
    
    return CacheStats(**stats)

@app.get("/api/family-members", response_model=List[FamilyMember])
async def get_family_members(conn=Depends(get_db)):
    """Get family members list"""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT steam_id, friendly_name, discord_id FROM family_members")
        rows = cursor.fetchall()
        
        return [
            FamilyMember(
                steam_id=row['steam_id'],
                friendly_name=row['friendly_name'],
                discord_id=row['discord_id']
            )
            for row in rows
        ]
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return []

@app.get("/api/family-library", response_model=List[GameDetails])
async def get_family_library(limit: int = 50, conn=Depends(get_db)):
    """Get family library games with details"""
    family_apps = get_cached_family_library()
    if not family_apps:
        return []
    
    games = []
    for app in family_apps[:limit]:
        appid = str(app['appid'])
        game_details = get_cached_game_details(appid)
        
        if game_details:
            games.append(GameDetails(
                appid=appid,
                name=game_details.get('name'),
                type=game_details.get('type'),
                is_free=game_details.get('is_free', False),
                categories=game_details.get('categories', []),
                price_data=game_details.get('price_data'),
                is_multiplayer=game_details.get('is_multiplayer', False),
                is_coop=game_details.get('is_coop', False),
                is_family_shared=game_details.get('is_family_shared', False)
            ))
    
    return games

@app.get("/api/wishlist", response_model=List[WishlistItem])
async def get_wishlist_summary(conn=Depends(get_db)):
    """Get wishlist summary across all family members"""
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT DISTINCT w.appid, w.steam_id, g.name, g.price_data
            FROM wishlist_cache w
            LEFT JOIN game_details_cache g ON w.appid = g.appid
            WHERE w.expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
            ORDER BY g.name
            LIMIT 100
        """)
        rows = cursor.fetchall()
        
        wishlist_items = []
        for row in rows:
            price_data = None
            if row['price_data']:
                import json
                try:
                    price_data = json.loads(row['price_data'])
                except:
                    pass
            
            wishlist_items.append(WishlistItem(
                appid=row['appid'],
                steam_id=row['steam_id'],
                game_name=row['name'],
                price_data=price_data
            ))
        
        return wishlist_items
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return []

@app.get("/api/recent-games", response_model=List[GameDetails])
async def get_recent_games(limit: int = 10, conn=Depends(get_db)):
    """Get recently added games"""
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT s.appid, s.detected_at, g.name, g.type, g.is_free, g.categories, 
                   g.price_data, g.is_multiplayer, g.is_coop, g.is_family_shared
            FROM saved_games s
            LEFT JOIN game_details_cache g ON s.appid = g.appid
            ORDER BY s.detected_at DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        
        games = []
        for row in rows:
            categories = []
            price_data = None
            
            if row['categories']:
                import json
                try:
                    categories = json.loads(row['categories'])
                except:
                    pass
            
            if row['price_data']:
                import json
                try:
                    price_data = json.loads(row['price_data'])
                except:
                    pass
            
            games.append(GameDetails(
                appid=row['appid'],
                name=row['name'],
                type=row['type'],
                is_free=bool(row['is_free']) if row['is_free'] is not None else False,
                categories=categories,
                price_data=price_data,
                is_multiplayer=bool(row['is_multiplayer']) if row['is_multiplayer'] is not None else False,
                is_coop=bool(row['is_coop']) if row['is_coop'] is not None else False,
                is_family_shared=bool(row['is_family_shared']) if row['is_family_shared'] is not None else False
            ))
        
        return games
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return []

@app.get("/api/config", response_model=ConfigData)
async def get_config_data():
    """Get sanitized configuration data"""
    try:
        from familybot.config import (
            DISCORD_API_KEY, ADMIN_DISCORD_ID, EPIC_CHANNEL_ID,
            FAMILY_STEAM_ID, NEW_GAME_CHANNEL_ID,
            WISHLIST_CHANNEL_ID, HELP_CHANNEL_ID,
            IP_ADDRESS
        )
        
        # Count family members
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM family_members")
        family_count = cursor.fetchone()[0]
        conn.close()
        
        return ConfigData(
            discord_configured=bool(DISCORD_API_KEY and ADMIN_DISCORD_ID),
            steam_family_configured=bool(FAMILY_STEAM_ID and NEW_GAME_CHANNEL_ID),
            free_epicgames_configured=bool(EPIC_CHANNEL_ID),
            help_message_configured=bool(HELP_CHANNEL_ID),
            family_members_count=family_count,
            websocket_ip=IP_ADDRESS or "127.0.0.1"
        )
    except Exception as e:
        logger.error(f"Error getting config data: {e}")
        return ConfigData(
            discord_configured=False,
            steam_family_configured=False,
            free_epicgames_configured=False,
            help_message_configured=False,
            family_members_count=0,
            websocket_ip="127.0.0.1"
        )

@app.post("/api/cache/purge", response_model=CommandResponse)
async def purge_cache(cache_type: str = "all"):
    """Purge cache data"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if cache_type == "all":
            tables = ['game_details_cache', 'user_games_cache', 'wishlist_cache', 
                     'family_library_cache', 'itad_price_cache', 'discord_users_cache']
            for table in tables:
                cursor.execute(f"DELETE FROM {table}")
            message = "All cache data purged successfully"
        elif cache_type == "expired":
            cleanup_expired_cache()
            message = "Expired cache data cleaned up successfully"
        else:
            table_map = {
                'games': 'game_details_cache',
                'wishlist': 'wishlist_cache',
                'family': 'family_library_cache',
                'prices': 'itad_price_cache'
            }
            if cache_type in table_map:
                cursor.execute(f"DELETE FROM {table_map[cache_type]}")
                message = f"{cache_type.title()} cache purged successfully"
            else:
                raise HTTPException(status_code=400, detail="Invalid cache type")
        
        conn.commit()
        conn.close()
        update_last_activity()
        
        return CommandResponse(success=True, message=message)
    except Exception as e:
        logger.error(f"Error purging cache: {e}")
        return CommandResponse(success=False, message=f"Error purging cache: {str(e)}")

@app.get("/api/logs", response_model=List[LogEntry])
async def get_logs(limit: int = 100, level: Optional[str] = None):
    """Get recent log entries"""
    # This is a simplified implementation
    # In a real implementation, you'd want to read from log files or a log database
    logs = []
    
    try:
        # Try to read from log files if they exist
        log_dir = Path(PROJECT_ROOT) / "logs"
        if log_dir.exists():
            log_files = sorted(log_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
            
            for log_file in log_files[:3]:  # Read from last 3 log files
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[-limit//3:]  # Get recent lines from each file
                        
                    for line in lines:
                        if line.strip():
                            # Parse log line (simplified)
                            parts = line.strip().split(' - ', 3)
                            if len(parts) >= 3:
                                timestamp_str = parts[0]
                                log_level = parts[1]
                                message = parts[2] if len(parts) == 3 else ' - '.join(parts[2:])
                                
                                if level and log_level.upper() != level.upper():
                                    continue
                                
                                try:
                                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                                except:
                                    timestamp = datetime.utcnow()
                                
                                logs.append(LogEntry(
                                    timestamp=timestamp,
                                    level=log_level,
                                    message=message,
                                    module=log_file.stem
                                ))
                except Exception as e:
                    logger.error(f"Error reading log file {log_file}: {e}")
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
    
    # Sort by timestamp and limit
    logs.sort(key=lambda x: x.timestamp, reverse=True)
    return logs[:limit]

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize web application"""
    logger.info("FamilyBot Web UI starting up...")
    
    # Create static and template directories if they don't exist
    (static_dir / "css").mkdir(exist_ok=True)
    (static_dir / "js").mkdir(exist_ok=True)
    (static_dir / "images").mkdir(exist_ok=True)

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("FamilyBot Web UI shutting down...")
