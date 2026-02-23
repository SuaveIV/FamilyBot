# TASK-07 — Remove duplicated family member loading logic

**Priority:** 🟠 High  
**Effort:** S (1 hr)  
**PRD reference:** §6.3  
**Depends on:** —

---

## Background

`load_family_members_from_db` exists in three places:

| File                      | Function name                  | SteamID validation                          |
| ------------------------- | ------------------------------ | ------------------------------------------- |
| `database.py`             | `load_family_members_from_db`  | Via `steam.steamid.SteamID` class (correct) |
| `admin_commands.py`       | `load_family_members`          | Manual string length/prefix check (weaker)  |
| `plugin_admin_actions.py` | `_load_family_members_from_db` | Manual string length/prefix check (weaker)  |

The two non-canonical implementations will silently pass through invalid SteamIDs that the canonical version would reject. They have also drifted in their migration logic.

## Acceptance criteria

- [ ] `load_family_members` in `admin_commands.py` is deleted.
- [ ] `_load_family_members_from_db` in `plugin_admin_actions.py` is deleted.
- [ ] All callers in both files import and call `load_family_members_from_db` from `database.py`.
- [ ] No functional change to the `database.py` implementation.
- [ ] `ruff check` passes on all modified files.

## Implementation notes

Search for all call sites before deleting:

```bash
grep -rn "_load_family_members_from_db\|load_family_members" src/
```

The `database.py` version handles the one-time config migration internally via a module-level flag (`_family_members_migrated_this_run`), so callers do not need to manage migration themselves.
