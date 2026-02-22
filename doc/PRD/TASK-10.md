# TASK-10 — Refactor database migrations to a declarative system

**Priority:** 🟡 Medium  
**Effort:** M (2–3 hrs)  
**PRD reference:** §6.4  
**Depends on:** —

---

## Background

`init_db` in `database.py` contains ~100 lines of `PRAGMA table_info` checks followed by `ALTER TABLE` calls, manually listed per-column. `migrate_database_phase1` and `migrate_database_phase2` are additional standalone functions with the same pattern. This is hard to read and error-prone to extend.

## Acceptance criteria

- [ ] A `COLUMN_MIGRATIONS` list at the top of the migrations section defines every column addition as a tuple of `(table, column, sql_definition)`.
- [ ] A single `_run_column_migrations(cursor)` helper applies the list idempotently.
- [ ] All existing per-column `ALTER TABLE` logic inside `init_db` is replaced by a call to `_run_column_migrations`.
- [ ] `migrate_database_phase1` and `migrate_database_phase2` are folded into `COLUMN_MIGRATIONS` and their standalone functions removed.
- [ ] The `detected_at` backfill `UPDATE` statement (data migration, not schema migration) is preserved in `init_db` after the schema migration runs.
- [ ] A fresh database and an existing database both initialise correctly.
- [ ] `ruff check` passes on the modified file.

## Implementation notes

```python
COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("saved_games",        "detected_at",     "TEXT"),
    ("game_details_cache", "is_multiplayer",  "BOOLEAN DEFAULT 0"),
    ("game_details_cache", "is_coop",         "BOOLEAN DEFAULT 0"),
    ("game_details_cache", "is_family_shared","BOOLEAN DEFAULT 0"),
    ("game_details_cache", "price_source",    "TEXT DEFAULT 'store_api'"),
    ("itad_price_cache",   "permanent",       "BOOLEAN DEFAULT 1"),
    ("itad_price_cache",   "lookup_method",   "TEXT DEFAULT 'appid'"),
    ("itad_price_cache",   "steam_game_name", "TEXT"),
]

def _run_column_migrations(cursor: sqlite3.Cursor) -> None:
    for table, column, definition in COLUMN_MIGRATIONS:
        existing = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            logger.info("Migration applied: %s.%s", table, column)
```

Adding a new column in future is then a single line appended to `COLUMN_MIGRATIONS`.
