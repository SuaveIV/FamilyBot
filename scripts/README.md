# FamilyBot Utility Scripts

This directory contains utility scripts for managing FamilyBot cache and maintenance operations.

## Cache Purge Scripts

These scripts allow you to clear various types of cached data to force fresh API calls and resolve issues with outdated data (especially EUR pricing from previous French API calls).

### Available Scripts

#### Game Details Cache

- **`purge_cache.ps1`** / **`purge_cache.sh`**
  - Purges game details cache to force fresh USD pricing and new boolean fields
  - Use this after the EUR→USD API change to get accurate pricing
  - **Recommended after major updates**

#### Wishlist Cache

- **`purge_wishlist.ps1`** / **`purge_wishlist.sh`**
  - Purges wishlist cache to force fresh wishlist data
  - Use when wishlist data seems stale or incorrect

#### Family Library Cache

- **`purge_family_library.ps1`** / **`purge_family_library.sh`**
  - Purges family library cache to force fresh family game data
  - Use when family shared games aren't showing correctly

#### All Cache Data

- **`purge_all_cache.ps1`** / **`purge_all_cache.sh`**
  - **⚠️ CAUTION:** Purges ALL cache data (game details, wishlist, family library, user games, ITAD prices)
  - Use for complete cache reset when multiple issues are present
  - **This will force re-fetching of all data**

## Usage

### Windows (PowerShell)

```powershell
# Run from FamilyBot root directory
.\scripts\purge_cache.ps1
.\scripts\purge_wishlist.ps1
.\scripts\purge_family_library.ps1
.\scripts\purge_all_cache.ps1
```

### Linux/Unix (Bash)

```bash
# Run from FamilyBot root directory
./scripts/purge_cache.sh
./scripts/purge_wishlist.sh
./scripts/purge_family_library.sh
./scripts/purge_all_cache.sh
```

### Command Line (Direct)

```bash
# Cache purging (standalone operations)
python -m src.familybot.FamilyBot --purge-cache
python -m src.familybot.FamilyBot --purge-wishlist
python -m src.familybot.FamilyBot --purge-family-library
python -m src.familybot.FamilyBot --purge-all

# Scan operations (require Discord bot for progress updates)
python -m src.familybot.FamilyBot --full-library-scan    # Redirects to Discord command
python -m src.familybot.FamilyBot --full-wishlist-scan   # Redirects to Discord command
```

**Note:** Scan commands require the bot to be running for real-time progress updates and admin verification. Use the Discord commands `!full_library_scan` and `!full_wishlist_scan` instead.

## Available Discord Commands

### Cache Management Commands (Admin Only, DM Required)

- **`!purge_cache`** - Purge game details cache via Discord
- **`!full_wishlist_scan`** - Comprehensive scan of ALL common wishlist games
- **`!full_library_scan`** - Scan all family members' complete game libraries
- **`!force_deals`** - Check current deals and post to wishlist channel

### Regular Commands

- **`!coop NUMBER`** - Find family shared multiplayer games with specified copies
- **`!deals`** - Check current deals on family wishlist games
- **`!force`** - Force new game notification check (admin only)
- **`!force_wishlist`** - Force wishlist refresh (admin only)

## When to Use

### After EUR→USD API Change

Run `purge_cache` to clear old French pricing data and force USD pricing with new boolean fields.

### Stale Data Issues

- **Wishlist problems**: Use `purge_wishlist`
- **Family library issues**: Use `purge_family_library`
- **Multiple cache issues**: Use `purge_all_cache`

### After Database Schema Updates

Run `purge_cache` to ensure all games get the new boolean fields (is_multiplayer, is_coop, is_family_shared).

## Safety Features

- **Confirmation prompts** before deletion
- **Detailed counts** of data being purged
- **Next steps guidance** after purging
- **Preserves user data** (family members, saved games, user registrations)

## Rebuilding Cache

After purging, the bot will automatically rebuild cache as needed. To speed up the process:

1. Start the bot: `python -m src.familybot.FamilyBot`
2. Run `!full_wishlist_scan` for comprehensive wishlist rebuild
3. Run `!full_library_scan` to cache all family members' complete game libraries
4. Run `!coop 2` to cache multiplayer games
5. Use `!force_deals` to cache deal information

All future API calls will use USD pricing and include the new performance-optimized boolean fields.
