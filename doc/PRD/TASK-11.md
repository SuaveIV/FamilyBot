# TASK-11 — Fix `asyncio.Queue` instantiation in `web_logging.py`

**Priority:** 🟡 Medium  
**Effort:** XS (< 30 min)  
**PRD reference:** §6.5  
**Depends on:** —

---

## Background

`WebSocketQueueHandler.__init__` calls `asyncio.Queue()` directly. In Python 3.10+, creating an `asyncio.Queue` outside a running event loop raises a `DeprecationWarning` and in some contexts a `RuntimeError`. This handler is instantiated at module import time, before the bot's event loop is running.

## Acceptance criteria

- [ ] `asyncio.Queue()` is not called in `__init__`.
- [ ] The queue is created lazily on first use via a property.
- [ ] Existing code that reads `handler.queue` continues to work without changes at the call site.
- [ ] No deprecation warnings related to this class appear on startup.
- [ ] `ruff check` passes on the modified file.

## Implementation notes

```python
class WebSocketQueueHandler(logging.Handler):
    def __init__(self, level: int = logging.NOTSET) -> None:
        super().__init__(level)
        self._queue: asyncio.Queue | None = None

    @property
    def queue(self) -> asyncio.Queue:
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue
```

The queue is now created on first access, which happens inside the running event loop, not at import time.
