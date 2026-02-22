# TASK-08 — Remove duplicated CLI argument parsing in `FamilyBot.py`

**Priority:** 🟠 High  
**Effort:** S (1 hr)  
**PRD reference:** §6.3  
**Depends on:** —

---

## Background

The `if __name__ == "__main__"` block and the `main()` entry-point function in `FamilyBot.py` define and handle identical argument parsers. Any change to CLI arguments currently requires editing both blocks. They have already drifted slightly in their help strings, meaning a user gets different help text depending on how they invoke the bot.

## Acceptance criteria

- [ ] A single private function (e.g. `_parse_and_dispatch()`) defines all arguments and handles all dispatch logic including `sys.exit()` calls.
- [ ] Both `if __name__ == "__main__"` and `main()` call that one function with no duplicated logic between them.
- [ ] No argument definitions, `add_argument` calls, or `sys.exit()` calls appear outside `_parse_and_dispatch`.
- [ ] The help text shown by `--help` is identical regardless of how the bot is invoked.
- [ ] `ruff check` passes on the modified file.

## Implementation notes

Target structure:

```python
def _parse_and_dispatch() -> None:
    parser = argparse.ArgumentParser(
        description="FamilyBot - Discord bot for Steam family management"
    )
    parser.add_argument("--purge-cache", ...)
    # ... all other arguments defined once ...
    args = parser.parse_args()

    if args.purge_cache:
        purge_game_cache()
        sys.exit(0)
    # ... all dispatch logic ...

    logger.info("Starting FamilyBot client...")
    try:
        asyncio.run(run_application())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down gracefully...")
    except Exception as e:
        logger.error("Unexpected error during startup: %s", e, exc_info=True)
        sys.exit(1)


def main() -> None:
    _parse_and_dispatch()


if __name__ == "__main__":
    _parse_and_dispatch()
```
