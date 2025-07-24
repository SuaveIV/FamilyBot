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
│   └── Token_Sender/        # Legacy token management (deprecated)
│       ├── getToken.py      # Token extraction script
│       └── config-template.yaml # Token sender configuration
├── scripts/                 # Utility scripts
│   ├── populate_database.py # Database population
│   ├── populate_prices.py   # Price data population
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
- **WebSocket Server**: Receives tokens from the Token_Sender component for secure communication
- **Command-line Interface**: Supports cache management, database population, and other maintenance operations

### Token Sender Plugin (`plugins/token_sender.py`)

- **Automated Token Extraction**: Uses the Playwright library with Chromium to reliably extract Steam web API tokens
- **Integrated Plugin**: Runs as a plugin within the main bot process, eliminating the need for separate WebSocket communication
- **Enhanced Session Management**: Utilizes explicit storage state saving to ensure reliable and persistent Steam login sessions
- **Admin Commands**: Provides `!force_token` and `!token_status` commands for monitoring and controlling the token extraction process
- **Easy Setup**: Automated browser profile creation with the `scripts/setup_browser.py` script

### Legacy Token Sender (`Token_Sender/getToken.py`)

- **Deprecated**: Original standalone Selenium-based implementation, preserved for reference purposes only
- **Migration Complete**: The new Token Sender plugin provides all the necessary functionality with significant improvements and enhancements

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
- **selenium**: Web automation for token extraction
- **webdriver-manager**: Automatic WebDriver management
- **websockets**: WebSocket communication between components
- **PyYAML**: Configuration file parsing
- **tqdm**: Progress bars for long-running operations
- **httpx**: Async HTTP client for improved performance
- **fastapi**: Modern web framework for the Web UI
- **uvicorn**: ASGI server for FastAPI
- **jinja2**: Template engine for HTML rendering
- **pydantic**: Data validation and serialization

### Setup

To set up your development environment, navigate to the project's root directory (`FamilyBot/`) in your terminal (PowerShell 7+ recommended on Windows, or Bash on macOS/Linux) and run the appropriate script:

**For Windows (PowerShell 7):**

```powershell
.\reinstall_bot.ps1
```

**For macOS/Linux (Bash):**

```bash
chmod +x ./reinstall_bot.sh # Make the script executable first
./reinstall_bot.sh
```

This script will:

- Create a new Python virtual environment (.venv).
- Install all necessary Python libraries (including interactions.py, selenium, PyYAML, requests, websockets, webdriver_manager) into the virtual environment.
- Ensure the project's internal modules are correctly configured.

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

The bot uses two separate configuration files for its different components.

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

