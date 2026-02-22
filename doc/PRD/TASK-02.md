# TASK-02 — Fix async event loop blocking: `plugin_admin_actions.py`

**Priority:** 🔴 Critical
**Effort:** M (2–4 hrs)
**PRD reference:** §6.2
**Depends on:** —

---

## Background

`plugin_admin_actions.py` calls `requests.get()` directly inside `async def` functions. This blocks the entire asyncio event loop — including Discord event handling — for the duration of each HTTP call. `aiohttp` is already a declared project dependency.

## Acceptance criteria

- [ ] No `requests.get` or `requests.post` calls remain inside any `async def` in this file.
- [ ] All HTTP calls use `aiohttp.ClientSession` with proper `async with` context management.
- [ ] Existing error handling (HTTP status checks, JSON decode errors, 429 retries) is fully preserved.
- [ ] `import requests` is removed from the file if no longer needed.
- [ ] `ruff check` passes on the modified file.

## Implementation notes

Replace the synchronous pattern:

```python
response = requests.get(url, timeout=15)
```

With the async pattern (reuse a session per function or pass one in):

```python
async with aiohttp.ClientSession() as session:
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
        data = await response.json()
```

Reference the existing `aiohttp` usage in `free_games.py` for the project's established pattern including retry logic and timeout handling.
