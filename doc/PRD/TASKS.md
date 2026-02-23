# FamilyBot — Improvement Tasks

> Tasks are ordered by recommended implementation sequence. Each task is self-contained and can be reviewed/merged independently. Complete and verify each task before starting the next.

---

## TASK-01 — Fix startup crash: add missing `token_sender` keys to config template

**Priority:** 🔴 Critical
**Effort:** XS (< 30 min)
**PRD reference:** §6.1

### Background

`config.py` reads three `token_sender` keys at import time. They are absent from `config-template.yml`, so any user who follows the standard setup flow gets an unhandled `KeyError` before the bot starts.

### Acceptance criteria

- [ ] `config-template.yml` includes a `token_sender` section with `token_save_path`, `browser_profile_path`, and `update_buffer_hours`, each with a sensible default value and an explanatory comment.
- [ ] `config.py` is unchanged — it should continue to read these keys as-is.
- [ ] Starting the bot with a config file generated from the updated template produces no `KeyError`.

### Implementation notes

Add the following to `config-template.yml`:

```yaml
token_sender:
    token_save_path: "tokens" # Directory where Steam tokens are saved
    browser_profile_path: "FamilyBotBrowserProfile" # Browser session for token extraction
    update_buffer_hours: 24 # Hours before token expiry to trigger a refresh
```

---

## TASK-02 — Fix async event loop blocking: `plugin_admin_actions.py`

**Priority:** 🔴 Critical
**Effort:** M (2–4 hrs)
**PRD reference:** §6.2
**Depends on:** Nothing

### Background

`plugin_admin_actions.py` calls `requests.get()` directly inside `async def` functions. This blocks the entire asyncio event loop — including Discord event handling — for the duration of each HTTP call. `aiohttp` is already a declared project dependency.

### Acceptance criteria

- [ ] No `requests.get` or `requests.post` calls remain inside any `async def` in this file.
- [ ] All HTTP calls use `aiohttp.ClientSession` with proper `async with` context management.
- [ ] Existing error handling (HTTP status checks, JSON decode errors, 429 retries) is fully preserved.
- [ ] `import requests` is removed from the file if no longer needed.
- [ ] `ruff check` passes on the modified file.

### Implementation notes

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

---

## TASK-03 — Fix async event loop blocking: `steam_admin.py`

**Priority:** 🔴 Critical
**Effort:** M (2–4 hrs)
**PRD reference:** §6.2
**Depends on:** TASK-02 (use the same patterns established there)

### Background

Same problem as TASK-02. `steam_admin.py` contains `requests.get()` calls inside `async def` command handlers, including inside `force_deals_command`, `force_deals_unlimited_command`, and `full_library_scan_command`.

### Acceptance criteria

- [ ] No `requests.get` or `requests.post` calls remain inside any `async def` in this file.
- [ ] All HTTP calls use `aiohttp.ClientSession`.
- [ ] Existing retry logic, error messages, and progress reporting are preserved.
- [ ] `import requests` is removed if no longer needed.
- [ ] `ruff check` passes on the modified file.

---

## TASK-04 — Fix async event loop blocking: `SteamAPIManager.make_request_with_retry`

**Priority:** 🔴 Critical
**Effort:** S (1–2 hrs)
**PRD reference:** §6.2
**Depends on:** TASK-02

### Background

`SteamAPIManager.make_request_with_retry` in `steam_api_manager.py` is declared `async def` but uses synchronous `requests.get()` internally. All callers `await` it expecting non-blocking behaviour, but it blocks the event loop on every call.

### Acceptance criteria

- [ ] `make_request_with_retry` uses `aiohttp` internally and is genuinely non-blocking.
- [ ] The method signature and return type remain compatible with all existing callers.
- [ ] Exponential backoff and 429 retry logic are preserved.
- [ ] Any `aiohttp.ClientSession` created in this method is properly closed after use.
- [ ] `import requests` is removed from `steam_api_manager.py` if no longer needed.

### Implementation notes

The method should either accept a session as a parameter (preferred for connection reuse), or create and close one per call. A session parameter makes testing easier and avoids creating a new TCP connection on every call.

---

## TASK-05 — Fix async event loop blocking: `steam_family.py` and `common_game.py`

**Priority:** 🟠 High
**Effort:** M (2–3 hrs)
**PRD reference:** §6.2
**Depends on:** TASK-04

### Background

`steam_family.py` and `common_game.py` call `requests.get()` in async command handlers. These are user-facing commands (`!coop`, `!deals`, `!common_games`) so blocking here directly degrades the Discord experience.

### Acceptance criteria

