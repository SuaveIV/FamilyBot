# FamilyBot Implementation Plan

Technical debt remediation and improvement roadmap based on codebase audit.

---

## Changes by File

### `src/familybot/lib/database.py`

The most touched file. Multiple improvements here should be batched together.

| Task | Priority | Effort | Description                                                                                                           |
| ---- | -------- | ------ | --------------------------------------------------------------------------------------------------------------------- |
| 1.2  | Critical | Medium | Fix thread safety — replace `check_same_thread=False` with proper write serialization (async queue or `asyncio.Lock`) |
| 2.1  | High     | Medium | Connection pooling — stop opening a new connection per operation; use module-level or thread-local connection         |
| 2.2  | High     | Low    | Normalize game data — add `normalize_game_data()` called at cache write and read points                               |
| 2.3  | High     | Low    | Migration state — replace `_family_members_migrated_this_run` boolean with a `migrations` table                       |
| 4.4  | Low      | Medium | Type annotations — add return types to all database helpers                                                           |

**Suggested order:** Do 1.2 + 2.1 together (both change connection handling). Then 2.3, then 2.2, then 4.4 incrementally.

---

### `src/familybot/lib/family_utils.py`

| Task | Priority | Effort | Description                                                                                           |
| ---- | -------- | ------ | ----------------------------------------------------------------------------------------------------- |
| 1.3  | Critical | Low    | Wrap `get_lowest_price` calls in `asyncio.to_thread()` (or convert to async with `httpx.AsyncClient`) |
| 2.2  | High     | Low    | Consume normalized game data from `normalize_game_data()`                                             |
| 2.4  | High     | Medium | Parallelize wishlist HTTP calls — replace sequential `await` loop with `asyncio.gather()` + semaphore |
| 4.4  | Low      | Medium | Add return type annotations                                                                           |

**Suggested order:** 1.3 first (correctness), then 2.4 (performance), then 2.2 + 4.4 together.

---

### `src/familybot/lib/plugin_admin_actions.py`

| Task | Priority | Effort | Description                                                                                                              |
| ---- | -------- | ------ | ------------------------------------------------------------------------------------------------------------------------ |
| 1.1  | Critical | Low    | Remove API key from f-string URLs — use `params=` argument instead                                                       |
| 3.1  | Medium   | High   | Extract into — command handlers in `steam_admin.py`/`steam_family.py` should call into here instead of duplicating logic |
| 3.3  | Medium   | Low    | Add transactions — group `cache_game_details` calls into single transaction with `BEGIN`/`COMMIT`                        |
| 4.4  | Low      | Medium | Add return type annotations                                                                                              |

**Suggested order:** 1.1 immediately, then 3.3 when touching cache code, then 3.1 as a larger refactor.

---

### `src/familybot/plugins/steam_family.py`

| Task | Priority | Effort | Description                                                                                          |
| ---- | -------- | ------ | ---------------------------------------------------------------------------------------------------- |
| 1.1  | Critical | Low    | Remove API key from f-string URLs                                                                    |
| 3.1  | Medium   | High   | Extract business logic — move data-fetching and formatting out of command handlers into `lib/` layer |

**Suggested order:** 1.1 immediately. 3.1 when doing the broader plugin refactor.

---

### `src/familybot/plugins/steam_admin.py`

| Task | Priority | Effort | Description                                                                                     |
| ---- | -------- | ------ | ----------------------------------------------------------------------------------------------- |
| 3.1  | Medium   | High   | Extract business logic — move data-fetching out of command handlers                             |
| 4.2  | Low      | Low    | Fix progress reporting — edit a single message instead of sending new ones to avoid rate limits |

**Suggested order:** 4.2 can be done quickly. 3.1 as part of broader refactor.

---

### `src/familybot/config.py`

| Task | Priority | Effort | Description                                                                                        |
| ---- | -------- | ------ | -------------------------------------------------------------------------------------------------- |
| 1.4  | Critical | Low    | Add startup validation — check for missing/placeholder values, wrong types, and raise clear errors |

**Suggested order:** Do this early. Low effort, high value.

---

### `src/familybot/lib/steam_api_manager.py`

| Task | Priority | Effort | Description                                                                     |
| ---- | -------- | ------ | ------------------------------------------------------------------------------- |
| 4.4  | Low      | Medium | Add return type annotations to `handle_api_response`, `make_request_with_retry` |

