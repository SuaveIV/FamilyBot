# In src/familybot/lib/user_repository.py

import logging

from familybot.lib.database import get_db_connection

logger = logging.getLogger(__name__)


def get_steam_id_from_friendly_name(friendly_name: str) -> str | None:
    """Retrieves the SteamID associated with a given friendly name from the family_members table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT steam_id FROM family_members WHERE friendly_name = ?",
            (friendly_name,),
        )
        result = cursor.fetchone()
        if result:
            return result["steam_id"]
        return None
    except Exception as e:
        logger.error(f"Error retrieving SteamID for friendly name {friendly_name}: {e}")
        return None


def get_steam_id_from_discord_id(discord_id: str) -> str | None:
    """Retrieves the SteamID associated with a given Discord ID.
    Checks family_members table first (for config-driven members with discord_id set),
    then falls back to users table (for !register users)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # First check family_members table (config-driven members with discord_id)
        cursor.execute(
            "SELECT steam_id FROM family_members WHERE discord_id = ?", (discord_id,)
        )
        result = cursor.fetchone()
        if result:
            return result["steam_id"]

        # Fall back to users table (!register users)
        cursor.execute("SELECT steam_id FROM users WHERE discord_id = ?", (discord_id,))
        result = cursor.fetchone()
        if result:
            return result["steam_id"]

        return None
    except Exception as e:
        logger.error(f"Error retrieving SteamID for Discord ID {discord_id}: {e}")
        return None
