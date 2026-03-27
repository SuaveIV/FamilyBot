"""Cache management operations for the FamilyBot."""

from typing import Any

from familybot.lib.database import get_write_connection
from familybot.lib.logging_config import get_logger

logger = get_logger("cache_service")


async def purge_game_details_cache() -> dict[str, Any]:
    """Purge the game details cache table.

    Returns:
        Dict with success status and message indicating number of entries deleted.
    """
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM game_details_cache")
            cache_count = cursor.fetchone()[0]

            cursor.execute("DELETE FROM game_details_cache")
            conn.commit()

        logger.info(f"Admin purged game details cache: {cache_count} entries deleted")
        return {
            "success": True,
            "message": f"Cache purge complete! Deleted {cache_count} cached game entries.\n\nNext steps:\n- Run populate-database to rebuild cache with USD pricing and new boolean fields.",
        }
    except Exception as e:
        logger.error(f"Error purging game details cache: {e}", exc_info=True)
        return {"success": False, "message": f"Error purging cache: {e}"}


async def purge_itad_cache() -> dict[str, Any]:
    """Purge the ITAD price cache and Steam-ITAD mapping cache tables.

    Returns:
        Dict with success status and message indicating number of entries deleted.
    """
    try:
        with get_write_connection() as conn:
            cursor = conn.cursor()

            # Get counts before deletion
            cursor.execute("SELECT COUNT(*) FROM itad_price_cache")
            price_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM steam_itad_mapping")
            mapping_count = cursor.fetchone()[0]

            # Delete both tables
            cursor.execute("DELETE FROM itad_price_cache")
            cursor.execute("DELETE FROM steam_itad_mapping")
            conn.commit()

        logger.info(
            f"Admin purged ITAD cache: {price_count} price entries and {mapping_count} mapping entries deleted"
        )
        return {
            "success": True,
            "message": f"Price cache purge complete! Deleted {price_count} price entries and {mapping_count} mapping entries.\n\nNext steps:\n- Run populate-prices to rebuild price cache.",
        }
    except Exception as e:
        logger.error(f"Error purging ITAD cache: {e}", exc_info=True)
        return {"success": False, "message": f"Error purging price cache: {e}"}
