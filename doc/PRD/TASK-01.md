# TASK-01 — Fix startup crash: add missing `token_sender` keys to config template

**Priority:** 🔴 Critical
**Effort:** XS (< 30 min)
**PRD reference:** §6.1
**Depends on:** —

---

## Background

`config.py` reads three `token_sender` keys at import time. They are absent from `config-template.yml`, so any user who follows the standard setup flow gets an unhandled `KeyError` before the bot starts.

## Acceptance criteria

- [x] `config-template.yml` includes a `token_sender` section with `token_save_path`, `browser_profile_path`, and `update_buffer_hours`, each with a sensible default value and an explanatory comment.
- [x] `config.py` is unchanged — it should continue to read these keys as-is.
- [x] Starting the bot with a config file generated from the updated template produces no `KeyError`.

## Implementation notes

Add the following to `config-template.yml`:

```yaml
token_sender:
  token_save_path: "tokens"                        # Directory where Steam tokens are saved
  browser_profile_path: "FamilyBotBrowserProfile"  # Browser session for token extraction
  update_buffer_hours: 24                           # Hours before token expiry to trigger a refresh
```
