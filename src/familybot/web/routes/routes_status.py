# In src/familybot/web/routes/status.py
"""Bot status and health-check endpoints."""

import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter

from familybot.web.models import BotStatus
from familybot.web.state import get_bot_client, get_bot_start_time, get_last_activity

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/status", response_model=BotStatus)
async def get_bot_status():
    """Return live bot status including uptime, Discord connection, and token validity."""
    client = get_bot_client()
    start_time = get_bot_start_time()

    uptime = None
    if start_time:
        uptime = str(datetime.now(UTC) - start_time).split(".")[0]

    token_valid = _check_token_valid()

    return BotStatus(
        online=client is not None,
        uptime=uptime,
        last_activity=get_last_activity(),
        discord_connected=client is not None and hasattr(client, "is_ready") and client.is_ready,
        websocket_active=True,
        token_valid=token_valid,
    )


@router.get("/health")
async def health_check():
    """Lightweight liveness probe."""
    return {"status": "healthy", "timestamp": datetime.now(UTC).isoformat()}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _check_token_valid() -> bool:
    try:
        from familybot.config import PROJECT_ROOT, TOKEN_SAVE_PATH

        token_save_dir = Path(PROJECT_ROOT) / TOKEN_SAVE_PATH
        exp_path = token_save_dir / "token_exp"
        tok_path = token_save_dir / "token"

        if not tok_path.exists() or not exp_path.exists():
            return False

        with exp_path.open() as f:
            exp = float(f.read().strip())

        return datetime.now(UTC).timestamp() < exp
    except Exception as exc:
        logger.debug("Token validity check failed: %s", exc)
        return False
