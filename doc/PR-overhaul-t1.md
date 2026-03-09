# PR: Async HTTP overhaul (requests → aiohttp) + token sender config

**Branch:** `overhaul-t1` → `main`
**Commits:** 4 | **Files changed:** 7 | **+896 / -775**

---

## What this does

The bot is built on an async framework (interactions.py), but a big chunk of the HTTP calls were still using the synchronous `requests` library. Every time the bot hit the Steam API — checking for new games, scanning wishlists, fetching price data — it was blocking the entire event loop while waiting for a response. That's the kind of thing that makes a bot feel laggy or unresponsive during heavy operations like `!force_deals` or `!full_wishlist_scan`.

This PR replaces every `requests` call with `aiohttp`, which plays nicely with `async`/`await` and lets the bot keep doing other things while it waits on network I/O. It's a broad change across the core library and most of the plugins, but the behavior from a user's perspective should be identical — just faster and more stable.

The second piece is a small config addition for the token sender plugin.

---

## Changes by file

### `src/familybot/lib/steam_api_manager.py`

The centerpiece of the network layer. `SteamAPIManager` now:

- Uses `aiohttp.ClientSession` for all HTTP requests instead of `requests.get`
- Has a `SimpleResponse` wrapper class that keeps a familiar `.status_code`, `.text`, and `.json()` interface so callers don't need to be rewritten wholesale
- Handles exponential backoff on 429 rate-limit responses (up to 3 retries, with jitter to avoid thundering-herd problems)
- Can accept an existing `aiohttp.ClientSession` or spin up its own — useful for batching many requests under one session

### `src/familybot/lib/family_utils.py`

`format_message` was the main offender here — it fetched app details from the Steam Store API inside a synchronous call. It's now fully async, opening a single `aiohttp.ClientSession` for all the games in the wishlist batch rather than making a new connection for each one.

### `src/familybot/lib/plugin_admin_actions.py`

The biggest file in the diff. The whole admin action layer — new game checks, wishlist collection, deal scanning — now runs through `aiohttp`. A few structural improvements came along for the ride:

- Added `_handle_api_response()`, a shared helper that processes response status, parses JSON, and logs errors in one place instead of scattering that logic across every caller
- `check_new_game_action` and `force_new_game_action` now share a single `aiohttp.ClientSession` across their fetches instead of opening a new one per request
- Same pattern for `check_wishlist_action` / `force_wishlist_action` and `force_deals_action`

### `src/familybot/plugins/common_game.py`

`!common_games` was fetching owned game lists with `requests`. Now uses `aiohttp.ClientSession` with a proper async context manager. Error handling is unchanged — still catches `ClientError`, JSON decode failures, and missing keys separately.

### `src/familybot/plugins/free_games.py`

All the Bluesky feed fetching and Reddit post resolution already had reasonable async structure, but was mixing `requests` calls in a few spots. Now consistently uses `aiohttp` throughout, including the short-URL resolution path for `redd.it` links. The `SteamAPIManager` integration (for rich Steam game embeds) now goes through the async request path as well.

### `src/familybot/plugins/steam_admin.py`

The `!force_deals` and `!force_deals_unlimited` commands were doing synchronous store API calls inside an async loop. They now use `aiohttp.ClientSession` for game detail fetches, and `!force_deals` specifically uses `make_request_with_retry()` from `SteamAPIManager` to get the retry/backoff behavior for free.

### `config-template.yml`

Added the `token_sender` configuration block:

```yaml
token_sender:
    token_save_path: "tokens"
    browser_profile_path: "FamilyBotBrowserProfile"
    update_buffer_hours: 24
```

These settings were previously baked into the plugin itself. Surfacing them in the config template makes the token refresh behavior adjustable without touching code.

---

## Why this matters

Using `requests` in an async bot isn't just a style problem — it actually stalls the event loop. During a `!full_wishlist_scan` that checks hundreds of games, every synchronous HTTP call held up everything else the bot might need to do: respond to commands, process Discord events, run scheduled tasks. The aiohttp migration fixes that at the root.

The retry logic in `SteamAPIManager` is also new. Previously a 429 from Steam would surface as an error. Now it backs off and retries automatically, which matters for the heavier scan commands.

---

## Testing notes

- `!force` — triggers a new game check, exercises `plugin_admin_actions.force_new_game_action`
- `!force_wishlist` — exercises `plugin_admin_actions.force_wishlist_action`
- `!force_deals` — hits `steam_admin.force_deals_command`, uses `make_request_with_retry`
- `!force_deals_unlimited` — same, no game limit
- `!full_wishlist_scan` — the heaviest path; rate limiting + progress reporting + aiohttp session
- `!force_free` — checks Bluesky feed via async fetch
- `!common_games @user` — fetches owned games via aiohttp

No schema changes. No new dependencies beyond `aiohttp`, which was already in the project.
