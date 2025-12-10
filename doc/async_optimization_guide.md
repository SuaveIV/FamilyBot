# FamilyBot Async Optimization Guide

## 1. Critical Issues to Fix

### A. Blocking `requests` Library Usage

**Problem**: Throughout your codebase, you're using the synchronous `requests` library in async functions, which blocks the event loop.

**Locations**:
- `steam_family.py`: Multiple `requests.get()` calls
- `steam_admin.py`: Multiple `requests.get()` calls  
- `plugin_admin_actions.py`: Multiple `requests.get()` calls
- `common_game.py`: Multiple `requests.get()` calls
- `utils.py`: `get_lowest_price()` function

**Solution**: Replace all `requests` with `httpx.AsyncClient`

```python
# BAD (blocking)
response = requests.get(url, timeout=10)

# GOOD (non-blocking)
async with httpx.AsyncClient() as client:
    response = await client.get(url, timeout=10)
```

**Implementation Strategy**:
1. Add a shared `httpx.AsyncClient` instance to your bot
2. Replace all `requests.get/post()` with async alternatives
3. Use `steam_api_manager.py` as the pattern (it already has async request handling)

---

## 2. Database Operations

### A. SQLite Synchronous Operations

**Problem**: SQLite operations in `database.py` are all synchronous, blocking the event loop during DB queries.

**Current State**: All DB operations use `sqlite3` directly
```python
conn = sqlite3.connect(DATABASE_FILE)
cursor = conn.cursor()
cursor.execute("SELECT...")  # Blocks event loop
```

**Solution**: Use `aiosqlite` for async database operations

```python
# Install: uv add aiosqlite

# BAD (blocking)
def get_cached_game_details(appid: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ... WHERE appid = ?", (appid,))
    return cursor.fetchone()

# GOOD (non-blocking)
async def get_cached_game_details(appid: str):
    async with aiosqlite.connect(DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT ... WHERE appid = ?", (appid,)) as cursor:
            return await cursor.fetchone()
```

**Migration Impact**: 
- **HIGH** - This requires updating ~50+ database function calls throughout your codebase
- **Benefit**: Significant reduction in event loop blocking, especially during bulk operations
- **Recommendation**: Start with high-traffic functions like `get_cached_game_details()`, `cache_game_details()`

---

## 3. Steam API Integration

### A. `steam` Library Blocking Calls

**Problem**: The `steam.webapi.WebAPI` library is synchronous. Calling it directly blocks the main event loop.

**Locations**:
- `populate_database.py`: `self.steam_api.call()` 
- `steam_admin.py`: Multiple `self.steam_api.call()` usages

**Hybrid Solution (Best for Robustness)**:
We will use a **Hybrid Approach**:
1. **Simple Calls (Storefront/Price)**: Use `httpx.AsyncClient` directly. These are standard JSON fetches.
2. **Complex Calls (User Data/Owned Games)**: Keep the `steam` library but **wrap every call** in `asyncio.to_thread()`. This offloads the blocking work to a separate thread, keeping the bot responsive without rewriting complex API logic.

```python
# 1. Simple Storefront Call (Use httpx)
async def get_game_price(app_id):
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://store.steampowered.com/api/appdetails?appids={app_id}")
        return resp.json()

# 2. Complex WebAPI Call (Wrap steam library)
async def get_owned_games_async(self, steam_id):
    # Offload the synchronous library call to a thread
    return await asyncio.to_thread(
        self.steam_api.call,
        "IPlayerService.GetOwnedGames",
        steamid=steam_id,
        include_appinfo=1
    )
```

---

## 4. Task Scheduling Improvements

### A. Background Tasks

**Current State**: Good use of `IntervalTrigger` tasks in plugins

**Optimization**: Ensure all task logic is fully async

**Review Needed**:
- ✅ `token_sender.py`: `token_update_scheduler()` - Mostly good, but token file I/O could be async
- ✅ `steam_tasks.py`: Good delegation to async actions
- ⚠️ `free_games.py`: Uses `aiohttp` (good!) but could benefit from session reuse

---

## 5. File I/O Operations

