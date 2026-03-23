# FamilyBot Web UI

A browser-based dashboard for monitoring and controlling your FamilyBot instance. Starts automatically alongside the bot and is available at `http://127.0.0.1:8080` by default.

## Table of Contents

- [Pages](#pages)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

---

## Pages

### Dashboard

The main overview. Shows bot status (online/offline, uptime, Discord connection, Steam token validity), cache entry counts for each table, recently detected family library additions, and configured family members.

Cache management buttons live here too — you can clean expired entries or purge everything from the browser without touching the CLI.

### Wishlist

Shows all family wishlist entries as a card grid with Steam cover art. Cards load immediately using the deterministic Steam CDN image URL; any missing game names are resolved in the background via a batch lookup that checks the local cache first, then falls back to the Steam Store API. Resolved names and images are cached permanently so subsequent loads are instant.

Features:

- Filter by family member
- Sort A–Z or by discount size
- Grid and list view toggle
- Games on multiple wishlists appear once, with all interested members shown as badges on the card
- Sale ribbons and strikethrough pricing for discounted games

### Logs

Log viewer with a live WebSocket stream. New log entries appear in real time as the bot runs. You can pause the stream without disconnecting if you need to read something without it scrolling away.

Filtering options: log level, entry limit, and a search box that highlights matches inline. Logs can be exported as a plain text file.

### Config

A read-only view of the current configuration state — which plugins are active, how many family members are configured, and what the WebSocket server IP is. No secrets are exposed.

Also has a copy-ready `config.yml` template and an accordion help section covering Discord IDs, Steam API keys, and channel IDs.

### Admin

Buttons for database operations and plugin actions that would otherwise require running a Discord command. Output appears in a terminal panel on the right.

Available actions:

- Populate database (scan family libraries and wishlists)
- Purge game details / wishlist / family library cache individually
- Force new game check
- Force wishlist refresh
- Force deals check (with optional per-member targeting)

---

## Configuration

```yaml
web_ui:
    enabled: true # Set to false to disable entirely
    host: "127.0.0.1" # Use 0.0.0.0 to allow access from other devices
    port: 8080
```

The `default_theme` key that previously existed in this section is no longer used and can be removed from your `config.yml`.

### Host options

- `127.0.0.1` — local access only (recommended)
- `0.0.0.0` — accessible from other devices on your network
- A specific IP address if you want to bind to a particular interface

### Security

The dashboard has no authentication. Keep `host` as `127.0.0.1` unless you're on a trusted network. If you want to expose it externally, put it behind a reverse proxy (nginx, Caddy) with auth in front of it.

---

## Troubleshooting

### **Web UI won't start**

Check that `web_ui.enabled` is `true` and the port isn't already in use. The bot logs will show the startup error.

### **Can't access from another device**

Change `host` to `0.0.0.0` and make sure your firewall allows the port.

### **Wishlist shows no cover art**

The images come from Steam's CDN directly — `cdn.akamai.steamstatic.com`. If that's blocked on your network the placeholders will stay. Game names still resolve via the local API.

### **Log viewer not updating**

Check the connection indicator in the card header — it shows `● live` when the WebSocket is connected and `● disconnected` if it dropped. It reconnects automatically every 5 seconds.

### **Wishlist shows items but no names**

Names missing from the local cache are fetched in the background after the page loads. If the bot hasn't run a wishlist scan recently (`!force_wishlist` or the 6-hour scheduled task), the game details cache may be empty. Running a scan from the Admin page will populate it.

---

## Development

### Architecture

- **Backend**: FastAPI with async/await
- **Templating**: Jinja2
- **Frontend**: Vanilla JS, no framework dependencies
- **Styling**: Custom CSS design system (Saira + Space Mono, dark theme)
- **Data validation**: Pydantic models

No Bootstrap, no CDN CSS dependencies beyond Font Awesome for icons. The design system lives entirely in `static/css/style.css` and uses CSS custom properties throughout, so it's straightforward to retheme. The fonts Saira (UI) and Space Mono (monospace) are bundled locally under `src/familybot/web/static/fonts/` and loaded via @font-face declarations in `static/css/style.css`. To update these fonts, replace the corresponding .woff2 files in the fonts directory and ensure the @font-face rules in `static/css/style.css` reference the correct filenames.

### File structure

```
src/familybot/web/
├── api.py                  # App setup, middleware, router registration
├── state.py                # Shared bot client reference and activity tracking
├── dependencies.py         # Shared FastAPI dependencies (get_db)
├── models.py               # Pydantic response models
├── routes/
│   ├── __init__.py
│   ├── pages.py            # HTML template responses
│   ├── status.py           # /api/status, /health
│   ├── cache.py            # /api/cache/stats, /api/cache/purge
│   ├── games.py            # /api/family-library, /api/recent-games,
│   │                       #   /api/game-info/batch
│   ├── wishlist.py         # /api/wishlist
│   ├── config.py           # /api/config, /api/family-members
│   ├── admin.py            # /api/admin/*
│   └── logs.py             # /api/logs, /ws/logs
├── static/
│   ├── css/style.css       # Full design system
│   └── js/
│       ├── app.js          # Shared utilities (status polling, toasts,
│       │                   #   cache stats, sidebar)
│       └── admin.js        # Admin panel command handling
└── templates/
    ├── navbar.html         # Sidebar included by all pages
    ├── dashboard.html
    ├── wishlist.html
    ├── logs.html
    ├── config.html
    └── admin.html
```

### API endpoints

| Method | Path                              | Description                           |
| ------ | --------------------------------- | ------------------------------------- |
| GET    | `/api/status`                     | Bot status, uptime, token validity    |
| GET    | `/health`                         | Liveness probe                        |
| GET    | `/api/cache/stats`                | Entry counts per cache table          |
| POST   | `/api/cache/purge`                | Purge cache by type                   |
| GET    | `/api/family-members`             | Configured family members             |
| GET    | `/api/config`                     | Sanitised config status               |
| GET    | `/api/family-library`             | Cached family library games           |
| GET    | `/api/recent-games`               | Recently detected additions           |
| POST   | `/api/game-info/batch`            | Name + cover art for up to 50 appids  |
| GET    | `/api/wishlist`                   | Paginated wishlist with member filter |
| POST   | `/api/admin/populate-database`    | Warm the cache                        |
| POST   | `/api/admin/purge-wishlist`       | Purge wishlist cache                  |
| POST   | `/api/admin/purge-family-library` | Purge family library cache            |
| POST   | `/api/admin/purge-game-details`   | Purge game details cache              |
| POST   | `/api/admin/plugin-action`        | Trigger plugin commands               |
| GET    | `/api/logs`                       | Recent log entries from disk          |
| WS     | `/ws/logs`                        | Live log stream                       |

### Adding a new page

1. Create a template in `templates/` — include `navbar.html` and source `app.js`
2. Add a route in `routes/pages.py`
3. Add a nav item in `templates/navbar.html`
4. If it needs new data, add an endpoint in the appropriate routes module or a new one

### Adding a new API endpoint

1. Add the Pydantic model to `models.py` if needed
2. Add the route to the appropriate module under `routes/`
3. If it needs shared state (bot client, last activity), import from `state.py`
4. If it needs a DB connection, use `Depends(get_db)` from `dependencies.py`

### CSS custom properties

The design system is defined as CSS variables on `:root` in `style.css`. The main ones to know:

```css
--bg           /* page background */
--bg-card      /* card background */
--border       /* default border color */
--accent       /* cyan highlight (#00c8ff) */
--text         /* primary text */
--text-dim     /* secondary text */
--text-muted   /* placeholder / label text */
--green / --yellow / --red   /* status colors */
--font-ui      /* Saira — headings, labels, buttons */
--font-mono    /* Space Mono — IDs, timestamps, code */
```
