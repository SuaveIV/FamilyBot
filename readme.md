# Family Bot

This project is a modified version of the original "FamilyBot" created by Chachigo. I have made significant improvements and refactorings to the codebase.
**Original Source:** [Chachigo/FamilyBot](https://github.com/Chachigo/FamilyBot)

## Introduction

Family Bot is a Discord bot primarily designed to notify about new games that are added to the Steam Family library. Plugins can be made to add functionalities using the [interactions.py](https://interactions-py.github.io/interactions.py/) library.

## Project Structure

The project follows a modern Python package structure with the following key components:

```bash
FamilyBot/
├── src/familybot/           # Main bot package
│   ├── FamilyBot.py         # Main bot entry point
│   ├── WebSocketServer.py   # WebSocket server for Token_Sender communication
│   ├── config.py            # Configuration loader
│   ├── lib/                 # Core libraries
│   │   ├── database.py      # Database operations
│   │   ├── types.py         # Type definitions
│   │   ├── utils.py         # Utility functions
│   │   └── logging_config.py # Logging configuration
│   ├── plugins/             # Bot plugins/commands
│   │   ├── steam_family.py  # Steam family functionality
│   │   ├── free_epicgames.py # Epic Games free games
│   │   ├── common_game.py   # Common games between users
│   │   ├── help_message.py  # Dynamic help system
│   │   └── token_sender.py  # Token management plugin
│   ├── web/                 # Web UI components
│   │   ├── api.py           # FastAPI web server
│   │   ├── models.py        # Pydantic data models
│   │   ├── static/          # CSS, JavaScript, and assets
│   │   └── templates/       # HTML templates
├── scripts/                 # Utility scripts
│   ├── populate_database.py # Database population
│   ├── populate_prices.py   # Price data population
│   ├── populate_prices_optimized.py # Optimized price data population
│   ├── populate_prices_async.py # Async price data population
│   └── README.md           # Scripts documentation
├── doc/                    # Documentation and images
│   ├── WEB_UI_README.md    # Web UI documentation
│   └── ROADMAP.md          # Project roadmap
├── logs/                   # Log files (auto-created)
├── config-template.yml     # Main bot configuration template
├── pyproject.toml         # Project dependencies and metadata
├── ATTRIB.md              # Third-party attributions
└── main.py               # Simple entry point (placeholder)
```

## How It Works

FamilyBot consists of several interconnected components:

### Main Bot (`FamilyBot.py`)

- **Discord Bot**: Handles all Discord interactions using the interactions.py library
- **Plugin System**: Automatically loads plugins from the `plugins/` directory, enabling modular and extensible functionality
- **Database Management**: SQLite database for caching game data, wishlists, and user information
- **Command-line Interface**: Supports cache management, database population, and other maintenance operations

### Token Sender Plugin (`plugins/token_sender.py`)

- **Automated Token Extraction**: Uses the Playwright library with Chromium to reliably extract Steam web API tokens
- **Integrated Plugin**: Runs as a plugin within the main bot process, eliminating the need for separate WebSocket communication
- **Enhanced Session Management**: Utilizes explicit storage state saving to ensure reliable and persistent Steam login sessions
- **Admin Commands**: Provides `!force_token` and `!token_status` commands for monitoring and controlling the token extraction process
- **Easy Setup**: Automated browser profile creation with the `scripts/setup_browser.py` script

### Plugin Architecture

- **Modular Design**: Each feature is implemented as a separate plugin
- **Auto-loading**: Plugins are automatically discovered and loaded at startup
- **Extensible**: New functionality can be added by creating new plugin files

### Database System

- **SQLite Backend**: Lightweight, file-based database for efficient data persistence
- **Caching Strategy**: Intelligent caching of Steam API responses to minimize the number of API calls required
- **Performance Optimization**: Pre-populating price data for family wishlist games, enabling faster deal detection during sales periods

### Web UI (`web/`)

- **Modern Interface**: FastAPI-powered web dashboard for comprehensive bot management and monitoring
- **Real-time Monitoring**: Live bot status, cache statistics, recent game activity, family member information, and overall system health metrics
- **Log Management**: Advanced log viewer with powerful filtering, search, and export capabilities
- **Theme Support**: 16+ Bootswatch themes, including comprehensive dark mode options, providing a visually appealing and customizable user experience
- **Cache Control**: Web-based interface for purging various cache types and monitoring cache statistics
- **Configuration Help**: Built-in setup guides and configuration templates to assist users in the initial bot setup
- **Responsive Design**: Mobile-friendly interface that seamlessly adapts to desktop, tablet, and mobile devices

## Installation

To install the bot, clone or unzip the repository archive.

### Requirements

This bot is compatible with **Python 3.13 and above.**
We use `uv` for blazing-fast dependency management and virtual environment creation.

### Dependencies

The project uses the following main dependencies (defined in `pyproject.toml`):

- **discord-py-interactions**: Modern Discord bot framework
- **requests**: HTTP library for API calls
- **playwright**: for automated token extraction
- **PyYAML**: Configuration file parsing
- **tqdm**: Progress bars for long-running operations
- **httpx**: Async HTTP client for improved performance
- **fastapi**: Modern web framework for the Web UI
- **uvicorn**: ASGI server for FastAPI
- **jinja2**: Template engine for HTML rendering
- **pydantic**: Data validation and serialization
- **audioop-lts**: Required for voice support in Discord interactions
- **pylint**: Code linter for maintaining code quality

### Setup

FamilyBot offers two setup methods: the modern `just` command runner (recommended) and legacy platform-specific scripts.

#### Development Environment with `mise`

This project uses `mise` to manage the Python version and ensure a consistent development environment. Before you begin, please install `mise` by following the official instructions:

-   [mise documentation](https://mise.jdx.dev/getting-started.html)

Once `mise` is installed, you can set up the project environment with the following commands:

```bash
# Install the Python version specified in .mise.toml
mise install

# Now you can proceed with the setup using `just`
```

#### Modern Setup with `just` (Recommended)

First, install the `just` command runner:

**Windows:**

```powershell
# Using Scoop (recommended)
scoop install just

# Using Chocolatey
choco install just

# Using Cargo
cargo install just
```

**macOS:**

```bash
# Using Homebrew
brew install just
```

**Linux:**

```bash
# Using Cargo
cargo install just
```

 Or check your distribution's package manager:

```bash
 Ubuntu/Debian: apt install just
 Arch: pacman -S just
 Fedora: dnf install just
```

Then set up FamilyBot:

```bash
# Install python version
mise install

# Complete setup (creates venv, installs dependencies, verifies installation)
just setup

# View all available commands
just --list

# Get help
just help
```

#### Legacy Setup (Platform-Specific Scripts)

If you prefer the traditional approach, you can use the platform-specific scripts. However, it is **highly recommended** to use the `just` command runner for a more streamlined experience.

**For Windows (PowerShell 7):**

```powershell
.\reinstall_bot.ps1
```

**For macOS/Linux (Bash):**

```bash
chmod +x ./reinstall_bot.sh # Make the script executable first
./reinstall_bot.sh
```

### Discord Bot Creation

1. Go to [https://discord.com/developers/applications](https://discord.com/developers/applications) and log in with your Discord account.
2. Click on **New Application** and set the name you want for your bot.
3. In the **"OAuth2" -> "General"** section, set the **"Install Link" to `None`**.
    ![Bot Disable Link](doc/Bot_Disable_Link.png)
4. Navigate to the **"Bot"** section:
    - Disable **"Public Bot"**.
    - Under **"Privileged Gateway Intents"**, enable all intents (currently, only the message content intent is essential, but others may be required in future updates).
    ![Bot Permission1](doc/Bot_Permission1.png)
5. To add the bot to your Discord server, go to **"OAuth2" -> "URL Generator"**:
    - In the "scopes" part, check `bot`.
    - In "Bot Permissions", check `Administrator`.
    - Copy the generated URL at the bottom and open it in a new tab.
    ![Bot Generated Link](doc/Bot_Generated_Link.png)
6. It will ask you to connect and select the server where you want to add the bot.
    ![Bot Add](doc/Bot_Add.png)
7. Grant the administrator permissions by clicking **Authorize**.
8. Finally, to get your bot's token: In the **"Bot"** section, click on **"Reset Token"** and copy the token. Save it temporarily, as you'll need it for configuration.

## Configuration

### Main Bot Configuration (`config.yml`)

The main bot uses `config.yml` for its settings. First, fill in the required data in the `config-template.yml` file located in your **project's root directory** (`FamilyBot/`) and then **rename it to `config.yml`**.

#### Discord IDs

To get Discord IDs (for yourself or channels):

- **User ID:** Enable Developer Mode in Discord's **User Settings -> App Settings -> Advanced**. Then, right-click on a user's profile picture and select "Copy ID".
- **Channel ID:** Right-click on a Discord channel and select "Copy ID".

#### Steam IDs and API Keys

The bot interacts with several Steam APIs. There are two distinct types of Steam keys/tokens you'll encounter:

1. **Steamworks Web API Key:** Used for accessing most public Steam Web API endpoints (e.g., `IPlayerService/GetOwnedGames`, `IWishlistService/GetWishlist`, `IFamilyGroupsService/GetSharedLibraryApps`). This is a developer-specific key.
    - **To Obtain:** Go to [https://steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey). Register a domain (you can use `localhost` for development) and generate your key. This key goes into the `steamworks_api_key` field in your `config.yml`.

2. **Steam Web API Token (`webapi_token`):** This is a client-side token, usually obtained from your browser session, and is specifically used by the `token_sender` plugin for actions that might mimic browser interaction. This token is *automatically collected* by the `token_sender` plugin. You don't need to manually put this into `config.yml`.

#### Steam Family ID

To get your Steam Family ID:

1. Use a site like [https://steamapi.xpaw.me/](https://steamapi.xpaw.me/).
2. Fill in the "Token" and "Steam ID" fields on this site (you'll need a Steamworks Web API Key for the "Token" field for `xpaw.me` to function).
3. For your Steam ID (SteamID64): Go to [https://steamdb.info/calculator/](https://steamdb.info/calculator/), paste your profile URL, and your Steam ID will be displayed.
    ![Steam ID](doc/Steam_ID.png)
4. After the values are filled on `xpaw.me`, navigate to [https://steamapi.xpaw.me/#IFamilyGroupsService/GetFamilyGroupForUser](https://steamapi.xpaw.me/#IFamilyGroupsService/GetFamilyGroupForUser) and click "Execute".
5. Your Family ID will be displayed in quotes.
6. To get other family user IDs (SteamID64s), use [https://steamdb.info/calculator/](https://steamdb.info/calculator/) with their profile URLs.

#### IsThereAnyDeal API Key

1. Create an account on [https://isthereanydeal.com/](https://isthereanydeal.com/).
2. Once logged in, go to [https://isthereanydeal.com/apps/my/](https://isthereanydeal.com/apps/my/) and create a new application.
3. Copy the API key displayed there.
    ![ITAD API KEY](doc/ITAD_API_KEY.png)

## Quick Start with `just` (Recommended)

If you have `just` and `mise` installed, here's the fastest way to get FamilyBot running:

```bash
# Install python version
mise install

# Complete setup and run
just setup
just setup-browser  # First-time only: set up Steam login
just run

# View all available commands
just --list

# Common development tasks
just lint            # Check code quality with ruff
just format          # Format code with ruff
just populate-db     # Set up database
just purge-cache     # Clear cache when needed
just logs            # View real-time logs
just status          # Check bot status
```

### `just` Command Reference

**Setup & Installation:**

- `just setup` - Complete development environment setup
- `just reinstall` - Clean reinstall (removes .venv and rebuilds)
- `just verify-setup` - Verify installation is working
- `just update-playwright` - Update Playwright and browser binaries

**Running the Bot:**

- `just run` - Start FamilyBot (recommended method)
- `just setup-browser` - Set up Steam login (first-time only)
- `just test-token` - Test token extraction functionality
- `just diagnose-token` - Run detailed token diagnostics
- `just force-token` - Force immediate token update

**Cache Management:**

- `just purge-cache` - Clear game details cache
- `just purge-wishlist` - Clear wishlist cache
- `just purge-family-library` - Clear family library cache
- `just purge-all-cache` - Clear all cache data

**Database Operations:**

- `just populate-db` - Populate database with game data
- `just populate-prices` - Standard price population
- `just populate-prices-fast` - Optimized price population (6-10x faster)
- `just populate-prices-turbo` - Async price population (15-25x faster)
- `just import-json` - Import data from JSON file
- `just convert-json` - Convert Steamworks JSON to FamilyBot format
- `just inspect-db` - Inspect database structure
- `just backup-db` - Backup database

**Code Quality:**

- `just lint` - Run ruff linter
- `just format` - Format code with ruff
- `just check` - Run all quality checks
- `just fix` - Auto-fix and format code

**Development:**

- `just logs` - View real-time logs
- `just status` - Check bot configuration status
- `just bump-patch` - Bump patch version
- `just help` - Show detailed help
- `just debug-deals` - Debug deals detection logic

**Migration:**

- `just migrate-from-legacy` - Show migration guide from old scripts
- `just install-just-help` - Show `just` installation instructions

## Running the Bot

### Token Sender Setup (First Time Only)

Before running the bot for the first time, you need to set up the Steam login session for the token sender plugin:

**Using `just` (Recommended):**

```bash
just setup-browser
```

**Using direct command:**

```bash
uv run python scripts/setup_browser.py
```

This will:

1. Open a Chromium browser window
2. Navigate to Steam login page
3. Allow you to log into Steam manually
4. Save your login session for the token sender plugin

### Running the Main Bot

The main entry point is `src/familybot/FamilyBot.py`. The token sender now runs as an integrated plugin, so you only need to start one process.

**Note:** The recommended way to run the bot and other scripts is by using the `just` commands. The `justfile` is configured to use `mise` to ensure the correct Python version is used.

**Using `just` (Recommended):**

```bash
# Start the bot
just run

# Check bot status
just status

# View logs in real-time
just logs
```

**Using Script Aliases:**

```bash
# Run the bot (works on all platforms)
uv run familybot

# Set up browser profile with Steam login
uv run familybot-setup

# Test token extraction functionality
uv run familybot-test
```

### Stopping the Bot

To stop the bot, go to its terminal window and press `Ctrl+C`. The bot has graceful shutdown handling implemented.

## Utility Scripts

The `scripts/` directory contains a suite of powerful utility scripts for managing the FamilyBot's database, cache, and overall performance. For detailed documentation, see [scripts/README.md](scripts/README.md) and [scripts/PRICE_OPTIMIZATION_README.md](scripts/PRICE_OPTIMIZATION_README.md).

### Database Population Scripts

- **`populate_database.py`** - A comprehensive script that populates the FamilyBot database with game data, wishlists, and family library information without requiring Discord interaction. This script is perfect for initial setup or complete database rebuilds.

#### Price Population Scripts (Performance Optimized)

FamilyBot now includes **three performance tiers** for price data population, each optimized for different use cases. See the [scripts/README.md](scripts/README.md) for a detailed performance comparison.

- **`populate_prices.py`** - **Original** sequential processing (1x speed baseline).
- **`populate_prices_optimized.py`** - **Threading-based optimization** with connection pooling (6-10x faster).
- **`populate_prices_async.py`** - **True async/await processing** (15-25x faster).

### Cache Management Scripts

The cache purge scripts allow you to clear various types of cached data, forcing fresh data retrieval and enabling troubleshooting.

- **`purge_cache.ps1/.sh`** - Purges the game details cache.
- **`purge_wishlist.ps1/.sh`** - Purges the wishlist cache.
- **`purge_family_library.ps1/.sh`** - Purges the family library cache.
- **`purge_all_cache.ps1/.sh`** - Purges ALL cache data.

### Usage Examples

**Using `just` (Recommended):**

```bash
# Complete setup workflow
just setup
just populate-db                    # Populate all data (run after initial setup)

# Price population - choose based on your needs:
just populate-prices                # Standard mode (reliable, slower)
just populate-prices-fast           # Optimized mode (6-10x faster, recommended)
just populate-prices-turbo          # Maximum performance mode (15-25x faster)

# Cache management
just purge-cache                    # Clear game details cache
just purge-wishlist                 # Clear wishlist cache
just purge-family-library           # Clear family library cache
just purge-all-cache                # Clear all caches
```

## Logging System

FamilyBot includes a comprehensive logging system that provides complete visibility into all bot operations, with special focus on private profile detection and error management.

### Log File Structure

All logs are automatically created in the `logs/` directory:

```shell
logs/
├── familybot.log              # Main bot application log (all levels)
├── familybot_errors.log       # Bot errors and critical issues only
├── steam_api.log              # Steam API specific issues (filtered)
├── scripts/
│   ├── populate_database.log  # Database population script logs
│   ├── populate_prices.log    # Price population script logs
│   ├── script_errors.log      # Combined script error log
│   └── [other script logs]    # Individual script logs
└── archived/                  # Auto-rotated old logs
```

### Key Features

- **Automatic Log Rotation**: Main logs rotate at 10MB, error logs at 5MB with multiple backups
- **Security-Conscious**: Automatically masks API keys, tokens, and sensitive data
- **Private Profile Detection**: Special logging for Steam private profile issues
- **Performance Tracking**: Built-in timing and success rate monitoring
- **Error Categorization**: API errors, database errors, and private profiles clearly separated

## Features

### Steam Family

This plugin includes all features related to Steam Family:

- Sends a notification when a new game is added to the Family library.
- Compares wishlists to find common games, facilitating price sharing among multiple users who desire the same game.
- `!coop <number>`: A command that returns all multiplayer games in the family library in the given number of copies (or more).
- `!deals`: Check current deals for family wishlist games (shows games on sale or at historical low prices).
- `!force_deals`: Admin command to force check deals and post results to the wishlist channel (limited to 100 games).
- `!force_deals_unlimited`: Admin command to check deals for ALL wishlist games with no limit (family sharing only).
- `!purge_cache`: Admin command to purge game details cache and force fresh USD pricing.
- `!full_library_scan`: Admin command to scan all family members' complete game libraries with rate limiting.
- `!full_wishlist_scan`: Admin command to perform comprehensive wishlist scan of ALL common games.

### Free Games (from freegamefindings.bsky.social)

This plugin monitors `freegamefindings.bsky.social` (Bluesky) for new free game announcements across various platforms (Steam, Epic Games, Amazon Prime Gaming, etc.).

- Sends a notification in a designated channel about new free games. For **Steam games**, notifications are enhanced with rich embeds including game images, descriptions, and original pricing from the Steam Store API.
- `!force_free`: An admin-only command to manually trigger a free game check. The bot responds directly in the channel where the command was invoked. If new Steam games are found, they will be posted with rich embeds.
- `!show_last_free_games`: Displays the last 10 free games identified from the Bluesky feed, with minimal filtering. This command does not affect the bot's tracking of seen games.

### Common Games

Adds the following commands:

- `!register <SteamID>`: Links a Discord account to a Steam ID. (Usable in bot DMs).
- `!common_games @user1 @user2`: Gets multiplayer games common to the sender's Steam library and the tagged users. (Usable in bot DMs).
- `!list_users`: Gets the list of users who have linked their SteamID with their DiscordID using the `!register` command. The list is sent in DM. (Usable in bot DMs).

### Help Message

This plugin dynamically generates a help message for all plugin commands. It automatically extracts command details from docstrings formatted as follows within your plugin Python files:

```python
    """
    [help]|!commandName| Description of what the command does| !commandName Arguments | Comment about the command
    """
```

 This ensures the help message is always up-to-date with your bot's latest features.

### Web UI

The Web UI provides a modern, browser-based interface for managing and monitoring FamilyBot:

- **Dashboard**: Real-time bot status, cache statistics, recent games, family members, and wishlist summary
- **Log Viewer**: Advanced log filtering, search, real-time updates, and export functionality
- **Configuration**: View current settings, plugin status, family member management, and setup help
- **Theme Support**: 16+ Bootswatch themes including multiple dark mode options (Darkly, Cyborg, Slate, Solar, Superhero, Vapor)
- **Cache Management**: Web-based cache purging and statistics monitoring
- **Mobile Responsive**: Works seamlessly on desktop, tablet, and mobile devices

#### Accessing the Web UI

Once the bot is running, the Web UI is automatically available at:

- **Default URL**: `http://127.0.0.1:8080` (or your configured host/port)
- **Configuration**: Customize host, port, and default theme in `config.yml` under the `web_ui` section
- **Auto-start**: The web server starts automatically with the bot (can be disabled in config)

For detailed Web UI documentation, see [doc/WEB_UI_README.md](doc/WEB_UI_README.md).

## Troubleshooting

### Common Issues

1. **Bot won't start**: Check that your `config.yml` is properly configured and all required fields are filled.
2. **Token issues**: Ensure the `token_sender` plugin is configured correctly.
3. **Database errors**: Try running the database population scripts or purging cache.
4. **Permission errors**: Ensure the bot has Administrator permissions in your Discord server.

### Getting Help

- Check the logs in the `logs/` directory for detailed error information
- Review the configuration files for missing or incorrect values
- Ensure all dependencies are properly installed using the reinstall script
