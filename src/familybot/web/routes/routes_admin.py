# In src/familybot/web/routes/admin.py
"""
Admin action endpoints — database population, cache purges, plugin triggers.
All mutating operations; none require auth beyond being reachable
(deploy behind a firewall or VPN in production).
"""

import logging

from fastapi import APIRouter, HTTPException

from familybot.lib.admin_commands import DatabasePopulator
from familybot.lib.database import (
    load_family_members_from_db,
    purge_family_library_cache,
    purge_wishlist_cache,
)
from familybot.lib.plugin_admin_actions import (
    force_new_game_action,
    force_wishlist_action,
    purge_game_details_cache_action,
)
from familybot.web.models import CommandResponse
from familybot.web.state import update_last_activity

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin")

_VALID_PLUGIN_COMMANDS = {"force_new_game", "force_wishlist", "force_deals"}


# ── Database population ───────────────────────────────────────────────────────


@router.post("/populate-database", response_model=CommandResponse)
async def populate_database_api(
    library_only: bool = False,
    wishlist_only: bool = False,
    rate_limit_mode: str = "normal",
):
    """Warm the cache by scanning family libraries and/or wishlists."""
    populator = DatabasePopulator(rate_limit_mode)
    try:
        family_members = load_family_members_from_db()
        if not family_members:
            raise HTTPException(status_code=400, detail="No family members configured.")

        total = 0

        if not wishlist_only:
            total += await populator.populate_family_library()
            total += await populator.populate_family_libraries(family_members)

        if not library_only:
            total += await populator.populate_wishlists(family_members)

        update_last_activity()
        return CommandResponse(
            success=True, message=f"Database populated. {total} new games cached."
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("populate-database failed: %s", exc, exc_info=True)
        return CommandResponse(
            success=False, message=f"Error populating database: {exc}"
        )
    finally:
        await populator.close()


# ── Cache purges ──────────────────────────────────────────────────────────────


@router.post("/purge-wishlist", response_model=CommandResponse)
async def purge_wishlist_api():
    try:
        purge_wishlist_cache()
        update_last_activity()
        return CommandResponse(success=True, message="Wishlist cache purged.")
    except Exception as exc:
        logger.error("purge-wishlist failed: %s", exc)
        return CommandResponse(success=False, message=str(exc))


@router.post("/purge-family-library", response_model=CommandResponse)
async def purge_family_library_api():
    try:
        purge_family_library_cache()
        update_last_activity()
        return CommandResponse(success=True, message="Family library cache purged.")
    except Exception as exc:
        logger.error("purge-family-library failed: %s", exc)
        return CommandResponse(success=False, message=str(exc))


@router.post("/purge-game-details", response_model=CommandResponse)
async def purge_game_details_api():
    try:
        result = await purge_game_details_cache_action()
        update_last_activity()
        return CommandResponse(success=result["success"], message=result["message"])
    except Exception as exc:
        logger.error("purge-game-details failed: %s", exc)
        return CommandResponse(success=False, message=str(exc))


# ── Plugin actions ────────────────────────────────────────────────────────────


@router.post("/plugin-action", response_model=CommandResponse)
async def plugin_admin_action_api(command_name: str, target_user: str | None = None):
    """Trigger a named plugin action (force_new_game, force_wishlist, force_deals)."""
    if command_name not in _VALID_PLUGIN_COMMANDS:
        raise HTTPException(
            status_code=400, detail=f"Unknown command: {command_name!r}"
        )

    try:
        if command_name == "force_new_game":
            result = await force_new_game_action()
        elif command_name == "force_wishlist":
            result = await force_wishlist_action()
        elif command_name == "force_deals":
            from familybot.lib.plugin_admin_actions import force_deals_action

            result = await force_deals_action(target_friendly_name=target_user)
        else:
            result = {"success": False, "message": "Unhandled command"}

        update_last_activity()
        return CommandResponse(success=result["success"], message=result["message"])

    except Exception as exc:
        logger.error("plugin-action %r failed: %s", command_name, exc, exc_info=True)
        return CommandResponse(
            success=False, message=f"Error running {command_name}: {exc}"
        )
