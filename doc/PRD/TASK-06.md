# TASK-06 — Fix async event loop blocking: `family_utils.py:format_message`

**Priority:** 🟠 High  
**Effort:** S (1–2 hrs)  
**PRD reference:** §6.2  
**Depends on:** TASK-02

---

## Background

`format_message` in `family_utils.py` makes synchronous `requests.get()` calls and is called directly from async functions in `plugin_admin_actions.py`. It is defined as a regular `def`, not `async def`, so it cannot use `await` — it needs to either be converted to `async def` or wrapped with `asyncio.to_thread`.

## Acceptance criteria

- [ ] `format_message` does not block the event loop when called from an async context.
- [ ] Chosen approach (convert to `async def` with `aiohttp`, or wrap with `asyncio.to_thread`) is applied consistently.
- [ ] All callers in `plugin_admin_actions.py` are updated accordingly.
- [ ] `ruff check` passes on all modified files.

## Implementation notes

Two viable approaches:

**Option A — Convert to `async def` (preferred):** Replace the `requests.get` calls with `aiohttp` and make the function `async`. All callers must then `await` it. This is the cleaner long-term solution.

**Option B — Wrap at call site (lower risk):** Keep `format_message` synchronous and wrap each call site:

```python
wishlist_message = await asyncio.to_thread(format_message, duplicate_games_for_display)
```

Option B is acceptable as an interim step but should be noted as tech debt to revisit. Option A is preferred.
