# Remaining Improvement Tasks

This document tracks the remaining tasks for the FamilyBot overhaul, including items from the original PRD and feedback from Pull Request #4.

---

## 🛠️ PR #4 Refinements

Tasks identified during the review of PR #4 that require implementation or correction.

### P4-01 — Fix `appid` validation in all wishlist loops
**Priority:** 🔴 Critical
**Description:** Mirror the `appid` validation fix from `plugin_admin_actions.py` to `steam_family.py` and `steam_admin.py`.
- [ ] Update `src/familybot/plugins/steam_family.py:check_deals_command` to validate `raw_app_id` before string conversion.
- [ ] Update `src/familybot/plugins/steam_admin.py` wishlist loops (if any remain after TASK-09) to use the same validation.
- [ ] Ensure `None` is never converted to the string `"None"`.

### P4-02 — Centralize rate-limiting constants
**Priority:** 🟠 High
**Description:** Rate-limit constants are currently duplicated across `steam_family.py` and `plugin_admin_actions.py`.
- [ ] Use `STEAM_API_RATE_LIMIT`, `STEAM_STORE_API_RATE_LIMIT`, and `FULL_SCAN_RATE_LIMIT` from `src/familybot/lib/constants.py`.
- [ ] Remove local re-definitions in all files.

### P4-03 — Fix Token Bucket `acquire` jitter
**Priority:** 🟠 High
**Description:** The `acquire` method in `src/familybot/lib/utils.py` updates `last_update` before awaiting, which double-credits elapsed time.
- [ ] Update `last_update` only *after* the `asyncio.sleep` call.

### P4-04 — Fix `make_request_with_retry` jitter placement
**Priority:** 🟠 High
**Description:** `SteamAPIManager.make_request_with_retry` and `admin_commands.py:make_request_with_retry` should only apply jitter on *retry* attempts.
- [ ] Wrap the jitter calculation/sleep in `if attempt > 0`.

### P4-05 — Modernize `datetime` usage
**Priority:** 🟢 Low
**Description:** `datetime.utcnow()` is deprecated in Python 3.12+.
- [ ] Replace all occurrences with `datetime.now(timezone.utc)`.
- [ ] Update imports to include `timezone` from `datetime`.

### P4-06 — Reuse `ClientSession` in `free_games.py`
**Priority:** 🟢 Low
**Description:** `_process_single_post` should accept and forward an existing `aiohttp.ClientSession`.
- [ ] Update `_process_single_post` signature.
- [ ] Pass the session from the parent calling loop.

---

## 📋 PRD Tasks (Remaining)

Tasks from the original `doc/PRD/TASKS.md` that are still outstanding.

### TASK-09 — Consolidate deal detection logic
**Priority:** 🟠 High
**Description:** Move deal detection logic from `steam_admin.py` and `plugin_admin_actions.py` into the shared `steam_helpers.py:process_game_deal`.
- [ ] Update all callers to use the centralized helper.
- [ ] Remove inline discount/historical-low calculations from admin commands.

### TASK-10 — Declarative database migration system
**Priority:** 🟡 Medium
**Description:** Replace imperative `ALTER TABLE` calls in `database.py` with a declarative `COLUMN_MIGRATIONS` list and a helper.
- [ ] Implement `COLUMN_MIGRATIONS` list and `_run_column_migrations` helper.

### TASK-11 — Fix `asyncio.Queue` in `web_logging.py`
**Priority:** 🟡 Medium
**Description:** `asyncio.Queue()` is currently instantiated in `__init__`, potentially outside a running event loop.
- [ ] Implement lazy initialization for the queue via a property.

### TASK-12 — Guard migration check with module-level flag
**Priority:** 🟡 Medium
**Description:** Prevent repeated `os.path.exists` calls for `gamelist.txt` in `family_game_manager.py`.
- [ ] Add `_migration_checked` flag to the module.

### TASK-13 — Rename `familly_game_manager.py` to `family_game_manager.py`
**Priority:** 🟢 Low
**Description:** Correct the double-l typo in the filename and all imports.
- [ ] Rename file and update all `import` references.

### TASK-14 — Standardise type annotations to Python 3.10+ syntax
**Priority:** 🟢 Low
**Description:** Replace `Optional`, `List`, `Dict` with built-in generics and `|` operator.
- [ ] Run `ruff check --select UP006,UP007,UP035 --fix`.
- [ ] Verify manual fixes for forward references or runtime evaluations.

---

## ✅ Completed Tasks
- [x] TASK-01 through TASK-07 (Core Async/Config Fixes)
- [x] TASK-08 (CLI Argument Consolidation)
- [x] Automatic Update Fix (Automatic vs Forced mismatch)
- [x] Scoping bug fix in `steam_family.py:coop_command`
- [x] Blocking `get_lowest_price` thread offloading
- [x] `format_message` keyword-only and optimization
- [x] `plugin_admin_actions.py` appid validation & refactor
- [x] `steam_helpers.py` price normalization
