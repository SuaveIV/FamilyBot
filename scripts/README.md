# FamilyBot Scripts

This directory contains a suite of powerful utility scripts for managing FamilyBot's database, cache, and overall performance.

## Database Population Scripts

### `populate_database.py` - Standalone Database Population

A comprehensive script that populates the FamilyBot database with game data, wishlists, and family library information without requiring Discord interaction. This script is perfect for initial setup or complete database rebuilds.

### Price Population Scripts (Performance Optimized)

FamilyBot now includes **three performance tiers** for price data population, each optimized for different use cases:

- **`populate_prices.py`** - **Original** sequential processing (1x speed baseline). Reliable but slower for large datasets.
- **`populate_prices_optimized.py`** - **Threading-based optimization** with connection pooling (6-10x faster). Uses concurrent requests with intelligent rate limiting and connection reuse to minimize data usage.
- **`populate_prices_async.py`** - **True async/await processing** (15-25x faster). Maximum performance with aggressive connection pooling and async I/O for the fastest possible price population.

All scripts pre-populate both Steam Store prices and ITAD historical price data for **family wishlist games only**. This is **essential for maximizing performance during Steam Summer/Winter Sales** when you want to achieve the fastest possible deal detection speeds.

#### Performance Comparison

| Script        | Processing Mode | Concurrency       | Expected Speed            | Data Usage Reduction |
| ------------- | --------------- | ----------------- | ------------------------- | -------------------- |
| **Original**  | Sequential      | 1 request         | ~1,200 games/hour         | Baseline             |
| **Optimized** | Threading       | 10-20 concurrent  | ~8,000-12,000 games/hour  | 15-25% reduction     |
| **Async**     | True Async      | 50-100 concurrent | ~20,000-30,000 games/hour | 25-35% reduction     |

#### Connection Reuse Benefits

- **Optimized**: 50 max connections, 20 keepalive connections, 30s expiry
- **Async**: 200 max connections, 100 keepalive connections, 60s expiry
- **Reduced Data Usage**: Persistent connections eliminate redundant TCP handshakes and DNS lookups

#### Usage

```bash
# Basic usage - populate all price data
just populate-prices

# Optimized mode (recommended)
just populate-prices-fast

# Maximum performance mode
just populate-prices-turbo
```

For more detailed usage and advanced options, see [PRICE_OPTIMIZATION_README.md](PRICE_OPTIMIZATION_README.md).

---

### `populate_database.py` - Database Population Details

#### Database Features

- **Beautiful progress bars** with tqdm
- **Rate limiting** to respect Steam API limits
- **Smart caching** - skips already processed games
- **Flexible options** - library-only, wishlist-only, or both
- **Dry run mode** - see what would be done without making changes
- **Multiple rate limiting modes** - fast, normal, or slow

#### Database Usage

**Note**: Ensure your virtual environment is activated before running these scripts manually. Use `just` for automatic environment handling.

```bash
# Basic usage - populate everything
just populate-db

# Advanced options
just populate-db --library-only    # Only scan family libraries
just populate-db --wishlist-only   # Only scan wishlists
just populate-db --fast           # Faster rate limiting
just populate-db --slow           # Slower rate limiting
just populate-db --dry-run        # Show what would be done
```

## Cache Purge Scripts

The cache purge scripts allow you to clear various types of cached data, forcing fresh data retrieval and enabling troubleshooting:

### Available Scripts

- **`purge_cache.ps1`** / **`purge_cache.sh`** - Purges the game details cache
- **`purge_wishlist.ps1`** / **`purge_wishlist.sh`** - Purges the wishlist cache
- **`purge_family_library.ps1`** / **`purge_family_library.sh`** - Purges the family library cache
- **`purge_all_cache.ps1`** / **`purge_all_cache.sh`** - Purges ALL cache data

### Usage Examples

**Using `just` (Recommended):**

```bash
# Purge specific cache types
just purge-cache
just purge-wishlist
just purge-family-library

# Purge everything
just purge-all-cache
```

## Command Line Interface

You can also use the main bot script with command line arguments:

```bash
# Cache purging operations
uv run python -m src.familybot.FamilyBot --purge-cache
uv run python -m src.familybot.FamilyBot --purge-wishlist
uv run python -m src.familybot.FamilyBot --purge-family-library
uv run python -m src.familybot.FamilyBot --purge-all
```

## Discord Commands

For interactive operations, you can use these Discord commands (admin only, DM required):

- **`!purge_cache`** - Purge game details cache
- **`!full_library_scan`** - Comprehensive library scan with rate limiting
- **`!full_wishlist_scan`** - Complete wishlist scan of all common games
- **`!force_deals`** - Check deals and post to wishlist channel (limited to 100 games)
- **`!force_deals_unlimited`** - Check deals for ALL wishlist games (family sharing only)

## Troubleshooting

If you encounter issues:

1. **Check permissions** - Ensure scripts are executable
2. **Verify paths** - Run from the FamilyBot root directory
3. **Database access** - Ensure `data/` directory is writable
4. **Python environment** - Verify all dependencies are installed
5. **Virtual environment** - Use `just` to automatically handle environment activation

For more help, check the main README.md or Discord commands documentation.
