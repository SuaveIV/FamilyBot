# FamilyBot — Code Quality & Reliability Improvement PRD

**Version:** 1.0
**Status:** Draft
**Owner:** FamilyBot Engineering
**Last Updated:** 2026-02-22

---

## 1. Overview

FamilyBot is a Discord bot that tracks Steam Family libraries, monitors wishlists for deals, and surfaces free game opportunities. The bot is operational and feature-complete, but a review of the codebase has identified a set of reliability, correctness, and maintainability issues that carry real user-facing risk. This document defines the scope, goals, and success criteria for a focused code quality sprint to address those issues before they result in outages or become harder to untangle as the codebase grows.

---

## 2. Problem Statement

Several categories of problems have been identified:

**Crash risk at startup.** `config.py` reads `token_sender` configuration keys that do not exist in `config-template.yml`. Any user following the standard setup flow will encounter an unhandled `KeyError` and the bot will not start.

**Event loop blocking.** A large number of `async` functions across the codebase call the synchronous `requests` library directly. This blocks the entire asyncio event loop — including all Discord event processing — for the duration of each HTTP request. Under normal operation this causes perceptible lag; under slow or failing network conditions it can freeze the bot entirely.

**Duplicated business logic.** The same code — particularly family member loading, CLI argument parsing, and deal-checking — has been copied across multiple files rather than extracted into shared functions. This means bugs need to be fixed in multiple places and the implementations have quietly diverged.

**Fragile database migrations.** Schema evolution is handled by ad-hoc `PRAGMA table_info` checks scattered across `init_db`. This works but is hard to read, hard to extend, and easy to get wrong.

**Minor correctness issues.** `asyncio.Queue()` is instantiated outside a running event loop in `web_logging.py`. The `_migrate_gamelist_to_db` filesystem check runs on every `get_saved_games()` call. Type annotation style is inconsistent across a Python 3.13 codebase.

---

## 3. Goals

- **G1** — Eliminate known startup crashes so a user following `config-template.yml` can run the bot without any manual fixes.
- **G2** — Remove all synchronous HTTP calls from async contexts so the event loop is never blocked.
- **G3** — Establish single sources of truth for family member loading, argument parsing, and deal detection logic.
- **G4** — Replace ad-hoc migration checks with a structured, declarative migration system.
- **G5** — Fix the remaining minor correctness issues (event loop queue init, redundant filesystem checks, naming).
- **G6** — Standardize code style so the codebase reads consistently and is easier to onboard contributors to.

---

## 4. Non-Goals

- No new user-facing features in this sprint.
- No changes to the database schema or the data model beyond what migration refactoring requires.
- No changes to plugin business logic beyond removing duplicates and fixing blocking calls.
- No UI or web dashboard changes.
- No performance benchmarking or load testing.

---

## 5. User Stories

| ID   | As a…        | I want…                                                                 | So that…                                                          |
| ---- | ------------ | ----------------------------------------------------------------------- | ----------------------------------------------------------------- |
| US-1 | New user     | The bot to start after filling in `config-template.yml`                 | I don't waste time debugging a crash that shouldn't exist         |
| US-2 | Bot operator | Discord commands to respond promptly even while API calls are in flight | The bot doesn't appear frozen                                     |
| US-3 | Bot operator | A deal, wishlist, or game-check error to be isolated to that operation  | One failed API call doesn't take down unrelated features          |
| US-4 | Contributor  | To find each piece of logic in exactly one place                        | I know where to make a change and that it will apply everywhere   |
| US-5 | Contributor  | Database migrations to be easy to read and extend                       | I can add a new column without fear of breaking existing installs |

---

## 6. Functional Requirements

### 6.1 Configuration — Startup Crash Fix

- `config-template.yml` must include all keys that `config.py` reads at import time, with sensible defaults.
- Keys that are missing must cause a clear error message, not an unhandled `KeyError`.
- Affected keys: `token_sender.token_save_path`, `token_sender.browser_profile_path`, `token_sender.update_buffer_hours`.

### 6.2 Async HTTP — Event Loop Safety

- No `requests.get()` or `requests.post()` call may appear directly inside an `async def` function body.
- All HTTP in async contexts must use either `aiohttp` (preferred for new code) or `asyncio.to_thread(requests.get, ...)` as a transition wrapper.
- Affected files: `plugin_admin_actions.py`, `steam_admin.py`, `steam_family.py`, `common_game.py`, `family_utils.py`.
- `SteamAPIManager.make_request_with_retry` must be made truly async (currently `async def` but uses synchronous `requests` internally).
- The existing `aiohttp` usage in `free_games.py` is the reference pattern.

### 6.3 Code Deduplication

#### Family Member Loading

- `load_family_members_from_db` in `database.py` is the canonical implementation.
- The duplicated implementations in `admin_commands.py` (`load_family_members`) and `plugin_admin_actions.py` (`_load_family_members_from_db`) must be deleted.
- All callers must import from `database.py`.

