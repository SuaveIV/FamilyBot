feat: Add comprehensive Web UI with FastAPI backend and Bootstrap frontend

## Summary

Implement a complete web-based interface for FamilyBot management and monitoring, featuring real-time status updates, advanced log management, and extensive theme customization.

## Features Added

- **FastAPI Web Server**: Modern async backend with REST API endpoints
- **Responsive Dashboard**: Real-time bot status, cache stats, recent games, and family overview
- **Advanced Log Viewer**: Filtering, search, export, and real-time streaming capabilities
- **Configuration Interface**: Setup help, plugin status, and family member management
- **Theme System**: 16+ Bootswatch themes including comprehensive dark mode support
- **Mobile Responsive**: Optimized for desktop, tablet, and mobile devices

## Files Added

### Backend

- `src/familybot/web/api.py` - FastAPI application with REST endpoints
- `src/familybot/web/models.py` - Pydantic data models
- `src/familybot/web/__init__.py` - Web module initialization
- `src/familybot/web/routes/__init__.py` - Route module initialization

### Frontend

- `src/familybot/web/templates/dashboard.html` - Main dashboard page
- `src/familybot/web/templates/logs.html` - Log viewer with filtering
- `src/familybot/web/templates/config.html` - Configuration overview
- `src/familybot/web/static/css/style.css` - Custom Bootstrap-compatible styles
- `src/familybot/web/static/js/theme_switcher.js` - Theme management system

### Documentation

- `doc/WEB_UI_README.md` - Comprehensive Web UI documentation
- `ATTRIB.md` - Third-party attributions and licenses
- `LICENSE` - MIT License file

## Files Modified

- `src/familybot/FamilyBot.py` - Integrated web server startup
- `src/familybot/config.py` - Added web UI configuration variables
- `config-template.yml` - Added web UI configuration section
- `readme.md` - Updated with Web UI information and features
- `doc/ROADMAP.md` - Marked Web UI implementation as completed
- `pyproject.toml` - Added FastAPI, Uvicorn, Jinja2, Pydantic dependencies

## Configuration

```yaml
web_ui:
  enabled: true
  host: "127.0.0.1"
  port: 8080
  default_theme: "default"
```

## Access

Web UI available at `http://127.0.0.1:8080` when bot is running.

## Breaking Changes

None - Web UI is optional and disabled by default in existing configurations.

## Dependencies Added

- fastapi>=0.104.0
- uvicorn>=0.24.0
- jinja2>=3.1.0
- pydantic>=2.0.0
