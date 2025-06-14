# FamilyBot Scripts

This directory contains utility scripts for managing FamilyBot's cache and database operations.

## Database Population Script

### `populate_database.py` - Standalone Database Population

A comprehensive script that populates the FamilyBot database with game data without requiring Discord interaction. Perfect for initial setup or complete database rebuilds.

#### Features

- **Beautiful progress bars** with tqdm (install with `pip install tqdm`)
- **Rate limiting** to respect Steam API limits
- **Smart caching** - skips already processed games
- **Flexible options** - library-only, wishlist-only, or both
- **Dry run mode** - see what would be done without making changes
- **Multiple rate limiting modes** - fast, normal, or slow

#### Usage

```bash
# Install tqdm for progress bars (recommended)
pip install tqdm
# OR run the installer script
python scripts/install_tqdm.py

# Basic usage - populate everything
python scripts/populate_database.py

# Advanced options
python scripts/populate_database.py --library-only    # Only scan family libraries
python scripts/populate_database.py --wishlist-only   # Only scan wishlists
python scripts/populate_database.py --fast           # Faster rate limiting
python scripts/populate_database.py --slow           # Slower rate limiting  
python scripts/populate_database.py --dry-run        # Show what would be done
```

#### Time Estimates

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
python scripts/populate_database.py

# 3. Verify everything works
python -m src.familybot.FamilyBot
# Then test: !coop 2, !deals
```

## Cache Purge Scripts

These scripts help you clear various types of cached data to force fresh data retrieval or troubleshoot issues.

### Available Scripts

#### Game Details Cache Purging

- **`purge_cache.ps1`** / **`purge_cache.sh`** - Purges game details cache
  - Clears all cached Steam game information (names, prices, categories, etc.)
  - Forces fresh USD pricing on next API calls
  - Useful when you want to refresh pricing data or fix currency issues

#### Wishlist Cache Purging  

- **`purge_wishlist.ps1`** / **`purge_wishlist.sh`** - Purges wishlist cache
  - Clears all cached family member wishlist data
  - Forces fresh wishlist data on next refresh
  - Useful when family members have updated their wishlists

#### Family Library Cache Purging

- **`purge_family_library.ps1`** / **`purge_family_library.sh`** - Purges family library cache
  - Clears cached family shared library data
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
python scripts/populate_database.py
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
python scripts/populate_database.py
```

## Command Line Interface

You can also use the main bot script with command line arguments:

```bash
# Cache purging operations
python -m src.familybot.FamilyBot --purge-cache
python -m src.familybot.FamilyBot --purge-wishlist  
python -m src.familybot.FamilyBot --purge-family-library
python -m src.familybot.FamilyBot --purge-all

# Scan operations (require Discord bot for progress updates)
python -m src.familybot.FamilyBot --full-library-scan
python -m src.familybot.FamilyBot --full-wishlist-scan
```

## Discord Commands

For interactive operations, you can use these Discord commands (admin only, DM required):

- **`!purge_cache`** - Purge game details cache
- **`!full_library_scan`** - Comprehensive library scan with rate limiting
- **`!full_wishlist_scan`** - Complete wishlist scan of all common games
- **`!force_deals`** - Check deals and post to wishlist channel

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
  pip install tqdm
  # OR
  python scripts/install_tqdm.py
  ```

## Troubleshooting

If you encounter issues:

1. **Check permissions** - Ensure scripts are executable
2. **Verify paths** - Run from the FamilyBot root directory
3. **Database access** - Ensure `data/` directory is writable
4. **Python environment** - Verify all dependencies are installed
5. **Missing tqdm** - Install with `pip install tqdm` for progress bars

For more help, check the main README.md or Discord commands documentation.