#### CLI Argument Parsing

- The `if __name__ == "__main__"` block and `main()` function in `FamilyBot.py` share identical argument definitions and handling logic.
- Extract to a single private `_parse_and_dispatch(args)` function called from both entry points.

#### Deal Detection Logic

- `steam_helpers.py:process_game_deal` is the correct abstraction for checking whether a game is on sale.
- `force_deals_command` and `force_deals_unlimited_command` in `steam_admin.py` must be refactored to call `process_game_deal` rather than re-implementing the detection inline.
- `plugin_admin_actions.py:force_deals_action` must similarly delegate to `process_game_deal`.
- The two admin commands differ only in game limit and family-sharing filter; these should become parameters, not separate commands. `force_deals_unlimited_command` may be kept as a thin alias or merged.

### 6.4 Database Migration Refactor

- All `ALTER TABLE` migration logic must be extracted from `init_db` into a structured migrations list.
- Each migration entry specifies: table name, column name, column definition.
- The runner iterates the list, checks `PRAGMA table_info`, and applies missing columns.
- `migrate_database_phase1` and `migrate_database_phase2` standalone functions must be folded into the unified system and the public functions removed or deprecated.
- Existing behaviour (idempotent, safe to run on every startup) must be preserved.

### 6.5 Minor Correctness Fixes

- `WebSocketQueueHandler.__init__` in `web_logging.py` must not call `asyncio.Queue()` directly; the queue must be lazily initialised on first use or created inside an async context.
- The `_migrate_gamelist_to_db` call in `familly_game_manager.py` must be guarded by a module-level flag so the filesystem check runs at most once per process.
- The filename `familly_game_manager.py` (double-l) should be corrected to `family_game_manager.py` with all imports updated.

### 6.6 Code Style Standardisation

- All type annotations across the codebase must use the Python 3.10+ union syntax (`str | None`, `list[str]`) instead of `Optional[str]`, `List[str]`.
- `from __future__ import annotations` may be used for forward references where needed.
- Existing `Optional` and `List` imports from `typing` must be removed from files where they are no longer needed after annotation updates.

---

## 7. Non-Functional Requirements

- **No regressions.** Every existing bot command must continue to work after each change. Changes should be made incrementally and tested after each task.
- **Backwards compatibility.** The SQLite database format must remain readable by the current schema after the migration refactor.
- **No new dependencies** beyond what is already in `pyproject.toml`, with the exception of `aiohttp` which is already a declared dependency.
- **Lint clean.** All modified files must pass `ruff check` and `ruff format` without errors.

---

## 8. Out of Scope

- Connection pooling for SQLite.
- Switching from SQLite to another database engine.
- Adding automated tests (a future sprint concern).
- Web UI changes.
- New Discord commands.

---

## 9. Risks & Mitigations

| Risk                                                                                       | Likelihood | Impact | Mitigation                                                                                                                                |
| ------------------------------------------------------------------------------------------ | ---------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Async HTTP refactor introduces subtle bugs in retry/error handling logic                   | Medium     | High   | Refactor one file at a time; verify existing error paths are preserved                                                                    |
| Renaming `familly_game_manager.py` breaks an import somewhere not caught in review         | Low        | Medium | `grep -r familly_game_manager` before and after; run the bot to confirm startup                                                           |
| Deduplication of family member loading changes behaviour for edge cases (invalid SteamIDs) | Low        | Low    | The canonical `database.py` version already handles SteamID validation via `steam.steamid.SteamID`; ensure all callers get that behaviour |
| Migration refactor causes double-application of a column add on existing installs          | Low        | Medium | The `PRAGMA table_info` check is idempotent by design; verify this is preserved                                                           |

---

## 10. Success Criteria

- [x] A fresh install following `config-template.yml` starts the bot without errors.
- [ ] No `requests.get` or `requests.post` calls appear in `async def` function bodies (verifiable via `grep`).
- [ ] `load_family_members_from_db` appears in exactly one file (`database.py`).
- [ ] CLI argument definitions appear in exactly one function in `FamilyBot.py`.
- [ ] Deal detection logic lives in `steam_helpers.py:process_game_deal`; all callers use it.
- [ ] `init_db` migration logic is driven by a declarative list; no `ALTER TABLE` strings appear outside it.
- [ ] `asyncio.Queue()` is not called at module import time.
- [ ] `_migrate_gamelist_to_db` is guarded by a module-level flag.
- [ ] `familly_game_manager.py` is renamed and all references updated.
- [ ] All modified files pass `ruff check` and `ruff format`.
- [ ] Bot starts and all commands function normally after all tasks are complete.

---

## 11. Delivery

All tasks are captured in `TASKS.md`. Tasks are ordered so that each can be completed, reviewed, and merged independently. The recommended order follows the dependency chain: configuration fix first (unblocks other testing), then async HTTP (highest user-facing risk), then deduplication, then migration refactor, then minor fixes.
