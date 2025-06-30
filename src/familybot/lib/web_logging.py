import asyncio
import logging
from logging import LogRecord


class WebSocketQueueHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self.queue = asyncio.Queue()

    def emit(self, record: LogRecord) -> None:
        try:
            self.queue.put_nowait(self.format(record))
        except asyncio.QueueFull:
            pass  # Or handle the full queue case