2. **Steam Web API Token (`webapi_token`):** This is a client-side token, usually obtained from your browser session, and is specifically used by the `Token_Sender` bot for actions that might mimic browser interaction (e.g., if you had features related to Steam Points Shop or specific client-side Steam features).

    - **To Get `webapi_token`:** Go to [https://store.steampowered.com/pointssummary/ajaxgetasyncconfig](https://store.steampowered.com/pointssummary/ajaxgetasyncconfig). Log in to Steam in another tab, then refresh the token tab. Copy the `webapi_token` value (in quotes). This token is *automatically collected* by the `Token_Sender` bot using Selenium and sent to the main bot via WebSocket. You don't need to manually put this into `config.yml`.

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

### Token Sender Configuration (`config.yaml`)

The `Token_Sender` bot is a separate Python script (`getToken.py`) located in the `src/familybot/Token_Sender/` subdirectory. It requires:

- **Firefox** (installed on your system).
- **Python 3.13+** (managed by your bot's virtual environment).

#### Configure Firefox for Selenium

Since the `webapi_token` can only be reliably obtained from a browser logged into Steam, `Token_Sender` uses Selenium.

1. You need to create a dedicated Firefox profile. In Firefox's address bar, type **`about:profiles`** and press Enter.
2. Click on **"Create a New Profile"**.
    ![Create Firefox Profile](doc/Create_Firefox_Profile.png)
3. **Note the path of this new profile**, as you will need it for the `Token_Sender`'s configuration.
4. Start this new profile in a new browser window and log in to [Steam](https://store.steampowered.com/).

#### Token Sender Configuration File

The `Token_Sender` bot has its own configuration. First, copy the template file `src/familybot/Token_Sender/config-template.yaml` to `src/familybot/Token_Sender/config.yaml`. Then, fill in the required data in `src/familybot/Token_Sender/config.yaml`:

- **`server_ip`**: The IP address of the main FamilyBot's WebSocket server. Use the same IP address you set for `websocket_server_ip` in the main bot's `config.yml` (e.g., `127.0.0.1` for local).
- **`token_save_path`**: The directory where the `webapi_token` and its expiration timestamp will be saved. We recommend using a relative path like `"tokens/"` (which will create a `FamilyBot/tokens/` folder).
- **`shutdown`**: Set to `true` if you want your computer to shut down after the token is successfully sent (mostly for dedicated systems; set to `false` for development).
- **`firefox_profile_path`**: The **complete path** to the Firefox profile you created in the previous step. Ensure you use **forward slashes (`/`)** or escaped backslashes (`\\`) in the path.

## Running the Bot

### Token Sender Setup (First Time Only)

Before running the bot for the first time, you need to set up the Steam login session for the token sender plugin:

```bash
# Set up browser profile with Steam login (run once)
uv run python scripts/setup_browser.py
```

This will:

1. Open a Chromium browser window
2. Navigate to Steam login page
3. Allow you to log into Steam manually
4. Save your login session for the token sender plugin

### Running the Main Bot

The main entry point is `src/familybot/FamilyBot.py`. The token sender now runs as an integrated plugin, so you only need to start one process.

From the `FamilyBot/` project root directory:

**Option 1: Using Script Aliases (Recommended):**

```bash
# Run the bot (works on all platforms)
uv run familybot

# Set up browser profile with Steam login
uv run familybot-setup

# Test token extraction functionality
uv run familybot-test
```

**Option 2: Direct Python Execution:**

**For Windows (PowerShell 7):**

```powershell
# Activate virtual environment
. .\.venv\Scripts\Activate.ps1

# Run the bot
uv run python .\src\familybot\FamilyBot.py
```

**For macOS/Linux (Bash):**

```bash
# Activate virtual environment
source ./.venv/bin/activate

# Run the bot
uv run python ./src/familybot/FamilyBot.py
```

### Legacy Launch Scripts (For Backward Compatibility)

The old launch scripts are still available but now only start the main bot since the token sender is integrated:

- **For Windows (PowerShell 7):**

    ```powershell
    .\run_bots.ps1
    ```

- **For macOS/Linux (Bash):**

    ```bash
    chmod +x ./run_bots.sh # Make the script executable first
    ./run_bots.sh
    ```

### Command-line Arguments

The main bot (`FamilyBot.py`) supports several command-line arguments for maintenance operations:

```bash
# Cache management operations
uv run python .\src\familybot\FamilyBot.py --purge-cache          # Purge game details cache
uv run python .\src\familybot\FamilyBot.py --purge-wishlist      # Purge wishlist cache
uv run python .\src\familybot\FamilyBot.py --purge-family-library # Purge family library cache
uv run python .\src\familybot\FamilyBot.py --purge-all           # Purge all cache data

# Note: --full-library-scan and --full-wishlist-scan require the bot to be running
# Use Discord commands !full_library_scan and !full_wishlist_scan instead
```

---

**Important Notes:**

- You will need **two separate terminal windows** if you run them manually (one for `FamilyBot.py` and one for `getToken.py`).
- Remember to activate the virtual environment (`. .\.venv\Scripts\Activate.ps1` or `source ./.venv/bin/activate`) in **each terminal window** where you plan to run a bot manually.

---

### Stopping the Bots

To stop the bots, go to their respective terminal windows and press `Ctrl+C`. Both bots have graceful shutdown handling implemented.

## Utility Scripts

The `scripts/` directory contains a suite of powerful utility scripts for managing the FamilyBot's database, cache, and overall performance:

### Database Population Scripts

- **`populate_database.py`** - A comprehensive script that populates the FamilyBot database with game data, wishlists, and family library information without requiring Discord interaction. This script is perfect for initial setup or complete database rebuilds.

#### Price Population Scripts (Performance Optimized)

FamilyBot now includes **three performance tiers** for price data population, each optimized for different use cases:

- **`populate_prices.py`** - **Original** sequential processing (1x speed baseline). Reliable but slower for large datasets.
- **`populate_prices_optimized.py`** - **Threading-based optimization** with connection pooling (6-10x faster). Uses concurrent requests with intelligent rate limiting and connection reuse to minimize data usage.
- **`populate_prices_async.py`** - **True async/await processing** (15-25x faster). Maximum performance with aggressive connection pooling and async I/O for the fastest possible price population.

All scripts pre-populate both Steam Store prices and ITAD historical price data for **family wishlist games only**. This is **essential for maximizing performance during Steam Summer/Winter Sales** when you want to achieve the fastest possible deal detection speeds.

**Performance Comparison:**

| Script | Processing Mode | Concurrency | Expected Speed | Data Usage Reduction |
|--------|----------------|-------------|----------------|---------------------|
| **Original** | Sequential | 1 request | ~1,200 games/hour | Baseline |
| **Optimized** | Threading | 10-20 concurrent | ~8,000-12,000 games/hour | 15-25% reduction |
| **Async** | True Async | 50-100 concurrent | ~20,000-30,000 games/hour | 25-35% reduction |

**Connection Reuse Benefits:**

- **Optimized**: 50 max connections, 20 keepalive connections, 30s expiry
- **Async**: 200 max connections, 100 keepalive connections, 60s expiry
- **Reduced Data Usage**: Persistent connections eliminate redundant TCP handshakes and DNS lookups

### Cache Management Scripts

The cache purge scripts allow you to clear various types of cached data, forcing fresh data retrieval and enabling troubleshooting:

- **`purge_cache.ps1/.sh`** - Purges the game details cache, clearing all cached Steam game information (names, prices, categories, etc.) and forcing fresh USD pricing on the next API calls. This is useful when you want to refresh pricing data or fix any currency-related issues.
- **`purge_wishlist.ps1/.sh`** - Purges the wishlist cache, clearing all cached family member wishlist data and forcing a fresh wishlist data refresh. This is helpful when family members have updated their Steam wishlists.
- **`purge_family_library.ps1/.sh`** - Purges the family library cache, clearing the cached family shared library data and forcing a fresh library data check. This is useful when new games have been added to the family sharing.
- **`purge_all_cache.ps1/.sh`** - Purges ALL cache data, completely resetting the cached information. This should be used with caution, as it will require time to rebuild all the caches.

### Usage Examples

```bash
# Populate all data (run after initial setup)
uv run python scripts/populate_database.py

# Price population - choose based on your needs:

# Standard mode (reliable, slower)
uv run python scripts/populate_prices.py

# Optimized mode (6-10x faster, recommended for most users)
uv run python scripts/populate_prices_optimized.py

# Maximum performance mode (15-25x faster, for large collections)
uv run python scripts/populate_prices_async.py

# During Steam sales (refresh current prices with maximum speed)
uv run python scripts/populate_prices_async.py --refresh-current --concurrent 75

# High-performance mode with custom settings
uv run python scripts/populate_prices_optimized.py --concurrent 20 --rate-limit aggressive

# Conservative mode for limited bandwidth
uv run python scripts/populate_prices_async.py --concurrent 25 --rate-limit conservative

# Clear all caches and rebuild
.\scripts\purge_all_cache.ps1
uv run python scripts/populate_database.py
```

**Recommended Usage:**

- **First-time setup**: Use `populate_prices_optimized.py` for a good balance of speed and reliability
- **Large game collections (500+ games)**: Use `populate_prices_async.py` for maximum performance
- **Steam sales**: Use `populate_prices_async.py --refresh-current` for fastest price updates
- **Limited bandwidth**: Use any script with `--rate-limit conservative` flag

For detailed documentation, see [scripts/README.md](scripts/README.md) and [scripts/PRICE_OPTIMIZATION_README.md](scripts/PRICE_OPTIMIZATION_README.md).

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

### Private Profile Monitoring

The logging system provides detailed tracking of private profile issues:

```log
[PRIVATE_PROFILE] username (steam_id): operation blocked - profile is private
```

### Viewing Logs

**Windows (PowerShell):**

```powershell
# View real-time logs
Get-Content logs\familybot.log -Wait
Get-Content logs\familybot_errors.log -Wait

# Search for specific issues
Select-String "ERROR" logs\familybot.log
Select-String "PRIVATE_PROFILE" logs\familybot.log
```

**macOS/Linux (Bash):**

```bash
# View real-time logs
tail -f logs/familybot.log
tail -f logs/familybot_errors.log

# Search for specific issues
grep "ERROR" logs/familybot.log
grep "PRIVATE_PROFILE" logs/familybot.log
```

### Log Management

Logs are automatically managed:

- Files rotate when size limits are reached
- Old logs are archived automatically
- All log files are git-ignored for security
- Sensitive data is automatically sanitized

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

### Free Epic Games

- Sends a notification in a designated channel about the new weekly free games on the Epic Games Store.
- `!force_epic`: An admin-only command (usable in DM) to manually trigger an Epic Games free game check.

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
2. **Token issues**: Ensure the Token_Sender is running and Firefox profile is properly configured.
3. **Database errors**: Try running the database population scripts or purging cache.
4. **Permission errors**: Ensure the bot has Administrator permissions in your Discord server.

### Getting Help

- Check the logs in the `logs/` directory for detailed error information
- Review the configuration files for missing or incorrect values
- Ensure all dependencies are properly installed using the reinstall script
- Verify that Firefox is installed and accessible for the Token_Sender component