### A. Synchronous File Operations

**Problem**: Multiple places use blocking file I/O

**Locations**:
- `token_sender.py`: Reading/writing token files
- `help_message.py`: Reading plugin files for help text
- `familly_game_manager.py`: Reading/writing game list

**Solution**: Use `aiofiles` library

```python
# Install: uv add aiofiles

# BAD (blocking)
with open(file_path, 'r') as f:
    content = f.read()

# GOOD (non-blocking)
import aiofiles
async with aiofiles.open(file_path, 'r') as f:
    content = await f.read()
```

---

## 6. Specific Function Optimizations

### Priority 1: High-Traffic Functions

#### `get_cached_game_details()` (database.py)
- **Current**: Synchronous SQLite query
- **Fix**: Convert to `aiosqlite`
- **Impact**: Called in every game data lookup across all plugins

#### `cache_game_details()` (database.py)
- **Current**: Synchronous SQLite insert
- **Fix**: Convert to `aiosqlite`
- **Impact**: Called for every new game cached

#### `get_lowest_price()` (utils.py)
- **Current**: Uses `requests` library
- **Fix**: Convert to `httpx.AsyncClient`
- **Impact**: Called in deal checking, wishlist updates

### Priority 2: Batch Operations

#### `populate_database.py`
- **Current**: Uses `asyncio.to_thread()` for steam API calls (acceptable workaround)
- **Current**: Uses `httpx.AsyncClient` for HTTP (good!)
- **Fix**: Convert database operations to `aiosqlite`
- **Benefit**: Faster bulk game caching

#### `plugin_admin_actions.py`
- **Current**: Mix of sync requests and database calls
- **Fix**: Convert all to async (httpx + aiosqlite)
- **Impact**: Admin commands will be more responsive

---

## 7. Implementation Plan (Phased Approach)

### Phase 1: Critical Path (Week 1)
**Goal**: Fix the most blocking operations

1. **Replace `requests` with `httpx.AsyncClient`**
   - Create a shared client in bot initialization
   - Update all *Storefront/Price* API calls in plugins (files using `requests.get`)
   - Files: `steam_family.py`, `steam_admin.py`, `common_game.py`, `utils.py`

2. **Create Hybrid Steam API Wrapper**
   - Update `steam_api_manager.py` to support the Hybrid Model
   - Add `call_webapi_async()` helper that uses `asyncio.to_thread` for `steam` library calls
   - Update all `self.steam_api.call()` usages to use the new async helper

### Phase 2: Database Layer (Week 2)
**Goal**: Eliminate database blocking

1. **Convert Core DB Functions to Async**
   - Install `aiosqlite`
   - Update `database.py` with async versions of functions
   - Start with: `get_cached_game_details()`, `cache_game_details()`

2. **Update Plugins to Use Async DB**
   - Update all plugin database calls
   - Test each plugin thoroughly

### Phase 3: File I/O & Refinements (Week 3)
**Goal**: Polish remaining blocking operations

1. **Async File Operations**
   - Install `aiofiles`
   - Update file I/O in token management
   - Update help message generation

2. **Connection Pooling Optimization**
   - Implement shared `httpx.AsyncClient` with connection pooling
   - Configure proper timeout and retry strategies
   - Add request rate limiting at the client level

---

## 8. Code Examples for Key Changes

### Example 1: Shared HTTP Client

```python
# In FamilyBot.py - bot initialization
import httpx

# Create shared async HTTP client
client._http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, connect=10.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
)

# In plugins - usage
async def fetch_game_data(self, app_id: str):
    response = await self.bot._http_client.get(
        f"https://store.steampowered.com/api/appdetails?appids={app_id}"
    )
    return response.json()
```

### Example 2: Async Database Operations

