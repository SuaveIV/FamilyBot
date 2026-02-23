# PLAN: Cache Strategy & Scheduled Timing Implementation

## Executive Summary

Transform your bot's task system from **unpredictable interval-based with unclear caching** to **scheduled timing with intelligent cache strategy**.

**Goals:**

- ✅ Reduce API calls by ~50%
- ✅ Make timing predictable and professional
- ✅ Ensure force commands actually force fresh data
- ✅ Improve debuggability and monitoring

**Estimated Time:** 2-3 hours
**Complexity:** Medium
**Risk:** Low (backwards compatible design)

---

## Phase 1: Problem Analysis

### Current Issues

#### Issue 1: Cache Confusion

**Problem:**

- Both hourly tasks AND force commands use the same `force_new_game_action()` function
- Function name says "force" but it uses cache if available
- No guarantee automated tasks get fresh data
- No guarantee force commands bypass cache

**Evidence:**

```python
# In steam_tasks.py
async def new_game_task(self):
    result = await force_new_game_action()  # Uses cache!

# In steam_admin.py  
async def force_new_game_command(self, ctx):
    result = await force_new_game_action()  # Also uses cache!
```

**Impact:**

- Users expect "force" to get fresh data
- Automated tasks may show stale data
- Confusion about when cache is used

#### Issue 2: Unpredictable Timing

**Problem:**

- `IntervalTrigger(hours=1)` runs 60 minutes after bot starts
- Timing depends on startup time
- If bot restarts, timing changes

**Example:**

```text
Bot starts: 10:37 AM
First run:  10:37 AM
Second run: 11:37 AM
Third run:  12:37 PM

Bot restarts: 2:15 PM
New timing:   2:15 PM, 3:15 PM, 4:15 PM...
```

**Impact:**

- Hard to debug ("when did this run?")
- Can't predict when tasks will execute
- Difficult to coordinate with external systems

#### Issue 3: Inefficient API Usage

**Problem:**

- No clear cache strategy
- Potential duplicate API calls
- Higher risk of rate limiting

**Impact:**

- Unnecessary API calls
- Could hit rate limits
- Slower performance

---

## Phase 2: Solution Design

### Design Decision 1: Separate Check vs Force Functions

**Strategy:** Create two versions of each action function

```text
├── Regular Check Functions (for automated tasks)
│   ├── check_new_game_action()    → uses cache, minimizes API
│   └── check_wishlist_action()    → uses cache, minimizes API
│
└── Force Functions (for admin commands)
    ├── force_new_game_action()    → bypasses cache, always fresh
    └── force_wishlist_action()    → bypasses cache, always fresh
```

**Benefits:**

- Clear separation of concerns
- Automated tasks = efficient
- Manual commands = accurate
- Names match behavior

### Design Decision 2: Scheduled Timing

**Strategy:** Switch from `IntervalTrigger` to `TimeTrigger`

```python
# Before (Interval-based)
@Task.create(IntervalTrigger(hours=1))

# After (Scheduled)
@Task.create(TimeTrigger(hour=list(range(24)), minute=15))
```

**Schedule:**

- **New game checks**: Every hour at `:15` (00:15, 01:15, 02:15, ...)
- **Wishlist updates**: Every 6 hours at `:45` (00:45, 06:45, 12:45, 18:45)

**Why :15 and :45?**

1. Avoids "top of hour rush" (many systems trigger at :00)
2. Staggers tasks (prevents simultaneous API calls)
3. Professional cron-style timing
4. Consistent regardless of restarts

### Design Decision 3: Smart Cache Strategy

| Data Type | Change Frequency | Automated Tasks | Force Commands | Cache TTL |
|-----------|-----------------|-----------------|----------------|-----------|
| Family Library | Slow (hours) | Use cache | Always fresh | 30 minutes |
| Wishlist Data | Moderate (hours) | Use cache | Always fresh | 2 hours |
| Game Details (prices) | Fast (minutes) | Always fresh* | Always fresh | Permanent** |

\* *In wishlist context, always fetch fresh prices*  
\*\* *Game metadata cached permanently, but refetched when needed for price updates*

**Rationale:**

