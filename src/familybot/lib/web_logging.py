import logging
import queue
from logging import LogRecord

class WebSocketQueueHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self.queue = queue.Queue()

    def emit(self, record: LogRecord) -> None:
        self.queue.put(self.format(record))