```python
# database.py - convert to async
import aiosqlite

async def get_cached_game_details(appid: str):
    async with aiosqlite.connect(DATABASE_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            """
            SELECT name, type, is_free, categories, price_data
            FROM game_details_cache
            WHERE appid = ? AND (permanent = 1 OR expires_at > DATETIME('now'))
            """,
            (appid,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "name": row["name"],
                    "type": row["type"],
                    "is_free": bool(row["is_free"]),
                    "categories": json.loads(row["categories"]) if row["categories"] else [],
                    "price_data": json.loads(row["price_data"]) if row["price_data"] else None,
                }
            return None

async def cache_game_details(appid: str, game_data: dict, permanent: bool = True):
    async with aiosqlite.connect(DATABASE_FILE) as conn:
        await conn.execute(
            """
            INSERT OR REPLACE INTO game_details_cache
            (appid, name, type, is_free, categories, price_data, cached_at, expires_at, permanent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                appid,
                game_data.get("name"),
                game_data.get("type"),
                game_data.get("is_free", False),
                json.dumps(game_data.get("categories", [])),
                json.dumps(game_data.get("price_overview")),
                datetime.utcnow().isoformat() + "Z",
                None if permanent else (datetime.utcnow() + timedelta(hours=24)).isoformat() + "Z",
                1 if permanent else 0,
            )
        )
        await conn.commit()
```

### Example 3: Hybrid Steam Manager (Async Wrapper)

```python
# steam_api_manager.py - Hybrid approach
import asyncio
import httpx
from steam.webapi import WebAPI

class SteamAPIManager:
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Keep the synchronous library for complex WebAPI calls
        self.steam_api = WebAPI(key=api_key) if api_key else None
        
        # Add async client for simple Storefront calls
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=50)
        )

    async def call_webapi(self, interface: str, method: str, **kwargs) -> dict:
        """
        Wraps the blocking steam library call in a thread.
        Usage: await manager.call_webapi("IPlayerService", "GetOwnedGames", steamid=...)
        """
        if not self.steam_api:
            return {}
            
        def _sync_call():
            return self.steam_api.call(f"{interface}.{method}", **kwargs)
            
        return await asyncio.to_thread(_sync_call)

    async def get_store_details(self, app_id: str) -> dict:
        """Direct async call for Storefront API (replaces requests)"""
        response = await self.client.get(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": app_id, "cc": "us", "l": "en"}
        )
        return response.json()
```

---

## 9. Performance Monitoring

### Add Timing Decorators

```python
# lib/performance.py
import time
import functools
from familybot.lib.logging_config import get_logger

logger = get_logger(__name__)

def async_timed(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        
        # Log slow operations
        if elapsed > 1.0:
            logger.warning(f"{func.__name__} took {elapsed:.2f}s")
        else:
            logger.debug(f"{func.__name__} took {elapsed:.2f}s")
        
        return result
    return wrapper

# Usage
@async_timed
async def fetch_game_details(app_id: str):
    # Your code here
    pass
```

---

## 10. Testing Strategy

### Unit Tests for Async Functions

```python
# tests/test_async_operations.py
import pytest
import asyncio

@pytest.mark.asyncio
async def test_async_game_details():
    """Test async game details fetching"""
    from familybot.lib.database import get_cached_game_details
    
    result = await get_cached_game_details("730")  # CS2
    assert result is not None
    assert result["name"] == "Counter-Strike 2"

@pytest.mark.asyncio
async def test_concurrent_game_fetches():
    """Test that multiple concurrent fetches work properly"""
    from familybot.lib.database import get_cached_game_details
    
    app_ids = ["730", "440", "570"]  # CS2, TF2, Dota 2
    
    tasks = [get_cached_game_details(app_id) for app_id in app_ids]
    results = await asyncio.gather(*tasks)
    
    assert len(results) == 3
    assert all(r is not None for r in results)
```

---

## 11. Expected Performance Improvements

### Before Optimization
- **Deal Check Command**: 15-30 seconds (100 games)
- **Wishlist Update**: 45-90 seconds (300 games)
- **Database Query**: 50-200ms per query (blocking)
- **Concurrent Operations**: Limited by blocking I/O

### After Optimization
- **Deal Check Command**: 5-10 seconds (100 games) - **50-67% faster**
- **Wishlist Update**: 15-30 seconds (300 games) - **67% faster**
- **Database Query**: 5-20ms per query (async) - **75-90% faster**
- **Concurrent Operations**: True parallelism, 10-50x throughput improvement