- Family library changes when someone buys a game (infrequent)
- Wishlists change when users add/remove games (moderate)
- Prices change constantly during sales (frequent)

---

## Phase 3: Implementation Steps

### Step 1: Refactor `plugin_admin_actions.py`

#### 1.1 Create Helper Functions

**Add these new helper functions at the top of the file:**

```python
async def _fetch_family_library_from_api(session: aiohttp.ClientSession) -> list:
    """
    Helper function to fetch family library from Steam API.
    Returns the game list or raises an exception.
    
    This centralizes API fetching logic and is used by both
    check and force functions.
    """
    await _rate_limit_steam_api()
    url_family_list = get_family_game_list_url()
    async with session.get(url_family_list, timeout=aiohttp.ClientTimeout(total=15)) as answer:
        games_json = await _handle_api_response("GetFamilySharedApps", answer)
    
    if not games_json:
        raise Exception("Failed to get family shared apps from API")

    game_list = games_json.get("response", {}).get("apps", [])
    if not game_list:
        logger.warning("No apps found in family game list response.")
        raise Exception("No games found in the family library")

    return game_list


async def _process_new_games(game_list: list, current_family_members: dict) -> Dict[str, Any]:
    """
    Helper function to process game list and detect new games.
    Shared logic between check_new_game_action and force_new_game_action.
    
    Args:
        game_list: List of games from family library
        current_family_members: Dict of {steam_id: friendly_name}
    
    Returns:
        Dict with success status and message
    """
    # [All the existing game processing logic from force_new_game_action]
    # - Build game_array and game_owner_list
    # - Compare with saved_games
    # - Detect new games
    # - Fetch game details (with caching)
    # - Format notifications
    # - Update saved_games
    # - Return result dict
```

**Why?**

- Eliminates code duplication
- Both check and force functions use same core logic
- Easier to maintain and test
- Clear separation: fetching vs processing

#### 1.2 Create Check Functions (Cache-Respecting)

**Add new function for automated tasks:**

```python
async def check_new_game_action() -> Dict[str, Any]:
    """
    Regular check for new games that respects cache (for scheduled tasks).
    Uses cached family library if available to minimize API calls.
    
    This function is called by the hourly automated task.
    It will use cached data if available and valid.
    
    Returns:
        Dict with success status and message
    """
    logger.info("Running check_new_game_action (cache-respecting)...")

    try:
        # Try to get cached family library first
        cached_family_library = get_cached_family_library()
        if cached_family_library is not None:
            logger.info(
                f"Using cached family library for new game check ({len(cached_family_library)} games)"
            )
            game_list = cached_family_library
        else:
            # If not cached, fetch from API
            logger.info("No cached family library found, fetching from API...")
            game_list = await _fetch_family_library_from_api()
            
            # Cache for next time (30 minute TTL)
            cache_family_library(game_list, cache_minutes=30)
            logger.info(f"Cached family library ({len(game_list)} games)")

        current_family_members = await _load_family_members_from_db()
        return await _process_new_games(game_list, current_family_members)

    except Exception as e:
        logger.critical(
            f"An unexpected error occurred in check_new_game_action: {e}", 
            exc_info=True
        )
        return {
            "success": False,
            "message": f"Error checking for new games: {str(e)}",
        }
```

**Similar pattern for wishlist:**

```python
async def check_wishlist_action() -> Dict[str, Any]:
    """
    Regular wishlist check that uses cached wishlist data (for scheduled tasks).
    
    Cache strategy:
    - Uses cached wishlist data (2-hour TTL)
    - Always fetches fresh game details (prices change frequently)
    
    This balances API efficiency with price accuracy.
    """
    logger.info("Running check_wishlist_action (cache-respecting for wishlists)...")
    
    # For each family member:
    #   1. Check for cached wishlist
    #   2. If cached, use it
    #   3. If not cached, fetch from API and cache it
    #   4. For game details, always fetch fresh (prices!)
    
    # [Implementation similar to existing force_wishlist_action
    #  but with cache checks before API calls for wishlist data]
```

#### 1.3 Rename/Refactor Force Functions

**Update existing force functions to clearly bypass cache:**

