# FastAPI application for FamilyBot Web UI

import os
import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Depends, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from familybot.config import PROJECT_ROOT, WEB_UI_HOST, WEB_UI_PORT
from familybot.lib.database import (
    get_db_connection, get_cached_game_details, get_cached_family_library,
    get_cached_wishlist, cleanup_expired_cache, purge_wishlist_cache, purge_family_library_cache
)
from familybot.lib.admin_commands import DatabasePopulator
from familybot.lib.plugin_admin_actions import (
    purge_game_details_cache_action,
    force_new_game_action,
    force_wishlist_action
)
from familybot.lib.logging_config import web_log_queue, setup_web_logging
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
    return templates.TemplateResponse("dashboard.html", {"request": request, "active_page": "dashboard"})

@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    """Logs viewer page"""
    return templates.TemplateResponse("logs.html", {"request": request, "active_page": "logs"})

@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    """Configuration page"""
    return templates.TemplateResponse("config.html", {"request": request, "active_page": "config"})

@app.get("/wishlist", response_class=HTMLResponse)
async def wishlist_page(request: Request):
    """Wishlist page"""
    return templates.TemplateResponse("wishlist.html", {"request": request, "active_page": "wishlist"})

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Admin page"""
    return templates.TemplateResponse("admin.html", {"request": request, "active_page": "admin"})

@app.get("/api/status", response_model=BotStatus)
async def get_bot_status():
    """Get bot status information"""
    global _bot_client, _bot_start_time, _last_activity
    
    uptime = None
    if _bot_start_time:
        uptime_delta = datetime.utcnow() - _bot_start_time
        uptime = str(uptime_delta).split('.')[0]  # Remove microseconds
    
    # Check token validity using the token plugin's logic
    token_valid = False
    try:
        from familybot.config import PROJECT_ROOT, TOKEN_SAVE_PATH
        import os
        
        token_save_dir = os.path.join(PROJECT_ROOT, TOKEN_SAVE_PATH)
        token_file_path = os.path.join(token_save_dir, "token")
        exp_file_path = os.path.join(token_save_dir, "token_exp")
        
        # Check if token files exist and token is not expired
        if os.path.exists(token_file_path) and os.path.exists(exp_file_path):
            with open(exp_file_path, 'r') as f:
                exp_timestamp = float(f.read().strip())
            
            now_timestamp = datetime.utcnow().timestamp()
            token_valid = now_timestamp < exp_timestamp
    except Exception as e:
        logger.error(f"Error checking token status: {e}")
        token_valid = False
    
    return BotStatus(
        online=_bot_client is not None,
        uptime=uptime,
        last_activity=_last_activity,
        discord_connected=_bot_client is not None and hasattr(_bot_client, 'is_ready') and _bot_client.is_ready,
        websocket_active=True,  # Assume WebSocket is active if bot is running
        token_valid=token_valid
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

@app.get("/api/wishlist")
async def get_wishlist_summary(page: int = 1, limit: int = 20, conn=Depends(get_db)):
    """Get paginated wishlist summary across all family members"""
    cursor = conn.cursor()
    offset = (page - 1) * limit
    
    try:
        # Get total count
        cursor.execute("""
            SELECT COUNT(DISTINCT w.appid)
            FROM wishlist_cache w
            WHERE w.expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
        """)
        total_items = cursor.fetchone()[0]

        # Get paginated items
        cursor.execute(f"""
            SELECT DISTINCT w.appid, w.steam_id, g.name, g.price_data
            FROM wishlist_cache w
            LEFT JOIN game_details_cache g ON w.appid = g.appid
            WHERE w.expires_at > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
            ORDER BY g.name
            LIMIT {limit} OFFSET {offset}
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
        
        return {"items": wishlist_items, "total_items": total_items}
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return {"items": [], "total_items": 0}

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

@app.post("/api/admin/populate-database", response_model=CommandResponse)
async def populate_database_api(
    library_only: bool = False,
    wishlist_only: bool = False,
    rate_limit_mode: str = "normal"
):
    """Trigger database population for libraries and/or wishlists."""
    try:
        populator = DatabasePopulator(rate_limit_mode)
        family_members = populator.load_family_members()
        
        total_cached = 0
        if not family_members:
            raise HTTPException(status_code=400, detail="No family members configured.")

        if not wishlist_only:
            total_cached += await populator.populate_family_libraries(family_members)
        
        if not library_only:
            total_cached += await populator.populate_wishlists(family_members)
        
        await populator.close()
        update_last_activity()
        return CommandResponse(success=True, message=f"Database populated. Total new games cached: {total_cached}")
    except Exception as e:
        logger.error(f"Error populating database: {e}")
        return CommandResponse(success=False, message=f"Error populating database: {str(e)}")

@app.post("/api/admin/purge-wishlist", response_model=CommandResponse)
async def purge_wishlist_api():
    """Purge all entries from the wishlist cache."""
    try:
        purge_wishlist_cache()
        update_last_activity()
        return CommandResponse(success=True, message="Wishlist cache purged successfully.")
    except Exception as e:
        logger.error(f"Error purging wishlist cache: {e}")
        return CommandResponse(success=False, message=f"Error purging wishlist cache: {str(e)}")

@app.post("/api/admin/purge-family-library", response_model=CommandResponse)
async def purge_family_library_api():
    """Purge all entries from the family library cache."""
    try:
        purge_family_library_cache()
        update_last_activity()
        return CommandResponse(success=True, message="Family library cache purged successfully.")
    except Exception as e:
        logger.error(f"Error purging family library cache: {e}")
        return CommandResponse(success=False, message=f"Error purging family library cache: {str(e)}")

@app.post("/api/admin/purge-game-details", response_model=CommandResponse)
async def purge_game_details_cache_api():
    """Purge all entries from the game details cache."""
    try:
        result = await purge_game_details_cache_action()
        update_last_activity()
        return CommandResponse(success=result["success"], message=result["message"])
    except Exception as e:
        logger.error(f"Error purging game details cache via API: {e}")
        return CommandResponse(success=False, message=f"Error purging game details cache: {str(e)}")

@app.post("/api/admin/plugin-action", response_model=CommandResponse)
async def plugin_admin_action_api(command_name: str, target_user: Optional[str] = None):
    """
    Triggers an admin action from a plugin.
    """
    try:
        if command_name == "force_new_game":
            result = await force_new_game_action()
        elif command_name == "force_wishlist":
            result = await force_wishlist_action()
        elif command_name == "force_deals":
            # Import the force_deals function
            from familybot.lib.plugin_admin_actions import force_deals_action
            result = await force_deals_action(target_friendly_name=target_user)
        else:
            raise HTTPException(status_code=400, detail="Invalid plugin admin command.")
        
        update_last_activity()
        return CommandResponse(success=result["success"], message=result["message"])
    except Exception as e:
        logger.error(f"Error executing plugin admin action '{command_name}': {e}")
        return CommandResponse(success=False, message=f"Error executing plugin admin action: {str(e)}")

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
                            import json
                            try:
                                log_data = json.loads(line)
                                log_level = log_data.get("levelname")
                                if level and log_level.upper() != level.upper():
                                    continue
                                
                                logs.append(LogEntry(
                                    timestamp=log_data.get("asctime"),
                                    level=log_level,
                                    message=log_data.get("message"),
                                    module=log_data.get("name")
                                ))
                            except json.JSONDecodeError:
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

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            log_entry = web_log_queue.get()
            await websocket.send_text(log_entry)
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        pass
    finally:
        await websocket.close()

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize web application"""
    setup_web_logging()
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
