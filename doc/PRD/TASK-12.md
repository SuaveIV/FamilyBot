# TASK-12 — Guard `_migrate_gamelist_to_db` with a module-level flag

**Priority:** 🟡 Medium  
**Effort:** XS (< 30 min)  
**PRD reference:** §6.5  
**Depends on:** —

---

## Background

`_migrate_gamelist_to_db` in `familly_game_manager.py` is called inside `get_saved_games()`, which runs on every scheduled game check. Each call performs an `os.path.exists` filesystem check for the legacy `gamelist.txt` file. After the first run the file never exists, but the check still happens on every invocation for the lifetime of the process.

## Acceptance criteria

- [ ] A module-level boolean flag (e.g. `_migration_checked`) is set to `True` after the first call to `_migrate_gamelist_to_db`.
- [ ] Subsequent calls to `get_saved_games()` skip the migration function entirely.
- [ ] The migration still executes correctly on the first call when `gamelist.txt` is present.
- [ ] `ruff check` passes on the modified file.

## Implementation notes

```python
_migration_checked: bool = False

def get_saved_games() -> list[...]:
    global _migration_checked
    if not _migration_checked:
        _migrate_gamelist_to_db()
        _migration_checked = True
    ...
```