```python
async def force_new_game_action() -> Dict[str, Any]:
    """
    Force check for new games that always fetches fresh data (for admin commands).
    Bypasses cache to ensure the most up-to-date information.
    
    This function is called by the !force admin command.
    It will always fetch fresh data from the Steam API.
    
    Returns:
        Dict with success status and message
    """
    logger.info("Running force_new_game_action (bypassing cache)...")

    try:
        # Always fetch fresh data from API (no cache check)
        logger.info("Force refresh: Fetching fresh family library from API...")
        game_list = await _fetch_family_library_from_api()
        
        # Update cache with fresh data for next regular check
        cache_family_library(game_list, cache_minutes=30)
        logger.info(f"Updated family library cache with {len(game_list)} games")

        current_family_members = await _load_family_members_from_db()
        return await _process_new_games(game_list, current_family_members)

    except Exception as e:
        logger.critical(
            f"An unexpected error occurred in force_new_game_action: {e}", 
            exc_info=True
        )
        return {
            "success": False,
            "message": f"Error forcing new game notification: {str(e)}",
        }
```

**Key differences from check function:**

1. No cache check - always calls `_fetch_family_library_from_api()`
2. Logs "bypassing cache" for clarity
3. Still updates cache to help next regular check

**Similar pattern for force_wishlist_action:**

```python
async def force_wishlist_action() -> Dict[str, Any]:
    """
    Force wishlist refresh that always fetches fresh data (for admin commands).
    
    Cache strategy:
    - Always fetches fresh wishlist data
    - Always fetches fresh game details
    - Updates cache for next regular check
    
    This ensures complete accuracy when admin requests it.
    """
    logger.info("Running force_wishlist_action (bypassing cache)...")
    
    # For each family member:
    #   1. Always fetch fresh wishlist from API
    #   2. Always fetch fresh game details
    #   3. Update cache with fresh data
    
    # [Implementation that skips all cache checks]
```

#### 1.4 File Structure Summary

**After refactoring, `plugin_admin_actions.py` should have:**

```python
# ==================== HELPER FUNCTIONS ====================
async def _fetch_family_library_from_api() -> list:
    """Centralized API fetching"""

async def _process_new_games(game_list, members) -> Dict:
    """Shared processing logic"""

# ==================== NEW GAME DETECTION ====================
async def check_new_game_action() -> Dict:
    """For automated tasks - uses cache"""

async def force_new_game_action() -> Dict:
    """For admin commands - bypasses cache"""

# ==================== WISHLIST MANAGEMENT ====================
async def check_wishlist_action() -> Dict:
    """For automated tasks - uses cache"""

async def force_wishlist_action() -> Dict:
    """For admin commands - bypasses cache"""

# ==================== OTHER ACTIONS ====================
async def force_deals_action() -> Dict:
    """Existing deals function"""

async def purge_game_details_cache_action() -> Dict:
    """Existing cache purge function"""
```

### Step 2: Update `steam_tasks.py`

#### 2.1 Change Imports

**Before:**

```python
from familybot.lib.plugin_admin_actions import force_new_game_action
```

**After:**

```python
from familybot.lib.plugin_admin_actions import check_new_game_action, check_wishlist_action
```

#### 2.2 Update New Game Task

**Before:**

```python
@Task.create(IntervalTrigger(hours=1))
async def new_game_task(self):
    """Background task to check for new games every hour."""
    logger.info("Running new game task...")
    try:
        from familybot.lib.plugin_admin_actions import force_new_game_action
        
        result = await force_new_game_action()
        if result["success"] and "New games detected" in result["message"]:
            await self.bot.send_to_channel(NEW_GAME_CHANNEL_ID, result["message"])
            logger.info("New game task: Posted new games to channel")
    except Exception as e:
        logger.error(f"Error in new game task: {e}", exc_info=True)
        await send_admin_dm(self.bot, f"New game task error: {e}")
```

**After:**