- [ ] No `requests.get` or `requests.post` in any `async def` in either file.
- [ ] `steam_family.py:coop_command` and `check_deals_command` use async HTTP.
- [ ] `common_game.py:get_common_games` uses async HTTP.
- [ ] `import requests` removed from both files if no longer needed.
- [ ] `ruff check` passes on both files.

---

## TASK-06 — Fix async event loop blocking: `family_utils.py:format_message`

**Priority:** 🟠 High
**Effort:** S (1–2 hrs)
**PRD reference:** §6.2
**Depends on:** TASK-02

### Background

`format_message` in `family_utils.py` makes synchronous `requests.get()` calls and is called directly from async functions in `plugin_admin_actions.py`. It is defined as a regular `def`, not `async def`, so it cannot use `await` — it needs to either be converted to `async def` or wrapped with `asyncio.to_thread`.

### Acceptance criteria

- [ ] `format_message` does not block the event loop when called from an async context.
- [ ] Chosen approach (convert to `async def` with `aiohttp`, or wrap calls with `asyncio.to_thread`) is applied consistently.
- [ ] All callers in `plugin_admin_actions.py` are updated accordingly.
- [ ] `ruff check` passes on modified files.

### Implementation notes

Converting to `async def` is the cleaner long-term choice. Wrapping with `asyncio.to_thread` at the call site is acceptable as a lower-risk interim step.

---

## TASK-07 — Remove duplicated family member loading logic

**Priority:** 🟠 High
**Effort:** S (1 hr)
**PRD reference:** §6.3
**Depends on:** Nothing

### Background

`load_family_members_from_db` exists in three places:

- `database.py` — canonical, includes SteamID validation via `steam.steamid.SteamID`
- `admin_commands.py` — named `load_family_members`, uses a manual string check instead of the `SteamID` class
- `plugin_admin_actions.py` — named `_load_family_members_from_db`, also uses a manual string check

The two non-canonical implementations will silently allow invalid SteamIDs that the canonical version would reject.

### Acceptance criteria

- [ ] `load_family_members` in `admin_commands.py` is deleted.
- [ ] `_load_family_members_from_db` in `plugin_admin_actions.py` is deleted.
- [ ] All callers in both files import and call `load_family_members_from_db` from `database.py`.
- [ ] No functional change to the `database.py` implementation.
- [ ] `ruff check` passes on all modified files.

---

## TASK-08 — Remove duplicated CLI argument parsing in `FamilyBot.py`

**Priority:** 🟠 High
**Effort:** S (1 hr)
**PRD reference:** §6.3
**Depends on:** Nothing

### Background

The `if __name__ == "__main__"` block and the `main()` entry-point function in `FamilyBot.py` define and handle identical argument parsers. Any change to CLI arguments currently requires editing both blocks. They have already drifted slightly in their help strings.

### Acceptance criteria

- [ ] A single private function (e.g. `_parse_and_dispatch()`) defines all arguments and handles all dispatch logic.
- [ ] Both `if __name__ == "__main__"` and `main()` call that function.
- [ ] No argument definitions or `sys.exit()` calls appear outside `_parse_and_dispatch`.
- [ ] `ruff check` passes on the modified file.

---

## TASK-09 — Consolidate deal detection into `steam_helpers.py:process_game_deal`

**Priority:** 🟠 High
**Effort:** L (4–6 hrs)
**PRD reference:** §6.3
**Depends on:** TASK-04, TASK-05

### Background

The logic for "is this game a good deal?" — discount threshold check, historical-low comparison, deal reason string formatting — is copy-pasted across:

- `steam_helpers.py:process_game_deal` (the intended canonical location)
- `steam_admin.py:force_deals_command` (inline, ~60 lines)
- `steam_admin.py:force_deals_unlimited_command` (inline again, nearly identical to above)
- `plugin_admin_actions.py:force_deals_action` (inline again)

The two admin commands differ only in game count limit and a family-sharing filter — not in deal detection logic.

### Acceptance criteria

- [ ] `process_game_deal` in `steam_helpers.py` is the single implementation of deal detection.
- [ ] `force_deals_command` and `force_deals_unlimited_command` call `process_game_deal`; they do not contain inline discount calculation.
- [ ] `force_deals_action` in `plugin_admin_actions.py` calls `process_game_deal`; it does not contain inline discount calculation.
- [ ] `force_deals_unlimited_command` is either merged into `force_deals_command` (with a parameter) or kept as a thin wrapper — no duplicated logic either way.
- [ ] Deal thresholds (30%, 15%, 1.2× buffer) are defined as named constants, not magic numbers.
- [ ] Existing command behaviour (output format, which deals are shown, progress messages) is unchanged.
- [ ] `ruff check` passes on all modified files.

