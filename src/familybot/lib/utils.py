# In src/familybot/lib/utils.py

import asyncio
import time

from familybot.lib.constants import (
    DEFAULT_PROGRESS_INTERVAL,
    MIN_ELAPSED_TIME_FOR_ESTIMATION,
    SECONDS_PER_MINUTE,
)
from familybot.lib.logging_config import get_logger

# Setup enhanced logging for this specific module
logger = get_logger(__name__)


def get_common_elements_in_lists(list_of_lists: list) -> list:
    """
    Finds elements common to ALL sublists in a list of lists.
    Args:
        list_of_lists: A list where each element is itself a list of items.
    Returns:
        A sorted list of elements that are present in every sublist.
    """
    if not list_of_lists:
        return []

    common_elements_set = set(list_of_lists[0])

    for i in range(1, len(list_of_lists)):
        common_elements_set = common_elements_set.intersection(set(list_of_lists[i]))
        if not common_elements_set:
            return []

    return sorted(list(common_elements_set))


class ProgressTracker:
    """
    Tracks progress and generates formatted progress messages with time estimation.

    Args:
        total_items: Total number of items to process
        progress_interval: Percentage interval for reporting (default: 10)
    """

    def __init__(
        self, total_items: int, progress_interval: int = DEFAULT_PROGRESS_INTERVAL
    ) -> None:
        if total_items < 0:
            raise ValueError("total_items must be non-negative")
        if not 1 <= progress_interval <= 100:
            raise ValueError("progress_interval must be between 1 and 100")

        self.total_items = total_items
        self.progress_interval = progress_interval
        self.start_time = time.time()
        self.last_reported_percent = 0

    def should_report_progress(self, processed_count: int) -> bool:
        """Check if progress should be reported based on interval."""
        if self.total_items == 0:
            return False

        current_percent = min(100, int(processed_count * 100 / self.total_items))
        return (
            current_percent // self.progress_interval
            > self.last_reported_percent // self.progress_interval
        )

    def get_progress_message(self, processed_count: int, context_info: str = "") -> str:
        """Generate formatted progress message with time estimation."""
        if self.total_items == 0:
            return "No items to process"

        # Calculate once and reuse
        progress_ratio = processed_count / self.total_items
        current_percent = min(100, int(progress_ratio * 100))
        elapsed_time = time.time() - self.start_time

        # Build base message
        progress_msg = (
            f"📊 **Progress: {current_percent}%** ({processed_count}/{self.total_items}"
        )
        if context_info:
            progress_msg += f" {context_info}"
        progress_msg += ")"

        # Add time estimation if we have meaningful progress
        if current_percent > 0 and elapsed_time > MIN_ELAPSED_TIME_FOR_ESTIMATION:
            time_msg = self._safe_time_calculation(elapsed_time, progress_ratio)
            progress_msg += time_msg

        self.last_reported_percent = current_percent
        return progress_msg

    def _safe_time_calculation(self, elapsed_time: float, progress_ratio: float) -> str:
        """Safely calculate time remaining with error handling."""
        try:
            if progress_ratio <= 0 or elapsed_time <= 0:
                return ""

            estimated_total = elapsed_time / progress_ratio
            remaining = max(0, estimated_total - elapsed_time)

            if remaining >= SECONDS_PER_MINUTE:
                return f" | ⏱️ ~{int(remaining / SECONDS_PER_MINUTE)} min remaining"
            elif remaining >= 1:
                return f" | ⏱️ ~{int(remaining)} sec remaining"
            else:
                return " | ⏱️ Almost done!"

        except (ZeroDivisionError, OverflowError, ValueError):
            logger.warning("Error calculating time estimation")
            return ""


class TokenBucket:
    """Token bucket rate limiter for controlling API request rates."""

    def __init__(self, rate: float, capacity: int | None = None):
        """
        Initialize token bucket.

        Args:
            rate: Tokens per second (e.g., 1/1.5 = 0.67 for one request every 1.5 seconds)
            capacity: Maximum tokens in bucket (defaults to rate * 10)
        """
        self.rate = rate
        self.capacity: int = (
            capacity if capacity is not None else max(1, int(rate * 10.0))
        )
        self.tokens: float = float(self.capacity)
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> None:
        """Acquire tokens from the bucket, waiting if necessary."""
        async with self._lock:
            now = time.time()
            # Add tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

            # If we don't have enough tokens, wait
            if self.tokens < tokens:
                wait_time = (tokens - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                # After sleep, we have consumed the tokens we waited for
                self.tokens = 0.0
                self.last_update = time.time()
            else:
                self.tokens -= tokens
                self.last_update = now