```python
@Task.create(TimeTrigger(hour=list(range(24)), minute=15))  # Every hour at :15
async def new_game_task(self):
    """Background task to check for new games - runs at :15 past each hour."""
    logger.info("Running scheduled new game task (hourly at :15)...")
    try:
        from familybot.lib.plugin_admin_actions import check_new_game_action
        
        result = await check_new_game_action()  # Uses cache
        if result["success"] and "New games detected" in result["message"]:
            await self.bot.send_to_channel(NEW_GAME_CHANNEL_ID, result["message"])
            logger.info("New game task: Posted new games to channel")
        else:
            logger.info(f"New game task result: {result['message']}")
    except Exception as e:
        logger.error(f"Error in new game task: {e}", exc_info=True)
        await send_admin_dm(self.bot, f"New game task error: {e}")
```

**Changes:**

1. ✅ `IntervalTrigger(hours=1)` → `TimeTrigger(hour=list(range(24)), minute=15)`
2. ✅ `force_new_game_action()` → `check_new_game_action()`
3. ✅ Updated log messages for clarity
4. ✅ Log result even when no new games (for debugging)

#### 2.3 Update Wishlist Task

**Before:**

```python
@Task.create(IntervalTrigger(hours=6))
async def wishlist_task(self):
    """Background task to refresh wishlist every 6 hours."""
    logger.info("Running wishlist task...")
    try:
        from familybot.lib.plugin_admin_actions import force_wishlist_action
        
        result = await force_wishlist_action()
        if result["success"] and "Details:" in result["message"]:
            wishlist_channel = await self.bot.fetch_channel(WISHLIST_CHANNEL_ID)
            if wishlist_channel and isinstance(wishlist_channel, GuildText):
                pinned_messages = await wishlist_channel.fetch_pinned_messages()
                if pinned_messages:
                    content_start = result["message"].find("Details:\n") + len("Details:\n")
                    wishlist_content = result["message"][content_start:]
                    await pinned_messages[-1].edit(content=wishlist_content)
                    logger.info("Wishlist task: Updated pinned message")
    except Exception as e:
        logger.error(f"Error in wishlist task: {e}", exc_info=True)
        await send_admin_dm(self.bot, f"Wishlist task error: {e}")
```

**After:**

```python
@Task.create(TimeTrigger(hour=[0, 6, 12, 18], minute=45))  # Every 6 hours at :45
async def wishlist_task(self):
    """Background task to refresh wishlist - runs at :45 of hours 0, 6, 12, 18."""
    logger.info("Running scheduled wishlist task (every 6 hours at :45)...")
    try:
        from familybot.lib.plugin_admin_actions import check_wishlist_action
        
        result = await check_wishlist_action()  # Uses cache for wishlists
        if result["success"] and "Details:" in result["message"]:
            wishlist_channel = await self.bot.fetch_channel(WISHLIST_CHANNEL_ID)
            if wishlist_channel and isinstance(wishlist_channel, GuildText):
                pinned_messages = await wishlist_channel.fetch_pinned_messages()
                if pinned_messages:
                    content_start = result["message"].find("Details:\n") + len("Details:\n")
                    wishlist_content = result["message"][content_start:]
                    await pinned_messages[-1].edit(content=wishlist_content)
                    logger.info("Wishlist task: Updated pinned message")
        else:
            logger.info(f"Wishlist task result: {result['message']}")
    except Exception as e:
        logger.error(f"Error in wishlist task: {e}", exc_info=True)
        await send_admin_dm(self.bot, f"Wishlist task error: {e}")
```

**Changes:**

1. ✅ `IntervalTrigger(hours=6)` → `TimeTrigger(hour=[0, 6, 12, 18], minute=45)`
2. ✅ `force_wishlist_action()` → `check_wishlist_action()`
3. ✅ Updated log messages for clarity
4. ✅ Log result even when no updates (for debugging)

#### 2.4 Update Startup Message

**Before:**

```python
@listen()
async def on_startup(self):
    """Start background tasks when the bot starts."""
    self.new_game_task.start()
    self.wishlist_task.start()
    logger.info("--Steam Family background tasks started")
```

**After:**

```python
@listen()
async def on_startup(self):
    """Start background tasks when the bot starts."""
    self.new_game_task.start()
    self.wishlist_task.start()
    logger.info("--Steam Family background tasks started (scheduled timing)")
    logger.info("  - New games: Every hour at :15")
    logger.info("  - Wishlist: Every 6 hours at :45 (00:45, 06:45, 12:45, 18:45)")
```

**Why?**

