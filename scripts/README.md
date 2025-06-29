# FamilyBot Scripts

This directory contains a suite of powerful utility scripts for managing FamilyBot's database, cache, and overall performance.

## Database Population Scripts

### `populate_database.py` - Standalone Database Population

A comprehensive script that populates the FamilyBot database with game data, wishlists, and family library information without requiring Discord interaction. This script is perfect for initial setup or complete database rebuilds.

### `populate_prices.py` - Wishlist Price Data Population

A specialized script that pre-populates both Steam Store prices and ITAD historical price data for **family wishlist games only**. This is **essential for maximizing performance during Steam Summer/Winter Sales** when you want to achieve the fastest possible deal detection speeds.

#### Features

- **Dual API integration** - Fetches both Steam Store and ITAD price data
- **Smart filtering** - Only processes games that need updates (unless forced)
- **Flexible modes** - Steam-only, ITAD-only, or both
- **Sale optimization** - Refresh current prices during active sales
- **Conservative rate limiting** - Respects both Steam and ITAD API limits
- **Progress tracking** - Beautiful progress bars with detailed statistics
- **Error resilience** - Continues processing even if some games fail

#### Usage

```bash
# Basic usage - populate all price data
uv run python scripts/populate_prices.py

# Steam Summer/Winter Sale workflow
uv run python scripts/populate_prices.py --refresh-current  # Update current prices during sales
uv run python scripts/populate_prices.py --steam-only       # Only Steam prices (faster)
uv run python scripts/populate_prices.py --itad-only        # Only historical prices

# Advanced options
uv run python scripts/populate_prices.py --force-refresh    # Refresh all data even if cached
uv run python scripts/populate_prices.py --conservative     # Very slow, safest rate limiting
uv run python scripts/populate_prices.py --fast            # Faster rate limiting (use carefully)
uv run python scripts/populate_prices.py --dry-run         # See what would be processed
```

#### When to Use

- **Before major sales** - Pre-populate ITAD data for instant deal detection
- **During active sales** - Use `--refresh-current` to update Steam prices
- **After cache purging** - Rebuild comprehensive price database
- **Performance optimization** - Make `!force_deals_unlimited` run at maximum speed

#### Time Estimates

For a typical family library (~1000 games):

- **Steam prices only**: 25-40 minutes
- **ITAD prices only**: 15-25 minutes  
- **Both Steam + ITAD**: 40-65 minutes
- **Refresh current prices**: 25-40 minutes

#### Steam Sale Workflow

```bash
# Before a major Steam sale (e.g., Summer Sale)
uv run python scripts/populate_prices.py

# During the sale (daily updates)
uv run python scripts/populate_prices.py --refresh-current --steam-only

# After the sale
# No action needed - cached data remains valid
```

---

### `populate_database.py` - Database Population Details

#### Database Features

- **Beautiful progress bars** with tqdm (install with `pip install tqdm`)
- **Rate limiting** to respect Steam API limits
- **Smart caching** - skips already processed games
- **Flexible options** - library-only, wishlist-only, or both
- **Dry run mode** - see what would be done without making changes
- **Multiple rate limiting modes** - fast, normal, or slow

#### Database Usage

**Note**: Ensure your virtual environment is activated before running these scripts manually. Use `uv run python` to automatically handle the environment.

```bash
# Install tqdm for progress bars (recommended)
uv add tqdm
# OR run the installer script
uv run python scripts/install_tqdm.py

# Basic usage - populate everything
uv run python scripts/populate_database.py

# Advanced options
uv run python scripts/populate_database.py --library-only    # Only scan family libraries
uv run python scripts/populate_database.py --wishlist-only   # Only scan wishlists
uv run python scripts/populate_database.py --fast           # Faster rate limiting
uv run python scripts/populate_database.py --slow           # Slower rate limiting  
uv run python scripts/populate_database.py --dry-run        # Show what would be done
```

#### Database Time Estimates

For a large combined library (2800+ games):

- **Library scan**: 50-70 minutes (one-time investment)
- **Wishlist scan**: 5-15 minutes
- **Total first run**: ~60-85 minutes
- **Subsequent runs**: Much faster due to caching

#### Recommended Workflow After Cache Purging

```bash
# 1. Clear all caches
.\scripts\purge_all_cache.ps1

# 2. Populate database (with progress bars!)
uv run python scripts/populate_database.py

# 3. Verify everything works
uv run python -m src.familybot.FamilyBot
# Then test: !coop 2, !deals
```

## Cache Purge Scripts

The cache purge scripts allow you to clear various types of cached data, forcing fresh data retrieval and enabling troubleshooting:

### Available Scripts

#### Game Details Cache Purging

- **`purge_cache.ps1`** / **`purge_cache.sh`** - Purges the game details cache
  - Clears all cached Steam game information (names, prices, categories, etc.)
  - Forces fresh USD pricing on next API calls
  - Useful when you want to refresh pricing data or fix currency issues

