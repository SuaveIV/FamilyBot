# TASK-03 — Fix async event loop blocking: `steam_admin.py`

**Priority:** 🔴 Critical  
**Effort:** M (2–4 hrs)  
**PRD reference:** §6.2  
**Depends on:** TASK-02 (use the same patterns established there)

---

## Background

Same problem as TASK-02. `steam_admin.py` contains `requests.get()` calls inside `async def` command handlers, including inside `force_deals_command`, `force_deals_unlimited_command`, and `full_library_scan_command`.

## Acceptance criteria

- [ ] No `requests.get` or `requests.post` calls remain inside any `async def` in this file.
- [ ] All HTTP calls use `aiohttp.ClientSession`.
- [ ] Existing retry logic, error messages, and progress reporting are preserved.
- [ ] `import requests` is removed if no longer needed.
- [ ] `ruff check` passes on the modified file.

## Implementation notes

Follow the same `aiohttp` pattern established in TASK-02. The three affected command handlers are:

- `force_deals_command` — calls `requests.get` for each wishlist game's app details
- `force_deals_unlimited_command` — same pattern, no game limit
- `full_library_scan_command` — calls `requests.get` for each game in each member's library

All three can share a single `aiohttp.ClientSession` created at the top of the command handler and passed through to any helper calls, rather than opening a new session per request.