- Makes it immediately clear that scheduled timing is active
- Shows exact timing for both tasks
- Helps with debugging and monitoring

### Step 3: Verify `steam_admin.py`

#### 3.1 Check Force Command Imports

**Verify the imports are correct:**

```python
# Should import force functions, not check functions
from familybot.lib.plugin_admin_actions import force_new_game_action, force_wishlist_action
```

#### 3.2 Verify Force Commands Use Force Functions

**Check `!force` command:**

```python
@prefixed_command(name="force")
async def force_new_game_command(self, ctx: PrefixedContext):
    if str(ctx.author_id) == str(ADMIN_DISCORD_ID) and ctx.guild is None:
        await ctx.send("Forcing new game notification check...")
        from familybot.lib.plugin_admin_actions import force_new_game_action
        
        result = await force_new_game_action()  # ✅ Correct - uses force
        await ctx.send(result["message"])
        # ...
```

**Check `!force_wishlist` command:**

```python
@prefixed_command(name="force_wishlist")
async def force_wishlist_command(self, ctx: PrefixedContext):
    if str(ctx.author_id) == str(ADMIN_DISCORD_ID) and ctx.guild is None:
        await ctx.send("Forcing wishlist refresh...")
        from familybot.lib.plugin_admin_actions import force_wishlist_action
        
        result = await force_wishlist_action()  # ✅ Correct - uses force
        await ctx.send(result["message"])
        # ...
```

**No changes needed** - these should already be using the force functions. Just verify they are NOT using check functions.

---

## Phase 4: Testing Plan

### Test 1: Verify Scheduled Timing

**Objective:** Confirm tasks run at expected times

**Steps:**

1. Start the bot and note the time (e.g., 14:32)
2. Check logs for startup confirmation:

   ```text
   --Steam Family background tasks started (scheduled timing)
     - New games: Every hour at :15
     - Wishlist: Every 6 hours at :45 (00:45, 06:45, 12:45, 18:45)
   ```

3. Wait until the next :15 (e.g., 15:15)
4. Verify new game task runs:

   ```log
   [2024-01-29 15:15:00] Running scheduled new game task (hourly at :15)...
   [2024-01-29 15:15:00] Running check_new_game_action (cache-respecting)...
   ```

5. If it's a wishlist time (e.g., 18:45), verify wishlist task:

   ```log
   [2024-01-29 18:45:00] Running scheduled wishlist task (every 6 hours at :45)...
   [2024-01-29 18:45:00] Running check_wishlist_action (cache-respecting for wishlists)...
   ```

**Expected Results:**

- ✅ Tasks run at exactly :15 and :45
- ✅ Not dependent on bot startup time
- ✅ Consistent across restarts

### Test 2: Verify Cache Behavior (Automated Tasks)

**Objective:** Confirm automated tasks use cache appropriately

**Steps:**

1. Wait for new game task at :15
2. Check logs for cache usage:

   ```log
   [15:15:00] Running check_new_game_action (cache-respecting)...
   [15:15:00] No cached family library found, fetching from API...
   [15:15:00] Cached family library (150 games)
   ```

3. Wait for next task at :45 (within 30-min cache window)
4. Check logs again:

   ```log
   [15:45:00] Running check_new_game_action (cache-respecting)...
   [15:45:00] Using cached family library for new game check (150 games)
   ```

5. Wait until cache expires (30 min after first fetch)
6. Verify it fetches fresh:

   ```log
   [16:15:00] Running check_new_game_action (cache-respecting)...
   [16:15:00] No cached family library found, fetching from API...
   ```

**Expected Results:**

- ✅ First run fetches from API
- ✅ Subsequent runs within 30 min use cache
- ✅ After 30 min, fetches fresh again
- ✅ ~50% reduction in API calls

### Test 3: Verify Force Commands Bypass Cache

**Objective:** Confirm force commands always get fresh data

**Steps:**

1. Wait for automated task to populate cache
2. Immediately run `!force` command
3. Check logs for bypass behavior:

   ```lok
   [15:16:00] Running force_new_game_action (bypassing cache)...
   [15:16:00] Force refresh: Fetching fresh family library from API...
   [15:16:00] Updated family library cache with 150 games
   ```