#### Wishlist Cache Purging  

- **`purge_wishlist.ps1`** / **`purge_wishlist.sh`** - Purges the wishlist cache
  - Clears all cached family member wishlist data
  - Forces fresh wishlist data on next refresh
  - Useful when family members have updated their wishlists

#### Family Library Cache Purging

- **`purge_family_library.ps1`** / **`purge_family_library.sh`** - Purges the family library cache
  - Clears the cached family shared library data
  - Forces fresh library data on next check
  - Useful when new games have been added to family sharing

#### Complete Cache Purging

- **`purge_all_cache.ps1`** / **`purge_all_cache.sh`** - Purges ALL cache data
  - Combines all the above purge operations
  - Completely resets all cached data
  - **Use with caution** - will require time to rebuild all caches

## Usage Examples

### PowerShell (Windows)

```powershell
# Purge specific cache types
.\scripts\purge_cache.ps1
.\scripts\purge_wishlist.ps1
.\scripts\purge_family_library.ps1

# Purge everything
.\scripts\purge_all_cache.ps1

# Populate database
uv run python scripts/populate_database.py
```

### Bash (Linux/macOS)

```bash
# Make scripts executable (first time only)
chmod +x scripts/*.sh

# Purge specific cache types
./scripts/purge_cache.sh
./scripts/purge_wishlist.sh
./scripts/purge_family_library.sh

# Purge everything
./scripts/purge_all_cache.sh

# Populate database
uv run python scripts/populate_database.py
```

## Command Line Interface

You can also use the main bot script with command line arguments:

```bash
# Cache purging operations
uv run python -m src.familybot.FamilyBot --purge-cache
uv run python -m src.familybot.FamilyBot --purge-wishlist  
uv run python -m src.familybot.FamilyBot --purge-family-library
uv run python -m src.familybot.FamilyBot --purge-all

# Scan operations (require Discord bot for progress updates)
uv run python -m src.familybot.FamilyBot --full-library-scan
uv run python -m src.familybot.FamilyBot --full-wishlist-scan
```

## Discord Commands

For interactive operations, you can use these Discord commands (admin only, DM required):

- **`!purge_cache`** - Purge game details cache
- **`!full_library_scan`** - Comprehensive library scan with rate limiting
- **`!full_wishlist_scan`** - Complete wishlist scan of all common games
- **`!force_deals`** - Check deals and post to wishlist channel (limited to 100 games)
- **`!force_deals_unlimited`** - Check deals for ALL wishlist games (family sharing only)

## When to Use Each Script

### Database Population Script (`populate_database.py`)

- **When**: Initial setup, after purging all caches, or major Steam account changes
- **Why**: Efficiently populates entire database with beautiful progress tracking
- **Advantage**: No Discord required, faster than Discord commands, better progress feedback

### Game Details Cache (`purge_cache`)

- **When**: Pricing seems outdated or incorrect
- **Why**: Forces fresh USD pricing and updated game information
- **Rebuild**: Use `populate_database.py` or automatic during normal bot operations

### Wishlist Cache (`purge_wishlist`)

- **When**: Family members have updated their Steam wishlists
- **Why**: Ensures bot sees the latest wishlist changes
- **Rebuild**: Use `populate_database.py --wishlist-only` or automatic every 24 hours

### Family Library Cache (`purge_family_library`)

- **When**: New games added to family sharing aren't showing up
- **Why**: Forces fresh check of family shared library
- **Rebuild**: Automatic every hour

### All Cache (`purge_all`)

- **When**: Major issues or after significant Steam account changes
- **Why**: Complete reset for troubleshooting
- **Rebuild**: Use `populate_database.py` for fastest rebuild

## Safety Features

- **Confirmation prompts** - All scripts ask for confirmation before proceeding
- **Backup recommendations** - Scripts remind you about rebuilding caches
- **Error handling** - Graceful failure with helpful error messages
- **Dry run support** - Database population script supports `--dry-run` for testing
- **Progress tracking** - Real-time progress bars with tqdm

## Performance Impact

- **Cache purging**: Instant operation
- **Database population**:
  - With `populate_database.py`: ~60-85 minutes for full 2800+ game library
  - Game details: ~1-2 hours via Discord commands
  - Wishlist: ~5-15 minutes
  - Family library: ~30 minutes

## Dependencies

- **tqdm** - For beautiful progress bars in `populate_database.py`

  ```bash
  uv add tqdm
  # OR
  uv run python scripts/install_tqdm.py
  ```

## Troubleshooting

If you encounter issues:

1. **Check permissions** - Ensure scripts are executable
2. **Verify paths** - Run from the FamilyBot root directory
3. **Database access** - Ensure `data/` directory is writable
4. **Python environment** - Verify all dependencies are installed
5. **Missing tqdm** - Install with `uv add tqdm` for progress bars
6. **Virtual environment** - Use `uv run python` to automatically handle environment activation

For more help, check the main README.md or Discord commands documentation.
