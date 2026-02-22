# TASK-04 — Fix async event loop blocking: `SteamAPIManager.make_request_with_retry`

**Priority:** 🔴 Critical  
**Effort:** S (1–2 hrs)  
**PRD reference:** §6.2  
**Depends on:** TASK-02

---

## Background

`SteamAPIManager.make_request_with_retry` in `steam_api_manager.py` is declared `async def` but uses synchronous `requests.get()` internally. All callers `await` it expecting non-blocking behaviour, but it blocks the event loop on every call.

## Acceptance criteria

- [ ] `make_request_with_retry` uses `aiohttp` internally and is genuinely non-blocking.
- [ ] The method signature and return type remain compatible with all existing callers.
- [ ] Exponential backoff and 429 retry logic are preserved.
- [ ] Any `aiohttp.ClientSession` created in this method is properly closed after use.
- [ ] `import requests` is removed from `steam_api_manager.py` if no longer needed.
- [ ] `ruff check` passes on the modified file.

## Implementation notes

The method should either accept a session as a parameter (preferred for connection reuse), or create and close one per call. A session parameter makes testing easier and avoids creating a new TCP connection on every call:

```python
async def make_request_with_retry(
    self,
    url: str,
    timeout: int = 10,
    session: aiohttp.ClientSession | None = None,
) -> aiohttp.ClientResponse | None:
    ...
```

Callers that already manage their own session can pass it in. Callers that don't can let the method create and close one internally.