4. Run `!force` again 10 seconds later
5. Verify it fetches fresh again (not using cache):

   ```log
   [15:16:10] Running force_new_game_action (bypassing cache)...
   [15:16:10] Force refresh: Fetching fresh family library from API...
   ```

**Expected Results:**

- ✅ Force commands never use cache
- ✅ Always fetch fresh from API
- ✅ Update cache for next regular check
- ✅ Logs clearly show "bypassing cache"

### Test 4: Verify Wishlist Cache Strategy

**Objective:** Confirm wishlists use cache but game details are fresh

**Steps:**

1. Run `!force_wishlist` to populate wishlist cache
2. Wait for scheduled wishlist task at :45
3. Check logs for cache usage:

   ```log
   [18:45:00] Running check_wishlist_action (cache-respecting for wishlists)...
   [18:45:00] Using cached wishlist for User1 (25 items)
   [18:45:00] Fetching app details from API for AppID: 123456 for wishlist
   ```

4. Verify:
   - Wishlist data uses cache
   - Game details fetched fresh (for price updates)

**Expected Results:**

- ✅ Wishlist data uses cache (2-hour TTL)
- ✅ Game details always fresh (prices)
- ✅ Balanced efficiency and accuracy

### Test 5: Integration Test

**Objective:** Verify entire system works together

**Steps:**

1. Let bot run for 24 hours
2. Monitor logs for:
   - Task timing consistency
   - Cache hit/miss rates
   - API call frequency
   - Any errors or issues

**Expected Results:**

- ✅ Tasks run at exact times every hour/6 hours
- ✅ Cache hit rate ~50% for new game checks
- ✅ No timing drift or inconsistencies
- ✅ Reduced API calls without data staleness

### Test 6: Edge Cases

**Test restart behavior:**

1. Start bot at 14:47
2. Verify next tasks:
   - 15:15 - New game check
   - 18:45 - Wishlist check
3. Restart bot at 15:30
4. Verify tasks continue at same times:
   - 15:45 - Next new game check (if within hour)
   - 16:15 - Next new game check
   - 18:45 - Wishlist check

**Test cache expiration edge cases:**

1. Populate cache at 15:00
2. Run check at 15:25 (should use cache)
3. Run check at 15:35 (should fetch fresh - cache expired)

**Test concurrent operations:**

1. Let automated task run at 15:15
2. Immediately run `!force` command
3. Verify both complete successfully without conflicts

---

## Phase 5: Deployment Strategy

### Option A: Incremental Deployment (Recommended)

#### **Day 1: Deploy Code**

1. Make code changes
2. Test locally
3. Deploy to production
4. Monitor logs closely

#### **Day 2-3: Monitor**

1. Watch for scheduled task execution
2. Verify cache behavior
3. Check API call rates
4. Look for errors

#### **Day 4-7: Optimize**

1. Adjust cache TTL if needed
2. Fine-tune task timing
3. Address any issues

### Option B: All-at-Once Deployment

#### **Single deployment with comprehensive testing:**

1. Make all changes
2. Test thoroughly in dev
3. Deploy to production
4. Monitor for 48 hours
5. Roll back if issues arise

### Option C: Gradual Rollout

#### **Phase 1:** Deploy only scheduled timing (easier to revert)

1. Update `steam_tasks.py` only
2. Keep existing cache behavior
3. Monitor timing for 1 week

#### **Phase 2:** Deploy cache strategy

1. Update `plugin_admin_actions.py`
2. Add check/force split
3. Monitor cache behavior

##### **Recommended:** Option A - gives you time to monitor and adjust

---

## Phase 6: Rollback Plan

### If Issues Arise

#### **Rollback Scheduled Timing:**

```python
# Revert to IntervalTrigger
@Task.create(IntervalTrigger(hours=1))
async def new_game_task(self):
    # ...
```

#### **Rollback Cache Strategy:**

```python
# Revert to single force function
async def force_new_game_action() -> Dict:
    # Original implementation with cache check
```

#### **Full Rollback:**

1. Restore original `plugin_admin_actions.py`
2. Restore original `steam_tasks.py`
3. Restart bot
4. Verify normal operation

##### Monitoring During Rollback

- Check logs for task execution
- Verify no data loss
- Confirm users not impacted
- Monitor API call rates

