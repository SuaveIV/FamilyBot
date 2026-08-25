# In src/familybot/web/routes/__init__.py
"""Web UI route modules.

Import all routers here so api.py can do a single
    from familybot.web.routes import all_routers
    for r in all_routers: app.include_router(r)
"""

from . import (
    routes_admin as admin,
)
from . import (
    routes_cache as cache,
)
from . import (
    routes_config as config,
)
from . import (
    routes_games as games,
)
from . import (
    routes_logs as logs,
)
from . import (
    routes_pages as pages,
)
from . import (
    routes_status as status,
)
from . import (
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
