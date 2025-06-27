# Family Bot

This project is a modified version of the original "FamilyBot" created by Chachigo. I have made significant improvements and refactorings to the codebase.
**Original Source:** [Chachigo/FamilyBot](https://github.com/Chachigo/FamilyBot)

## Introduction

Family Bot is a Discord bot primarily designed to notify about new games that are added to the Steam Family library. Plugins can be made to add functionalities using the [interactions.py](https://interactions-py.github.io/interactions.py/) library.

## Project Structure

The project follows a modern Python package structure:

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
│   │   └── help_message.py  # Dynamic help system
│   └── Token_Sender/        # Separate token management bot
│       ├── getToken.py      # Token extraction script
│       └── config-template.yaml # Token sender configuration
├── scripts/                 # Utility scripts
│   ├── populate_database.py # Database population
│   ├── populate_prices.py   # Price data population
│   └── README.md           # Scripts documentation
├── doc/                    # Documentation images
├── logs/                   # Log files (auto-created)
├── config-template.yml     # Main bot configuration template
├── pyproject.toml         # Project dependencies and metadata
└── main.py               # Simple entry point (placeholder)
```

## How It Works

FamilyBot consists of several interconnected components:

### Main Bot (`FamilyBot.py`)

- **Discord Bot**: Handles all Discord interactions using interactions.py
- **Plugin System**: Automatically loads plugins from the `plugins/` directory
- **Database Management**: SQLite database for caching game data, wishlists, and user information
- **WebSocket Server**: Receives tokens from the Token_Sender component
- **Command-line Interface**: Supports cache management and maintenance operations

### Token Sender (`Token_Sender/getToken.py`)

- **Automated Token Extraction**: Uses Selenium with Firefox to extract Steam web API tokens
- **WebSocket Client**: Sends tokens to the main bot via WebSocket connection
- **Session Management**: Maintains Steam login sessions for token renewal

### Plugin Architecture

- **Modular Design**: Each feature is implemented as a separate plugin
- **Auto-loading**: Plugins are automatically discovered and loaded at startup
- **Extensible**: New functionality can be added by creating new plugin files

### Database System

- **SQLite Backend**: Lightweight, file-based database for data persistence
- **Caching Strategy**: Intelligent caching of Steam API responses to minimize API calls
- **Performance Optimization**: Pre-populated price data for faster deal detection

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

## Running the Bots

Both bots need to run concurrently in separate processes. The main entry point is `src/familybot/FamilyBot.py`, not the `main.py` file (which is just a placeholder).

From the `FamilyBot/` project root directory, you have a few options:

### Option 1: Using the Launch Scripts (Recommended for ease-of-use)

These scripts will launch both the main bot and the token sender in separate terminal windows, allowing them to operate concurrently.

- **For Windows (PowerShell 7):**

    ```powershell
    .\run_bots.ps1
    ```

- **For macOS/Linux (Bash):**

    ```bash
    chmod +x ./run_bots.sh # Make the script executable first
    ./run_bots.sh
    ```

**🚨 Security Note for Windows Launch Scripts (.ps1 and .bat) 🚨**
The `run_bots.ps1` script (which internally calls `run_bots.bat` commands) and the `run_bots.bat` script itself operate by directly launching `cmd.exe` processes. This method effectively **bypasses Windows PowerShell's Execution Policy** (a security feature). While this resolves issues in environments where PowerShell scripts might be blocked, it means that these scripts will run without security checks or prompts.

**It is crucial to review the content of these scripts (`run_bots.ps1`, `run_bots.bat`, and the Python files they execute) and ensure you trust their source before running them.** This approach trades off some security strictness for functionality in certain environments.

### Option 2: Running Manually (For more control or troubleshooting)

You can also launch each bot manually in its own separate terminal window. This requires you to first activate the virtual environment in each window.

- **Step 1: Activate the Virtual Environment**
    Open a new terminal window, navigate to your `FamilyBot/` project root directory, and run:
- **For Windows (PowerShell 7):**

```powershell
        . .\.venv\Scripts\Activate.ps1
```

- **For macOS/Linux (Bash):**

```bash
        source ./.venv/bin/activate
```

You should see `(.venv)` appear at the beginning of your terminal prompt.

- **Step 2: Run the Bot Executables**
  Once the virtual environment is active in a terminal window, run the respective bot:
  - **To run the main bot (FamilyBot.py + WebSocket server):**

    ```powershell
    uv run python .\src\familybot\FamilyBot.py
    ```

    (Use `./src/familybot/FamilyBot.py` for macOS/Linux Bash)

  - **To run the token sender bot (getToken.py):**

    ```powershell
    uv run python .\src\familybot\Token_Sender\getToken.py
    ```

    (Use `./src/familybot/Token_Sender/getToken.py` for macOS/Linux Bash)

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

The `scripts/` directory contains powerful utility scripts for database management and performance optimization:

### Database Population Scripts

- **`populate_database.py`** - Comprehensive database population script that fetches game data, wishlists, and family libraries. Perfect for initial setup or complete rebuilds.
- **`populate_prices.py`** - Specialized price data population script that pre-populates both Steam Store prices and ITAD historical price data for **family wishlist games only**. **Essential for Steam Summer/Winter Sales** to maximize deal detection speed.

### Cache Management Scripts

- **`purge_cache.ps1/.sh`** - Purge game details cache to force fresh USD pricing
- **`purge_wishlist.ps1/.sh`** - Purge wishlist cache when family members update their wishlists
- **`purge_family_library.ps1/.sh`** - Purge family library cache when new games are added
- **`purge_all_cache.ps1/.sh`** - Purge ALL cache data for complete reset

### Usage Examples

```bash
# Populate all data (run after initial setup)
uv run python scripts/populate_database.py

# Prepare for Steam sales (populate price data)
uv run python scripts/populate_prices.py

# During Steam sales (refresh current prices)
uv run python scripts/populate_prices.py --refresh-current --steam-only

# Clear all caches and rebuild
.\scripts\purge_all_cache.ps1
uv run python scripts/populate_database.py
```

For detailed documentation, see [scripts/README.md](scripts/README.md).

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