---

## Phase 7: Success Metrics

### After 1 Week

#### **Measure these metrics:**

1. **Timing Consistency**
   - ✅ Tasks run at expected times 100% of the time
   - ✅ No timing drift over days
   - ✅ Consistent across restarts

2. **Cache Performance**
   - ✅ Cache hit rate ~50% for automated tasks
   - ✅ ~50% reduction in API calls
   - ✅ No increase in stale data reports

3. **User Experience**
   - ✅ Force commands feel responsive
   - ✅ Automated updates arrive on time
   - ✅ Data appears fresh and accurate

4. **System Health**
   - ✅ No increase in errors
   - ✅ Lower API rate limiting
   - ✅ Improved debuggability

### Success Criteria

- [ ] All tasks run on schedule (100% on-time execution)
- [ ] Cache hit rate between 40-60%
- [ ] API calls reduced by at least 40%
- [ ] Zero data staleness complaints
- [ ] Force commands always get fresh data
- [ ] No timing-related bugs
- [ ] Improved log clarity for debugging

---

## Phase 8: Documentation Updates

### Update README

**Add section on task scheduling:**

```markdown
## Automated Tasks

FamilyBot runs scheduled tasks for automatic updates:

- **New Game Checks**: Every hour at :15
- **Wishlist Updates**: Every 6 hours at :45 (00:45, 06:45, 12:45, 18:45)

These tasks use intelligent caching to minimize API calls while ensuring data freshness.
```

### Update Admin Guide

**Add section on force commands:**

```markdown
## Force Commands

Admin commands that bypass cache for guaranteed fresh data:

- `!force` - Force new game check (always fetches fresh)
- `!force_wishlist` - Force wishlist refresh (always fetches fresh)

Use these when you need the most up-to-date information immediately.
```

### Add Technical Documentation

**Create `docs/CACHE_STRATEGY.md`:**

- Document cache TTLs
- Explain check vs force functions
- Show cache flow diagrams
- Troubleshooting guide

**Create `docs/TASK_SCHEDULING.md`:**

- Document task timing
- Explain timing decisions
- Show scheduling examples
- Monitoring guide

---

## Phase 9: Future Enhancements

### Short-term (Next Month)

1. **Cache Statistics**
   - Track hit/miss rates
   - Log cache performance
   - Dashboard for monitoring

2. **Configurable Timing**
   - Move timing to config.yml
   - Allow admin to customize
   - Per-guild timing support

3. **Cache Warming**
   - Pre-populate cache on startup
   - Reduce initial load time
   - Improve first-run UX

### Long-term (Next Quarter)

1. **Adaptive Caching**
   - Adjust TTL based on change frequency
   - Learn optimal cache times
   - Auto-tune performance

2. **Multi-tier Cache**
   - Redis for distributed caching
   - Shared cache across instances
   - Improved scalability

3. **Advanced Scheduling**
   - Per-user notification preferences
   - Quiet hours support
   - Smart timing based on activity

---

## Appendix A: Code Snippets Reference

### TimeTrigger Examples

```python
# Every hour at :15
TimeTrigger(hour=list(range(24)), minute=15)

# Every 6 hours at :45
TimeTrigger(hour=[0, 6, 12, 18], minute=45)

# Daily at 9 AM
TimeTrigger(hour=9, minute=0)

# Every weekday at 5 PM
TimeTrigger(day_of_week="mon-fri", hour=17, minute=0)
```

### Cache Pattern Examples

```python
# Cache-respecting pattern
cached_data = get_cached_data()
if cached_data is not None:
    logger.info("Using cached data")
    data = cached_data
else:
    logger.info("Fetching fresh data")
    data = await fetch_from_api()
    cache_data(data, ttl=30)

# Cache-bypassing pattern
logger.info("Force refresh: bypassing cache")
data = await fetch_from_api()
cache_data(data, ttl=30)  # Update cache
```

---

## Appendix B: Troubleshooting Guide

### Issue: Tasks Not Running at Expected Times

**Symptoms:**

- No log entries at :15 or :45
- Tasks running at random times
- Inconsistent scheduling

**Diagnosis:**

