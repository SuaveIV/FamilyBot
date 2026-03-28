# In src/familybot/web/api.py
"""
FamilyBot Web UI — FastAPI application entry point.

Creates the app, wires up middleware and static files, then delegates
all routing to the modules in familybot.web.routes.

FamilyBot.py imports:
    from familybot.web.api import app as web_app
    from familybot.web.api import set_bot_client
Both are re-exported here for backwards compatibility.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from familybot.config import WEB_UI_HOST, WEB_UI_PORT
from familybot.lib.logging_config import setup_web_logging
from familybot.web.routes import routes_admin as route_admin
from familybot.web.routes import routes_cache as route_cache
from familybot.web.routes import routes_common_games as route_common_games
from familybot.web.routes import routes_config as route_config
from familybot.web.routes import routes_games as route_games
from familybot.web.routes import routes_logs as route_logs
from familybot.web.routes import routes_pages as route_pages
from familybot.web.routes import routes_status as route_status
from familybot.web.routes import routes_wishlist as route_wishlist
from familybot.web.state import set_bot_client  # re-exported for FamilyBot.py

__all__ = ["app", "set_bot_client"]

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="FamilyBot Web UI",
    description="Web interface for FamilyBot Discord bot",
    version="1.0.0",
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://{WEB_UI_HOST}:{WEB_UI_PORT}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ──────────────────────────────────────────────────────────────

_web_dir = Path(__file__).parent
_static_dir = _web_dir / "static"
_static_dir.mkdir(exist_ok=True)
(_static_dir / "css").mkdir(exist_ok=True)
(_static_dir / "js").mkdir(exist_ok=True)
(_static_dir / "images").mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(route_status.router)
app.include_router(route_cache.router)
app.include_router(route_games.router)
app.include_router(route_wishlist.router)
app.include_router(route_common_games.router)
app.include_router(route_config.router)
app.include_router(route_admin.router)
app.include_router(route_logs.router)
app.include_router(route_pages.router)  # HTML routes last — avoids shadowing API paths

# ── Lifecycle ─────────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup_event():
    setup_web_logging()


@app.on_event("shutdown")
async def shutdown_event():
    import logging

    logging.getLogger(__name__).info("FamilyBot Web UI shutting down.")
