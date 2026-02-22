# TASK-13 — Rename `familly_game_manager.py` to `family_game_manager.py`

**Priority:** 🟢 Low  
**Effort:** XS (< 30 min)  
**PRD reference:** §6.5  
**Depends on:** TASK-12 (do both in one commit to avoid two separate renames)

---

## Background

The filename contains a double-l typo (`familly`). While harmless at runtime, it creates unnecessary confusion and is inconsistent with every other use of "family" in the codebase.

## Acceptance criteria

- [ ] File is renamed from `familly_game_manager.py` to `family_game_manager.py`.
- [ ] All `import` and `from ... import` statements referencing `familly_game_manager` are updated.
- [ ] `grep -r "familly_game_manager" .` returns no results after the change.
- [ ] Bot starts and `get_saved_games` / `set_saved_games` function correctly.

## Known import locations

Verify with `grep -rn familly_game_manager src/` before starting, then update each:

- `src/familybot/plugins/steam_admin.py`
- `src/familybot/lib/plugin_admin_actions.py`

## Implementation notes

```bash
git mv src/familybot/lib/familly_game_manager.py \
       src/familybot/lib/family_game_manager.py
```

Then update the import statements in the files above. Commit TASK-12 and TASK-13 together so the module is only touched once.