### Implementation notes

Suggested refactor of the command:

```python
@prefixed_command(name="force_deals")
async def force_deals_command(
    self, ctx: PrefixedContext,
    target_friendly_name: str | None = None,
    limit: int = 100,
    family_sharing_only: bool = False,
):
    ...
    for item in global_wishlist[:limit]:
        if family_sharing_only and not game_data.get("is_family_shared"):
            continue
        deal_info = await process_game_deal(app_id, self.steam_api_manager)
        if deal_info:
            deals_found.append(deal_info)
```

---

## TASK-10 — Refactor database migrations to a declarative system

**Priority:** 🟡 Medium
**Effort:** M (2–3 hrs)
**PRD reference:** §6.4
**Depends on:** Nothing

### Background

`init_db` in `database.py` contains ~100 lines of `PRAGMA table_info` checks followed by `ALTER TABLE` calls, manually listed per-column. `migrate_database_phase1` and `migrate_database_phase2` are additional standalone functions with the same pattern. This is hard to read and error-prone to extend.

### Acceptance criteria

- [ ] A `COLUMN_MIGRATIONS` list at the top of the migrations section defines every column addition as a tuple of `(table, column, sql_definition)`.
- [ ] A single `_run_column_migrations(cursor, migrations)` helper applies the list idempotently.
- [ ] All existing per-column `ALTER TABLE` logic inside `init_db` is replaced by a call to `_run_column_migrations`.
- [ ] `migrate_database_phase1` and `migrate_database_phase2` are folded into `COLUMN_MIGRATIONS` and their standalone functions removed.
- [ ] The `detected_at` backfill `UPDATE` statement (which is data migration, not schema migration) is preserved in `init_db` after the schema migration runs.
- [ ] A fresh database and an existing database both initialise correctly.
- [ ] `ruff check` passes on the modified file.

### Implementation notes

```python
COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("saved_games",         "detected_at",      "TEXT"),
    ("game_details_cache",  "is_multiplayer",    "BOOLEAN DEFAULT 0"),
    ("game_details_cache",  "is_coop",           "BOOLEAN DEFAULT 0"),
    ("game_details_cache",  "is_family_shared",  "BOOLEAN DEFAULT 0"),
    ("game_details_cache",  "price_source",      "TEXT DEFAULT 'store_api'"),
    ("itad_price_cache",    "permanent",         "BOOLEAN DEFAULT 1"),
    ("itad_price_cache",    "lookup_method",     "TEXT DEFAULT 'appid'"),
    ("itad_price_cache",    "steam_game_name",   "TEXT"),
]

def _run_column_migrations(cursor: sqlite3.Cursor) -> None:
    for table, column, definition in COLUMN_MIGRATIONS:
        existing = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            logger.info("Migration applied: %s.%s", table, column)
```

---

## TASK-11 — Fix `asyncio.Queue` instantiation in `web_logging.py`

**Priority:** 🟡 Medium
**Effort:** XS (< 30 min)
**PRD reference:** §6.5
**Depends on:** Nothing

### Background

`WebSocketQueueHandler.__init__` calls `asyncio.Queue()` directly. In Python 3.10+, creating an `asyncio.Queue` outside a running event loop raises a `DeprecationWarning` and in some contexts a `RuntimeError`. This handler is instantiated at import time before the bot's event loop is running.

### Acceptance criteria

- [ ] `asyncio.Queue()` is not called in `__init__`.
- [ ] The queue is created lazily on first use, or the handler is restructured so it is only instantiated inside a running event loop.
- [ ] Existing code that reads `handler.queue` continues to work.
- [ ] No deprecation warnings are raised on startup related to this class.

### Implementation notes

Lazy initialisation option:

```python
class WebSocketQueueHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self._queue: asyncio.Queue | None = None

    @property
    def queue(self) -> asyncio.Queue:
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue
```

---

## TASK-12 — Guard `_migrate_gamelist_to_db` with a module-level flag

**Priority:** 🟡 Medium
**Effort:** XS (< 30 min)
**PRD reference:** §6.5
**Depends on:** Nothing

### Background

`_migrate_gamelist_to_db` in `familly_game_manager.py` is called inside `get_saved_games()`, which is called frequently (on every scheduled game check). Each call does an `os.path.exists` filesystem check for the old `gamelist.txt` file. After the first run this check always returns `False` but still happens on every invocation.

### Acceptance criteria

