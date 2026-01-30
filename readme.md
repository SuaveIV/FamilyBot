# FamilyBot

FamilyBot is a Discord bot that tracks Steam Family libraries. It notifies you when someone adds a new game, helps find common multiplayer titles among friends, and monitors wishlists for deals.

This is a modified and refactored version of the original [Chachigo/FamilyBot](https://github.com/Chachigo/FamilyBot).

## Project Structure

The project is organized as a Python package:

```bash
FamilyBot/
├── src/familybot/           # Main bot logic
│   ├── FamilyBot.py         # Entry point
│   ├── WebSocketServer.py   # Token communication
│   ├── config.py            # Settings loader
│   ├── lib/                 # Shared utilities and database logic
│   ├── plugins/             # Bot features (Steam, Epic, Tokens)
│   └── web/                 # Web dashboard (FastAPI)
├── scripts/                 # Maintenance and setup scripts
├── doc/                    # Manuals and planning docs
├── config-template.yml     # Configuration template
└── pyproject.toml         # Dependencies and metadata
```

## How It Works

FamilyBot combines a Discord bot with a web-based dashboard.

### Core Bot

- **Interaction**: Uses `interactions.py` to handle Discord commands and events.
- **Plugins**: Modular features are loaded from the `plugins/` directory.
- **Storage**: Uses SQLite to cache game details, wishlists, and user mappings locally.

### Token Management

- **Automation**: Uses Playwright to extract Steam web API tokens automatically.
- **Sessions**: Saves login states so you don't have to log in repeatedly.
- **Admin Control**: Use `!force_token` to refresh tokens manually.

### Web Dashboard

- **Status**: Check if the bot is online, see cache stats, and view recent library additions.
- **Logs**: A built-in viewer for monitoring bot activity in real-time.
- **Themes**: Choose from several Bootswatch themes (with dark mode support).
- **Control**: Purge caches or trigger database population from your browser.

## Installation

### Requirements

- **Python 3.13+**
- `uv` for dependency management (recommended)
- `mise` for environment management (optional but recommended)

### Setup

We recommend using the `just` command runner for a smooth setup.

#### 1. Environment with `mise`

Install [mise](https://mise.jdx.dev/), then run:

```bash
mise install
```

#### 2. Install Dependencies

```bash
just setup
```

#### 3. Steam Login

Set up your Steam session for the token sender:

```bash
just setup-browser
```

## Discord Bot Configuration

1. Create an application on the [Discord Developer Portal](https://discord.com/developers/applications).
2. Disable **Public Bot** and enable all **Privileged Gateway Intents**.
3. Under **OAuth2 -> URL Generator**, select `bot` and `Administrator`. Open the generated link to add the bot to your server.
4. Copy your bot token from the **Bot** section.

## Bot Settings (`config.yml`)

Fill out `config-template.yml` and rename it to `config.yml`.

### IDs and Keys

- **Discord IDs**: Right-click users/channels in Discord (with Developer Mode on) to copy IDs.
- **Steamworks API Key**: Get one at [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey).
- **IsThereAnyDeal API Key**: Register at [isthereanydeal.com](https://isthereanydeal.com/).

### Steam Family ID

1. Go to [steamapi.xpaw.me](https://steamapi.xpaw.me/).
2. Use `IFamilyGroupsService/GetFamilyGroupForUser` with your SteamID and API key.
3. Your Family ID will be in the response.

## Quick Start Commands

```bash
just run             # Start the bot
just status          # Check config and environment
just populate-db     # Warm the cache with library data
just logs            # Watch the logs in real-time
just --list          # See all available commands
```

## Troubleshooting

- **Bot won't start**: Double-check `config.yml` for missing keys or trailing spaces.
- **No data**: Run `just populate-db` to ensure your local database isn't empty.
- **Permissions**: Ensure the bot has "Administrator" or sufficient channel permissions.

For more details, see the [scripts/README.md](scripts/README.md) or the [Web UI guide](doc/WEB_UI_README.md).