```python
# Check if TimeTrigger is properly configured
logger.info(f"Task trigger: {self.new_game_task.trigger}")
```

**Solutions:**

1. Verify `TimeTrigger` syntax
2. Check task is started in `on_startup`
3. Ensure bot has been running long enough to reach trigger time
4. Check timezone settings

### Issue: Cache Not Working

**Symptoms:**

- Every run fetches from API
- Cache hit rate 0%
- Logs show "No cached data found" every time

**Diagnosis:**

```python
# Check cache contents
cached = get_cached_family_library()
logger.info(f"Cache status: {cached is not None}")
if cached:
    logger.info(f"Cache has {len(cached)} items")
```

**Solutions:**

1. Verify cache is being written
2. Check cache TTL isn't too short
3. Verify cache key consistency
4. Check database permissions

### Issue: Force Commands Using Cache

**Symptoms:**

- `!force` returns instantly (should take a few seconds)
- Logs show "Using cached" in force commands
- Force commands not getting fresh data

**Diagnosis:**

```python
# Check which function is being called
logger.info(f"Function called: {func.__name__}")
```

**Solutions:**

1. Verify using `force_new_game_action()`, not `check_new_game_action()`
2. Check imports in command file
3. Verify function implementation

### Issue: Stale Data in Automated Tasks

**Symptoms:**

- Old prices shown in wishlist
- Newly added games not appearing
- Data doesn't match Steam

**Diagnosis:**

```python
# Check cache timestamps
logger.info(f"Cached at: {cache_entry['cached_at']}")
logger.info(f"Expires at: {cache_entry['expires_at']}")
logger.info(f"Current time: {datetime.now()}")
```

**Solutions:**

1. Reduce cache TTL
2. Force cache refresh
3. Check cache expiration logic

---

## Appendix C: Migration Checklist

**Before Starting:**

- [ ] Backup current codebase
- [ ] Document current behavior
- [ ] Backup database
- [ ] Test environment ready

**Code Changes:**

- [ ] Create helper functions in `plugin_admin_actions.py`
- [ ] Create `check_new_game_action()`
- [ ] Create `check_wishlist_action()`
- [ ] Update `force_new_game_action()` with clear logging
- [ ] Update `force_wishlist_action()` with clear logging
- [ ] Update `steam_tasks.py` imports
- [ ] Change to `TimeTrigger` for new game task
- [ ] Change to `TimeTrigger` for wishlist task
- [ ] Update task function calls to use `check_*`
- [ ] Update startup logging
- [ ] Verify `steam_admin.py` uses `force_*` functions

**Testing:**

- [ ] Test scheduled timing locally
- [ ] Test cache behavior (check functions)
- [ ] Test force command behavior
- [ ] Test cache expiration
- [ ] Test concurrent operations
- [ ] Test across bot restarts

**Deployment:**

- [ ] Deploy code changes
- [ ] Monitor logs for 24 hours
- [ ] Verify task timing
- [ ] Check cache statistics
- [ ] Monitor API call rates
- [ ] Check for errors

**Documentation:**

- [ ] Update README
- [ ] Update admin guide
- [ ] Create cache strategy docs
- [ ] Create scheduling docs
- [ ] Document rollback procedure

**Post-Deployment:**

- [ ] Monitor for 1 week
- [ ] Measure success metrics
- [ ] Gather user feedback
- [ ] Optimize if needed
- [ ] Document lessons learned

---

## Summary

**This plan provides:**

- ✅ Clear problem analysis
- ✅ Detailed solution design
- ✅ Step-by-step implementation
- ✅ Comprehensive testing strategy
- ✅ Deployment and rollback plans
- ✅ Success metrics and monitoring
- ✅ Future enhancement roadmap

**Estimated Timeline:**

- Code changes: 2-3 hours
- Testing: 2-4 hours
- Deployment: 1 hour
- Monitoring: 1 week

**Expected Outcomes:**

- 50% reduction in API calls
- 100% predictable task timing
- Improved debugging and monitoring
- Better user experience
- More professional bot behavior

**Next Steps:**

1. Review this plan
2. Ask questions/clarifications
3. Begin Phase 3 implementation
4. Execute testing plan
5. Deploy and monitor

Good luck! 🚀