- [ ] A module-level boolean flag (e.g. `_migration_checked`) is set to `True` after the first call to `_migrate_gamelist_to_db`.
- [ ] Subsequent calls to `get_saved_games()` skip the migration check entirely.
- [ ] The migration still runs correctly on the first call when `gamelist.txt` exists.
- [ ] `ruff check` passes on the modified file.

---

## TASK-13 — Rename `familly_game_manager.py` to `family_game_manager.py`

**Priority:** 🟢 Low
**Effort:** XS (< 30 min)
**PRD reference:** §6.5
**Depends on:** TASK-12 (do both in one commit to avoid two renames)

### Background

The filename contains a double-l typo (`familly`). While harmless, it creates unnecessary confusion and inconsistency with all other uses of "family" in the codebase.

### Acceptance criteria

- [ ] File is renamed from `familly_game_manager.py` to `family_game_manager.py`.
- [ ] All `import` and `from ... import` statements referencing `familly_game_manager` are updated.
- [ ] `grep -r "familly_game_manager" .` returns no results after the change.
- [ ] Bot starts and `get_saved_games` / `set_saved_games` function correctly.

### Checklist of known import locations

- `src/familybot/plugins/steam_admin.py`
- `src/familybot/lib/plugin_admin_actions.py`
- Any other file found via `grep -r familly_game_manager src/`

---

## TASK-14 — Standardise type annotations to Python 3.10+ syntax

**Priority:** 🟢 Low
**Effort:** S (1–2 hrs)
**PRD reference:** §6.6
**Depends on:** All other tasks (do last to avoid conflicts)

### Background

The project targets Python 3.13, but many files still use the older `typing` module imports: `Optional[str]`, `List[str]`, `Dict[str, Any]`, `Tuple[...]`. Python 3.10+ allows `str | None`, `list[str]`, `dict[str, Any]`, `tuple[...]` directly. Mixing both styles makes the codebase harder to read.

### Acceptance criteria

- [ ] No `Optional`, `List`, `Dict`, or `Tuple` imports remain from `typing` except where required for runtime use (e.g. `TypedDict`, `TYPE_CHECKING` guards).
- [ ] All annotations use built-in generics: `str | None`, `list[str]`, `dict[str, Any]`, `tuple[str, ...]`.
- [ ] `from __future__ import annotations` is added to any file that has forward references after the change.
- [ ] `ruff check` passes on all modified files (ruff's `UP` ruleset flags most of these automatically — running `ruff check --select UP --fix` is a good starting point).
- [ ] No runtime errors are introduced (annotations that are evaluated at runtime, e.g. in dataclasses or Pydantic models, must be verified separately).

### Implementation notes

Run this to find and auto-fix the majority of cases:

```bash
uv run ruff check --select UP006,UP007,UP035 --fix src/ scripts/
```

Review the diff carefully before committing, especially in files that use Pydantic or other runtime annotation evaluation.

---

## Task Summary

| Task    | Description                                           | Priority    | Effort | Depends on       |
| ------- | ----------------------------------------------------- | ----------- | ------ | ---------------- |
| TASK-01 | Fix startup crash: add missing config keys            | 🔴 Critical | XS     | —                |
| TASK-02 | Async HTTP: `plugin_admin_actions.py`                 | 🔴 Critical | M      | —                |
| TASK-03 | Async HTTP: `steam_admin.py`                          | 🔴 Critical | M      | TASK-02          |
| TASK-04 | Async HTTP: `SteamAPIManager.make_request_with_retry` | 🔴 Critical | S      | TASK-02          |
| TASK-05 | Async HTTP: `steam_family.py`, `common_game.py`       | 🟠 High     | M      | TASK-04          |
| TASK-06 | Async HTTP: `family_utils.py:format_message`          | 🟠 High     | S      | TASK-02          |
| TASK-07 | Remove duplicated family member loading               | 🟠 High     | S      | —                |
| TASK-08 | Remove duplicated CLI argument parsing                | 🟠 High     | S      | —                |
| TASK-09 | Consolidate deal detection logic                      | 🟠 High     | L      | TASK-04, TASK-05 |
| TASK-10 | Declarative database migration system                 | 🟡 Medium   | M      | —                |
| TASK-11 | Fix `asyncio.Queue` in `web_logging.py`               | 🟡 Medium   | XS     | —                |
| TASK-12 | Guard migration check with module-level flag          | 🟡 Medium   | XS     | —                |
| TASK-13 | Rename `familly_game_manager.py`                      | 🟢 Low      | XS     | TASK-12          |
| TASK-14 | Standardise type annotations                          | 🟢 Low      | S      | All others       |

**Effort key:** XS < 30 min · S 1–2 hrs · M 2–4 hrs · L 4–6 hrs
