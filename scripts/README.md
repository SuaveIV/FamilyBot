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

## Rebuilding Cache

After purging, the bot will automatically rebuild cache as needed. To speed up the process:

1. Start the bot: `python -m src.familybot.FamilyBot`
2. Run `!full_wishlist_scan` for comprehensive wishlist rebuild
3. Run `!full_library_scan` to cache all family members' complete game libraries
4. Run `!coop 2` to cache multiplayer games
5. Use `!force_deals` to cache deal information

All future API calls will use USD pricing and include the new performance-optimized boolean fields.
