# In src/familybot/lib/user_repository.py

import logging
import sqlite3

from familybot.config import FAMILY_USER_DICT
from familybot.lib.database import (
    _has_migration_run,
    get_db_connection,
    get_write_connection,
)
from steam.steamid import SteamID

logger = logging.getLogger(__name__)


def _parse_family_config_entry(value) -> tuple[str, str | None]:
    """Parse a family config entry value into (friendly_name, discord_id).

    Supports two config formats:
    - Old format (flat string): "Friendly Name" -> ("Friendly Name", None)
    - New format (dict): {"name": "Friendly Name", "discord_id": 123} -> ("Friendly Name", 123)
    """
    if isinstance(value, str):
        return value, None
    discord_id = value.get("discord_id")
    return value["name"], str(discord_id) if discord_id is not None else None


def sync_family_members_from_config():
    """Synchronizes family members from config.yml into the family_members database table.
    This ensures that members defined in the configuration are always present in the DB.

    Supports two config formats:
    - Old format (flat string): "steam_id": "Friendly Name"
    - New format (dict): "steam_id": {"name": "Friendly Name", "discord_id": 123456789}

    When using the legacy string format, preserves any existing discord_id from the database
    rather than clobbering it to NULL.
    """
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()

            for steam_id, value in FAMILY_USER_DICT.items():
                friendly_name, discord_id = _parse_family_config_entry(value)

                # For legacy string format (discord_id is None), preserve existing discord_id
                if discord_id is None:
                    cursor.execute(
                        "SELECT discord_id FROM family_members WHERE steam_id = ?",
                        (steam_id,),
                    )
                    existing = cursor.fetchone()
                    if existing and existing["discord_id"]:
                        discord_id = existing["discord_id"]

                cursor.execute(
                    "INSERT OR REPLACE INTO family_members (steam_id, friendly_name, discord_id) VALUES (?, ?, ?)",
                    (steam_id, friendly_name, discord_id),
                )
                logger.debug(
                    "Synced family member: '%s' (Steam ID: %s, Discord ID: %s).",
                    friendly_name,
                    steam_id,
                    discord_id,
                )

            conn.commit()
            logger.info("Family members synchronized from config.yml to database.")
    except Exception as e:
        logger.error(f"Error synchronizing family members from config: {e}")


def _migrate_family_members_from_config(conn: sqlite3.Connection) -> None:
    """Helper: migrate family members from config.yml under an existing write connection."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM migrations WHERE name = ?",
        ("family_members_from_config",),
    )
    if cursor.fetchone() is not None:
        logger.debug(
            "Database: Migration 'family_members_from_config' already applied. Skipping."
        )
        return

    if FAMILY_USER_DICT:
        logger.info(
            "Database: Migration 'family_members_from_config' not found. Migrating from config.yml."
        )
        config_members_to_insert = []
        for steam_id, value in FAMILY_USER_DICT.items():
            friendly_name, discord_id = _parse_family_config_entry(value)
            config_members_to_insert.append((steam_id, friendly_name, discord_id))

        if config_members_to_insert:
            cursor.executemany(
                "INSERT OR IGNORE INTO family_members (steam_id, friendly_name, discord_id) VALUES (?, ?, ?)",
                config_members_to_insert,
            )
            conn.commit()
            logger.info(
                f"Database: Migrated {len(config_members_to_insert)} family members from config.yml."
            )
        else:
            logger.info(
                "Database: No family members found in config.yml for migration."
            )
    else:
        logger.debug(
            "Database: config.yml is empty. Skipping family members migration."
        )

    cursor.execute(
        "INSERT OR IGNORE INTO migrations (name, applied_at) VALUES (?, STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))",
        ("family_members_from_config",),
    )
    conn.commit()


def load_family_members_from_db() -> dict:
    """
    Loads family member data (steam_id: friendly_name) from the database,
    performing a one-time migration from config.yml if necessary.
    """
    members = {}

    # Check and run migration in a single write transaction to avoid TOCTOU race
    if not _has_migration_run("family_members_from_config"):
        with get_write_connection() as write_conn:
            # Re-check under the write lock to handle concurrent startup
            cursor = write_conn.cursor()
            cursor.execute(
                "SELECT 1 FROM migrations WHERE name = ?",
                ("family_members_from_config",),
            )
            if cursor.fetchone() is None:
                _migrate_family_members_from_config(write_conn)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT steam_id, friendly_name FROM family_members")
        for row in cursor.fetchall():
            steam_id = row["steam_id"]
            friendly_name = row["friendly_name"]
            # Basic validation for SteamID64: must be 17 digits and start with '7656119'
            try:
                sid = SteamID(steam_id)
                if sid.is_valid():
                    members[str(sid.as_64)] = friendly_name
                else:
                    logger.warning(
                        f"Database: Invalid SteamID '{steam_id}' found for user '{friendly_name}'. Skipping this entry."
                    )
            except Exception:
                logger.warning(
                    f"Database: Invalid SteamID format '{steam_id}' for user '{friendly_name}'. Skipping this entry."
                )
        logger.debug(f"Loaded {len(members)} valid family members from database.")
    except sqlite3.Error as e:
        logger.error(f"Error reading family members from DB: {e}")

    return members


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
