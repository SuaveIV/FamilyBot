import asyncio
import logging
from logging import LogRecord


class WebSocketQueueHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self._queue = None

    @property
    def queue(self) -> asyncio.Queue:
        """Lazy initialization of the queue to ensure it's created within an event loop."""
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    def emit(self, record: LogRecord) -> None:
        try:
            self.queue.put_nowait(self.format(record))
        except (asyncio.QueueFull, RuntimeError):
            # RuntimeError can occur if there is no running event loop
            pass
