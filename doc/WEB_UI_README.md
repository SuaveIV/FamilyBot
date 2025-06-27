# FamilyBot Web UI Documentation

This document provides comprehensive documentation for the FamilyBot Web UI, a modern browser-based interface for managing and monitoring your Discord bot.

## Table of Contents

- [Introduction](#introduction)
- [Features Overview](#features-overview)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [User Interface Guide](#user-interface-guide)
- [Theme System](#theme-system)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Introduction

The FamilyBot Web UI is a FastAPI-powered web dashboard that provides a modern, responsive interface for managing your Discord bot. It offers real-time monitoring, log management, configuration viewing, and cache control capabilities through an intuitive web browser interface.

### Key Benefits

- **Real-time Monitoring**: Live bot status updates and system health metrics
- **Advanced Log Management**: Filter, search, and export logs with ease
- **Theme Customization**: 16+ professional themes including comprehensive dark mode support
- **Mobile Responsive**: Works seamlessly on desktop, tablet, and mobile devices
- **Cache Control**: Web-based cache management and statistics
- **Configuration Help**: Built-in setup guides and configuration templates

## Features Overview

### Dashboard Page

The main dashboard provides an at-a-glance view of your bot's status and activity:

- **Bot Status Panel**: Online/offline status, uptime, Discord connection, and WebSocket status
- **Cache Statistics**: Real-time cache counts for game details, user games, wishlist, family library, price data, and Discord users
- **Recent Games**: Latest games added to the family library
- **Family Members**: Overview of configured family members and their Discord linkage status
- **Wishlist Summary**: Current wishlist items with price information

### Log Viewer Page

Advanced log management with professional-grade features:

- **Real-time Log Streaming**: Live log updates with auto-refresh capability
- **Advanced Filtering**: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **Search Functionality**: Real-time search across log messages, levels, and modules
- **Export Capability**: Download logs as text files for external analysis
- **Log Level Highlighting**: Color-coded log entries for easy identification
- **Copy to Clipboard**: Individual log entry copying for sharing or analysis

### Configuration Page

Comprehensive configuration overview and management:

- **Configuration Status**: Visual overview of Discord, Steam Family, and plugin configuration status
- **Plugin Status**: Real-time status of all loaded plugins
- **Family Member Management**: View and manage configured family members
- **System Information**: WebSocket server details and system metrics
- **Configuration Templates**: Copy-ready configuration templates with detailed comments
- **Setup Help**: Interactive help system with step-by-step guides

## Installation & Setup

### Prerequisites

The Web UI is automatically included with FamilyBot and requires no additional installation. Ensure you have:

- FamilyBot properly installed and configured
- Python 3.13+ with all dependencies installed
- Network access to the configured host/port

### Automatic Setup

The Web UI starts automatically when you run FamilyBot:

```bash
# Start FamilyBot (Web UI starts automatically)
uv run familybot
```

The web server will be available at `http://127.0.0.1:8080` by default.

### Manual Configuration

If you need to customize the Web UI settings, add the following section to your `config.yml`:

```yaml
# --- Web UI Configuration ---
web_ui:
  enabled: true                    # Enable/disable the Web UI
  host: "127.0.0.1"               # Host to bind the web server to
  port: 8080                      # Port for the web server
  default_theme: "default"        # Default Bootswatch theme
```

## Configuration

### Basic Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `enabled` | `true` | Enable or disable the Web UI completely |
| `host` | `"127.0.0.1"` | IP address to bind the web server to |
| `port` | `8080` | Port number for the web server |
| `default_theme` | `"default"` | Default theme for new users |

### Host Configuration

- **Local Access Only**: `127.0.0.1` (recommended for security)
- **Network Access**: `0.0.0.0` (allows access from other devices on your network)
- **Specific Interface**: Use a specific IP address

### Port Configuration

- **Default**: `8080` (standard development port)
- **Alternative Ports**: `3000`, `5000`, `8000`, `8888` (common alternatives)
- **Custom Ports**: Any available port between 1024-65535

### Security Considerations

- **Local Access**: Keep `host` as `127.0.0.1` for local-only access
- **Firewall**: Ensure your firewall allows the configured port if network access is needed
- **Reverse Proxy**: Consider using nginx or Apache for production deployments

## User Interface Guide

### Navigation

The Web UI features a responsive navigation bar with:

- **FamilyBot Logo**: Returns to dashboard
- **Dashboard**: Main overview page
- **Logs**: Log viewer and management
- **Config**: Configuration and setup help
- **Theme Selector**: Dropdown for theme switching
- **Status Indicator**: Real-time bot online/offline status

### Dashboard Usage

#### Bot Status Panel

- **Green Status**: Bot is online and functioning normally
- **Red Status**: Bot is offline or experiencing issues
- **Refresh Button**: Manually update status information
- **Metrics**: View uptime, Discord connection, and WebSocket status

#### Cache Statistics

- **Real-time Counts**: Live updates of cache entry counts
- **Clean Expired**: Remove only expired cache entries
- **Purge All**: Clear all cache data (requires confirmation)
- **Color Coding**: Visual indicators for cache health

#### Recent Games Section

- **Game Cards**: Visual representation of recently added games
- **Game Metadata**: App ID, type, and special attributes
- **Badges**: Visual indicators for free games, multiplayer, and co-op titles

### Log Viewer Usage

#### Filtering Logs

1. **Log Level Filter**: Select specific log levels to display
2. **Entry Limit**: Choose how many log entries to load (50-500)
3. **Search Box**: Real-time search across all log content
4. **Filter Button**: Apply selected filters
5. **Clear Button**: Reset all filters

#### Log Management

- **Auto-refresh**: Toggle automatic log updates (10-second intervals)
- **Export Logs**: Download current logs as a text file
- **Copy Entries**: Click the copy button on individual log entries
- **Scroll Navigation**: Smooth scrolling through log history

#### Log Level Color Coding

- **ERROR/CRITICAL**: Red background with danger border
- **WARNING**: Yellow background with warning border
- **INFO**: Blue background with info border
- **DEBUG**: Gray background with secondary border

### Configuration Page Usage

#### Configuration Overview

- **Status Cards**: Visual indicators for major configuration areas
- **Plugin Status**: Real-time plugin loading and configuration status
- **Family Members**: Tabular view of configured family members

#### Quick Actions

- **Refresh Configuration**: Reload configuration data
- **Configuration Help**: Open interactive help modal
- **Validate Configuration**: Check configuration integrity (future feature)

#### Configuration Templates

- **Copy Template**: One-click copying of complete configuration templates
- **Commented Examples**: Detailed explanations for each configuration option
- **Setup Guides**: Step-by-step instructions for obtaining API keys and IDs

## Theme System

### Available Themes

The Web UI supports 16+ professional Bootswatch themes:

#### Light Themes

- **Bootstrap Default**: Clean, modern Bootstrap styling
- **Cerulean**: Professional blue theme
- **Cosmo**: Flat, modern design
- **Flatly**: Clean flat design
- **Journal**: Newspaper-inspired theme
- **Litera**: Typography-focused theme
- **Lumen**: Light, airy design
- **Minty**: Fresh green theme
- **Pulse**: Purple accent theme
- **Sandstone**: Warm, earthy tones
- **United**: Orange Ubuntu-inspired theme
- **Yeti**: Clean, minimal design

#### Dark Themes

- **Cyborg**: High-contrast dark theme
- **Darkly**: Professional dark theme
- **Slate**: Modern dark gray theme
- **Solar**: Dark theme with warm accents
- **Superhero**: Dark theme with orange highlights
- **Vapor**: Dark theme with pink accents

### Theme Features

- **Persistent Selection**: Themes are saved to browser localStorage
- **System Preference Detection**: Automatically detects system dark/light mode preference
- **Smooth Transitions**: Animated theme switching
- **Mobile Optimized**: All themes work perfectly on mobile devices
- **High Contrast**: Excellent readability in all themes

### Switching Themes

1. Click the **Theme** dropdown in the navigation bar
2. Browse available themes organized by light/dark categories
3. Click any theme to apply it immediately
4. Your selection is automatically saved for future visits

### Custom Theme Development

The theme system is built on Bootstrap 5.3 and Bootswatch, making it easy to add custom themes:

1. Add your theme URL to the `themes` object in `theme_switcher.js`
2. Include theme metadata (name, preview color, dark mode flag)
3. Test theme compatibility with custom CSS classes

## Troubleshooting

### Common Issues

#### Web UI Won't Start

**Symptoms**: Bot starts but Web UI is not accessible

**Solutions**:

1. Check that `web_ui.enabled` is set to `true` in `config.yml`
2. Verify the port is not in use by another application
3. Check firewall settings for the configured port
4. Review bot logs for Web UI startup errors

#### Cannot Access from Other Devices

**Symptoms**: Web UI works locally but not from other devices

**Solutions**:

1. Change `web_ui.host` from `127.0.0.1` to `0.0.0.0`
2. Ensure firewall allows incoming connections on the configured port
3. Use the correct IP address of the host machine
4. Check network connectivity between devices

#### Themes Not Loading

**Symptoms**: Theme dropdown is empty or themes don't apply

**Solutions**:

1. Check internet connectivity (themes load from CDN)
2. Clear browser cache and localStorage
3. Disable browser extensions that might block external CSS
4. Check browser console for JavaScript errors

#### Log Viewer Not Updating

**Symptoms**: Logs don't appear or don't update in real-time

**Solutions**:

1. Check that the bot is generating logs
2. Verify log file permissions
3. Refresh the page to reload log data
4. Check browser console for API errors

### Performance Optimization

#### Large Log Files

- Use log level filtering to reduce data transfer
- Limit the number of log entries loaded
- Export logs for offline analysis of large datasets
- Consider log rotation settings in the bot configuration

#### Network Latency

- Use a local installation for best performance
- Consider caching strategies for remote deployments
- Optimize theme loading by hosting themes locally

### Browser Compatibility

The Web UI is tested and supported on:

- **Chrome/Chromium**: 90+
- **Firefox**: 88+
- **Safari**: 14+
- **Edge**: 90+

#### Mobile Browsers

- **Chrome Mobile**: Full support
- **Safari Mobile**: Full support
- **Firefox Mobile**: Full support

## Development

### Architecture Overview

The Web UI is built using modern web technologies:

- **Backend**: FastAPI with async/await support
- **Frontend**: Vanilla JavaScript with Bootstrap 5.3
- **Templating**: Jinja2 for server-side rendering
- **Styling**: Bootstrap + Bootswatch themes + custom CSS
- **Data Validation**: Pydantic models for API responses

### File Structure

```bash
src/familybot/web/
├── api.py              # FastAPI application and routes
├── models.py           # Pydantic data models
├── static/
│   ├── css/
│   │   └── style.css   # Custom CSS styles
│   └── js/
│       └── theme_switcher.js  # Theme management
└── templates/
    ├── dashboard.html  # Main dashboard page
    ├── logs.html      # Log viewer page
    └── config.html    # Configuration page
```

### API Endpoints

The Web UI exposes several REST API endpoints:

- `GET /api/status` - Bot status and health metrics
- `GET /api/logs` - Paginated log entries with filtering
- `GET /api/config` - Configuration overview and status
- `GET /api/cache/stats` - Cache statistics
- `POST /api/cache/purge` - Cache management operations
- `GET /api/recent-games` - Recently added games
- `GET /api/family-members` - Family member information
- `GET /api/wishlist` - Wishlist data

### Extending the Web UI

#### Adding New Pages

1. Create a new HTML template in `templates/`
2. Add route handler in `api.py`
3. Update navigation in existing templates
4. Add any required API endpoints

#### Adding New API Endpoints

1. Define Pydantic models in `models.py`
2. Implement route handler in `api.py`
3. Add error handling and validation
4. Update frontend JavaScript to consume the API

#### Custom Styling

1. Add custom CSS to `static/css/style.css`
2. Use Bootstrap-compatible CSS variables
3. Test across all supported themes
4. Ensure mobile responsiveness

### Contributing

When contributing to the Web UI:

1. Follow existing code style and patterns
2. Test across multiple themes and devices
3. Ensure accessibility compliance
4. Add appropriate error handling
5. Update documentation for new features

---

For additional support or questions about the Web UI, please refer to the main FamilyBot documentation or create an issue in the project repository.
