# In src/familybot/web/routes/__init__.py
"""
Web UI route modules.

Import all routers here so api.py can do a single
    from familybot.web.routes import all_routers
    for r in all_routers: app.include_router(r)
"""

from . import (
    routes_admin as admin,
    routes_cache as cache,
    routes_config as config,
    routes_games as games,
    routes_logs as logs,
    routes_pages as pages,
    routes_status as status,
    routes_wishlist as wishlist,
)

# Ordered so page routes (catch-all /) come last
all_routers = [
    status.router,
    cache.router,
    games.router,
    wishlist.router,
    config.router,
    admin.router,
    logs.router,
    pages.router,  # HTML page routes last — avoids shadowing API paths
]
