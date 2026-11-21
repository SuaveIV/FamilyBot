# `familybot_lib_cases.jsonl`

Recorded behavior of seven pure functions from `src/familybot/lib/`, captured with
[rust-anything](https://github.com/erkamyaman/rust-anything) during a Rust-port spike on
this branch. The Rust crate itself was removed; this corpus was kept because it is a
ready-made edge-case fixture that does not depend on Rust.

**1559 cases**, one JSON object per line: `{"fn": ..., "args": [...], "ok": ...}` or
`{"fn": ..., "args": [...], "error": ...}`. 189 of them record an exception the
original raises on purpose.

| Function | Source |
| --- | --- |
| `split_message` | `lib/discord_utils.py` |
| `truncate_message_list` | `lib/discord_utils.py` |
| `extract_steam_id` | `lib/free_game_sources.py` |
| `url_domain` | `lib/free_game_sources.py` |
| `sanitize_log_message` | `lib/logging_config.py` |
| `parse_price_string` | `lib/steam_helpers.py` |
| `get_common_elements_in_lists` | `lib/utils.py` |

The generated inputs deliberately cover the Python semantics that are easy to get wrong:
non-ASCII and emoji, `-0` and `NaN`, Unicode decimal digits, `str.rstrip()` also stripping
`U+001C`–`U+001F`, `urlparse().netloc` keeping trailing spaces, and `1 == 1.0 == True`
inside set operations.

**Use.** A regression corpus for these functions if they are ever refactored: parse each
line, call the current Python implementation, compare. It is not wired into any test runner
yet — the repository has no `tests/` package.

**Regenerating.** `rust-anything bridge . 'src/familybot/lib/'` then `rust-anything record`,
run with `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=src` so the recorder sees the project venv.
