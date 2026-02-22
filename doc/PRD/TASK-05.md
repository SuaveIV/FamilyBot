# TASK-05 — Fix async event loop blocking: `steam_family.py` and `common_game.py`

**Priority:** 🟠 High  
**Effort:** M (2–3 hrs)  
**PRD reference:** §6.2  
**Depends on:** TASK-04

---

## Background

`steam_family.py` and `common_game.py` call `requests.get()` in async command handlers. These are user-facing commands (`!coop`, `!deals`, `!common_games`) so blocking here directly degrades the Discord experience for all users during any HTTP call.

## Acceptance criteria

- [ ] No `requests.get` or `requests.post` in any `async def` in either file.
- [ ] `steam_family.py:coop_command` uses async HTTP for Steam Store API calls.
- [ ] `steam_family.py:check_deals_command` uses async HTTP for Steam Store API calls.
- [ ] `common_game.py:get_common_games` uses async HTTP for both `GetOwnedGames` and `appdetails` calls.
- [ ] `import requests` removed from both files if no longer needed.
- [ ] `ruff check` passes on both files.

## Implementation notes

Both files make two distinct types of HTTP calls:

1. **Steam Web API calls** (e.g. `GetOwnedGames`) — these can go through `SteamAPIManager.make_request_with_retry` once TASK-04 is complete, so no additional work is needed for those call sites beyond removing the direct `requests` calls.
2. **Steam Store API calls** (e.g. `appdetails`) — use `aiohttp.ClientSession` directly, following the pattern from TASK-02.

Verify that the progress messages and per-game error handling in `common_game.py:get_common_games` continue to work correctly after the refactor, as this command iterates over potentially hundreds of games.