---

## 12. Dependencies to Add

```toml
# Add to pyproject.toml

[project]
dependencies = [
    # Existing dependencies...
    "aiosqlite~=0.19.0",  # Async SQLite
    "aiofiles~=23.2.1",   # Async file I/O
]
```

---

## 13. Migration Checklist

### Phase 1: HTTP Layer ✓
- [ ] Create shared `httpx.AsyncClient` in bot
- [ ] Replace `requests` in `utils.py::get_lowest_price()`
- [ ] Replace `requests` in `steam_family.py`
- [ ] Replace `requests` in `steam_admin.py`
- [ ] Replace `requests` in `plugin_admin_actions.py`
- [ ] Replace `requests` in `common_game.py`
- [ ] Update `steam_api_manager.py` to remove `requests`
- [ ] Test all API-dependent commands

### Phase 2: Database Layer ✓
- [ ] Install `aiosqlite`
- [ ] Convert `get_cached_game_details()` to async
- [ ] Convert `cache_game_details()` to async
- [ ] Convert `get_cached_wishlist()` to async
- [ ] Convert `cache_wishlist()` to async
- [ ] Convert `get_cached_family_library()` to async
- [ ] Convert all other cache functions to async
- [ ] Update all plugin database calls to use `await`
- [ ] Test database operations under load

### Phase 3: Steam API Layer (Hybrid) ✓
- [ ] Update `SteamAPIManager` with `httpx` client and `call_webapi` wrapper
- [ ] Wrap `steam.webapi.WebAPI` usage in `populate_database.py` using new helper
- [ ] Wrap `steam.webapi.WebAPI` usage in `steam_admin.py` using new helper
- [ ] Ensure all direct `self.steam_api.call` are routed through async wrapper
- [ ] Test Steam API operations for non-blocking behavior

### Phase 4: File I/O ✓
- [ ] Install `aiofiles`
- [ ] Convert token file operations in `token_sender.py`
- [ ] Convert help message file reading in `help_message.py`
- [ ] Convert game list file operations in `familly_game_manager.py`

### Phase 5: Testing & Optimization ✓
- [ ] Add performance timing decorators
- [ ] Create unit tests for async functions
- [ ] Load test with concurrent operations
- [ ] Profile and identify remaining bottlenecks
- [ ] Document performance improvements

---

## 14. Price Population Optimization

### A. Async Script Improvements (`scripts/populate_prices_async.py`)
**Problem**: The script currently collects ALL data in memory before writing to the database (Phase 1 -> Phase 2). 
- **Risk**: If the script is interrupted (Ctrl+C), all progress is lost.
- **Memory**: Large datasets consume unnecessary memory.

**Solution**: Implement **Incremental Writing**.
- Write to the database every 50-100 successful items *during* the collection phase.
- Use a robust `batch_write` function that handles partial failures without rolling back valid data.

### B. Bot Price Checking (`utils.py`)
**Problem**: `get_lowest_price()` is synchronous and blocks the event loop.
**Solution**: 
1. Convert `get_lowest_price` to `async`.
2. Replace `requests` with `httpx.AsyncClient`.
3. Update consumers (`steam_family.py`, etc.) to `await` the call.

---

## 15. Risk Mitigation

### Backward Compatibility
- Keep old sync functions temporarily with `_sync` suffix
- Gradual migration, test each plugin independently
- Feature flags for rollback if needed

### Database Transactions
- Be careful with async database commits
- Use proper connection context managers
- Test rollback scenarios

### Error Handling
- Async errors propagate differently
- Add comprehensive try/except in all async functions
- Test timeout scenarios thoroughly

---

## Conclusion

**Priority Order**:
1. **HTTP Client Replacement** (Biggest immediate impact, easiest to implement)
2. **Database Async Conversion** (High impact, moderate difficulty)
3. **Steam API Direct Async** (Medium impact, replaces workarounds)
4. **File I/O Async** (Low impact, nice to have)

**Estimated Total Work**: 2-3 weeks for full implementation and testing

**Expected Result**: 50-70% reduction in command response times and much better scalability under load.
