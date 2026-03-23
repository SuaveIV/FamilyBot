# In src/familybot/web/routes/config.py
"""
Configuration status and family-member listing endpoints.
"""

import logging
import sqlite3

from fastapi import APIRouter, Depends

from familybot.lib.database import get_db_connection
from familybot.web.dependencies import get_db
from familybot.web.models import ConfigData, FamilyMember

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/family-members", response_model=list[FamilyMember])
async def get_family_members(conn=Depends(get_db)):
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT steam_id, friendly_name, discord_id FROM family_members")
        return [
            FamilyMember(
                steam_id=row["steam_id"],
                friendly_name=row["friendly_name"],
                discord_id=row["discord_id"],
            )
            for row in cursor.fetchall()
        ]
    except sqlite3.OperationalError:
        return []


@router.get("/api/config", response_model=ConfigData)
async def get_config_data():
    """Return sanitised configuration status (no secrets)."""
    try:
        from familybot.config import (
            ADMIN_DISCORD_ID,
            DISCORD_API_KEY,
            EPIC_CHANNEL_ID,
            FAMILY_STEAM_ID,
            HELP_CHANNEL_ID,
            IP_ADDRESS,
            NEW_GAME_CHANNEL_ID,
        )

        # Build ConfigData booleans from config values first
        config_data = ConfigData(
            discord_configured=bool(DISCORD_API_KEY and ADMIN_DISCORD_ID),
            steam_family_configured=bool(FAMILY_STEAM_ID and NEW_GAME_CHANNEL_ID),
            free_epicgames_configured=bool(EPIC_CHANNEL_ID),
            help_message_configured=bool(HELP_CHANNEL_ID),
            family_members_count=0,  # Will be updated below
            websocket_ip=IP_ADDRESS or "127.0.0.1",
        )

        # Now try to get family_members_count with its own try/except
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM family_members")
            family_count = cursor.fetchone()[0]
            config_data.family_members_count = family_count
        except Exception:
            logger.exception("Error querying family_members count")
            config_data.family_members_count = 0  # Safe default
        finally:
            conn.close()

        return config_data
    except Exception:
        logger.exception("Error building config response")
        return ConfigData(
            discord_configured=False,
            steam_family_configured=False,
            free_epicgames_configured=False,
            help_message_configured=False,
            family_members_count=0,
            websocket_ip="127.0.0.1",
        )