**Suggested order:** Incremental, when touching the file.

---

### `src/familybot/plugins/token_sender.py`

| Task | Priority | Effort | Description                                             |
| ---- | -------- | ------ | ------------------------------------------------------- |
| 3.4  | Medium   | Low    | Add file locking — use `filelock` around token file I/O |

**Suggested order:** When touching token code. Quick win.

---

### `inspect_db.py` (project root)

| Task | Priority | Effort | Description                                                                                                  |
| ---- | -------- | ------ | ------------------------------------------------------------------------------------------------------------ |
| 4.3  | Low      | Low    | Relocate — move to `scripts/`, import path logic from `lib/database.py`, update `pyproject.toml` entry point |

**Suggested order:** Quick cleanup when you have a spare hour.

---

### `pyproject.toml`

| Task | Priority | Effort | Description                                                            |
| ---- | -------- | ------ | ---------------------------------------------------------------------- |
| 2.5  | High     | High   | Update entry points if price script consolidation changes script names |
| 4.3  | Low      | Low    | Update `inspect_db` entry point path after relocation                  |

---

### New Files

| File                                    | Task | Priority | Effort | Description                                                                                    |
| --------------------------------------- | ---- | -------- | ------ | ---------------------------------------------------------------------------------------------- |
| `src/familybot/lib/price_client.py`     | 2.5  | High     | High   | Shared `PriceClient` class with Steam Store API fetch, ITAD lookup, batch write, rate limiting |
| `src/familybot/lib/wishlist_service.py` | 3.1  | Medium   | High   | Extracted wishlist logic from plugin command handlers                                          |
| `src/familybot/lib/token_io.py`         | 3.4  | Medium   | Low    | `read_token()`/`write_token()` with file locking                                               |

---

### Scripts (batch changes)

| File                                   | Task | Priority | Effort | Description                                                |
| -------------------------------------- | ---- | -------- | ------ | ---------------------------------------------------------- |
| `scripts/populate_prices.py`           | 2.5  | High     | High   | Refactor into thin orchestrator using shared `PriceClient` |
| `scripts/populate_prices_optimized.py` | 2.5  | High     | High   | Deprecate or redirect to unified script                    |
| `scripts/populate_prices_async.py`     | 2.5  | High     | High   | Deprecate or redirect to unified script                    |

---

## Recommended Execution Order

### ~~Sprint 1: Critical~~ ✅ COMPLETE (PR #12)

1. ~~`config.py` — add validation (1.4)~~ ✅
2. ~~`steam_family.py` + `plugin_admin_actions.py` — remove API keys from URLs (1.1)~~ ✅
3. ~~`family_utils.py` — wrap sync I/O calls (1.3)~~ ✅ (already complete)

### Sprint 2: Database overhaul (batch changes to `database.py`) — ✅ COMPLETE (PR #13)

1. ~~`database.py` — thread safety + connection pooling (1.2 + 2.1)~~
2. ~~`database.py` — migration state table (2.3)~~
3. ~~`database.py` — normalize game data function (2.2)~~

### Sprint 3: Performance

1. `family_utils.py` — parallelize wishlist HTTP calls (2.4)
2. Scripts — consolidate price population scripts (2.5)

### Sprint 4: Maintainability (can be incremental)

1. Plugins — extract business logic (3.1)
2. `plugin_admin_actions.py` — add batch transactions (3.3)
3. `token_sender.py` — add file locking (3.4)
4. All files — tighten exception handling (3.2)

### Sprint 5: Cleanup (opportunistic)

1. `inspect_db.py` — relocate (4.3)
2. `steam_admin.py` — fix rate limiting (4.2)
3. Registration — Steam ID validation (4.1)
4. All core files — type annotations (4.4)

---

## Testing Strategy

- **Sprint 1:** Manual verification + existing integration tests
- **Sprint 2:** Add concurrent write tests for connection pooling
- **Sprint 3:** Benchmark wishlist parallelization; verify consolidated scripts produce identical output
- **Sprint 4:** Unit tests for extracted logic; mypy for type annotations
- **Sprint 5:** Incremental type checking

---

## Notes

- Tasks 1.2 and 2.1 should be done together since both touch `database.py` connection handling
- Task 2.5 (consolidate scripts) is the highest effort item and can be deferred if time is tight
- Task 3.1 (extract business logic) is the highest effort maintainability win and unlocks testability
