# In src/familybot/web/routes/logs.py
"""
Log viewing endpoints:
  - GET  /api/logs       — recent log entries from log files
  - WS   /ws/logs        — live log stream via WebSocket
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, WebSocket

from familybot.config import PROJECT_ROOT
from familybot.lib.logging_config import get_web_log_queue
from familybot.web.models import LogEntry

logger = logging.getLogger(__name__)
router = APIRouter()

_LOG_DIR = Path(PROJECT_ROOT) / "logs"


@router.get("/api/logs", response_model=list[LogEntry])
async def get_logs(limit: int = 100, level: str | None = None):
    """Read recent log entries from on-disk log files."""
    logs: list[LogEntry] = []

    if not _LOG_DIR.exists():
        return logs

    log_files = sorted(
        _LOG_DIR.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True
    )

    for log_file in log_files[:3]:
        try:
            with open(log_file, encoding="utf-8") as f:
                lines = f.readlines()[-(limit // 3) :]

            for line in lines:
                entry = _parse_log_line(line.strip(), log_file.stem)
                if entry is None:
                    continue
                if level and entry.level.upper() != level.upper():
                    continue
                logs.append(entry)

        except Exception as exc:
            logger.debug("Could not read log file %s: %s", log_file, exc)

    logs.sort(key=lambda e: e.timestamp, reverse=True)
    return logs[:limit]


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """Stream live log entries to connected clients via WebSocket."""
    await websocket.accept()
    queue = get_web_log_queue()
    try:
        while True:
            if queue is not None:
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=1.0)
                    await websocket.send_text(entry)
                except asyncio.TimeoutError:
                    await websocket.send_text('{"type":"heartbeat"}')
            else:
                await asyncio.sleep(1.0)
                await websocket.send_text('{"type":"heartbeat"}')
    except (asyncio.CancelledError, Exception):
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_log_line(line: str, fallback_module: str) -> LogEntry | None:
    if not line:
        return None
    try:
        data = json.loads(line)
        ts_raw = data.get("asctime", "")
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except Exception:
            ts = datetime.now(timezone.utc)
        return LogEntry(
            timestamp=ts,
            level=data.get("levelname", "INFO"),
            message=data.get("message", ""),
            module=data.get("name"),
        )
    except json.JSONDecodeError:
        pass

    # Plain text fallback
    parts = line.split(" - ", 3)
    if len(parts) >= 3:
        try:
            ts = datetime.fromisoformat(parts[0].replace("Z", "+00:00"))
        except Exception:
            ts = datetime.now(timezone.utc)
        return LogEntry(
            timestamp=ts,
            level=parts[1].strip(),
            message=" - ".join(parts[2:]),
            module=fallback_module,
        )
    return None
