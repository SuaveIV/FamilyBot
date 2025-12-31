# In src/familybot/lib/utils.py

import json
import time
from typing import List

import requests

from familybot.config import ITAD_API_KEY  # Import ITAD_API_KEY from config
from familybot.lib.database import cache_itad_price, get_cached_itad_price
from familybot.lib.logging_config import get_logger

# Setup enhanced logging for this specific module
logger = get_logger(__name__)


def get_lowest_price(steam_app_id: int) -> str:
    """Fetches the lowest historical price for a given Steam App ID from IsThereAnyDeal with permanent caching for historical prices."""
    if not ITAD_API_KEY or ITAD_API_KEY == "YOUR_ITAD_API_KEY_HERE":
        logger.error(
            "ITAD_API_KEY is missing or a placeholder. Cannot fetch lowest price."
        )
        return "N/A"

    # Try to get cached price first (permanent cache preferred)
    cached_price = get_cached_itad_price(str(steam_app_id))
    if cached_price:
        logger.debug(
            f"Using cached ITAD price for {steam_app_id}: {cached_price['lowest_price_formatted'] or cached_price['lowest_price']}"
        )
        return (
            cached_price["lowest_price_formatted"]
            or cached_price["lowest_price"]
            or "N/A"
        )

    # If not cached, fetch from ITAD API
    try:
        logger.info(f"Fetching ITAD price from API for Steam App ID: {steam_app_id}")
        url_lookup = f"https://api.isthereanydeal.com/games/lookup/v1?key={ITAD_API_KEY}&appid={steam_app_id}"
        lookup_response = requests.get(url_lookup, timeout=5)
        lookup_response.raise_for_status()
        answer_lookup = json.loads(lookup_response.text)

        game_id = answer_lookup.get("game", {}).get("id")
        if not game_id:
            logger.warning(
                f"No ITAD game_id found for Steam App ID {steam_app_id}. Response: {answer_lookup}"
            )
            return "N/A"

        # Use the prices/v3 endpoint for comprehensive price data including historical lows
        url_prices = f"https://api.isthereanydeal.com/games/prices/v3?key={ITAD_API_KEY}&country=US&shops=61"
        data = [game_id]
        prices_response = requests.post(url_prices, json=data, timeout=5)
        prices_response.raise_for_status()
        answer_prices = json.loads(prices_response.text)

        if (
            answer_prices
            and len(answer_prices) > 0
            and "historyLow" in answer_prices[0]
        ):
            history_low = answer_prices[0]["historyLow"].get("all", {})
            price_amount = history_low.get("amount")
            
            # v3 historyLow usually contains shop info
            shop_name = history_low.get("shop", {}).get("name", "Historical Low (All Stores)")

            if price_amount is not None:
                # Cache the price data permanently (historical lowest price)
                cache_itad_price(
                    str(steam_app_id),
                    {
                        "lowest_price": str(price_amount),
                        "lowest_price_formatted": f"${price_amount}",
                        "shop_name": shop_name,
                    },
                    permanent=True,
                )

                logger.debug(
                    f"Cached ITAD price for {steam_app_id} permanently: ${price_amount} from {shop_name}"
                )
                return str(price_amount)
        
        logger.info(
            f"No historical lowest price found for Steam App ID {steam_app_id}."
        )
        return "N/A"

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching ITAD data for {steam_app_id}: {e}")
        return "N/A"
    except json.JSONDecodeError as e:
        logger.error(
            f"JSON decode error for ITAD data {steam_app_id}: {e}."
        )
        return "N/A"
    except KeyError as e:
        logger.error(
            f"Missing key in ITAD response for {steam_app_id}: {e}."
        )
        return "N/A"
    except Exception as e:
        logger.critical(
            f"An unexpected error occurred in get_lowest_price for {steam_app_id}: {e}",
            exc_info=True,
        )
        return "N/A"


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

    # Constants
    DEFAULT_PROGRESS_INTERVAL = 10
    MIN_ELAPSED_TIME_FOR_ESTIMATION = 1  # Seconds
    SECONDS_PER_MINUTE = 60

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
        if current_percent > 0 and elapsed_time > self.MIN_ELAPSED_TIME_FOR_ESTIMATION:
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

            if remaining >= self.SECONDS_PER_MINUTE:
                return f" | ⏱️ ~{int(remaining / self.SECONDS_PER_MINUTE)} min remaining"
            elif remaining >= 1:
                return f" | ⏱️ ~{int(remaining)} sec remaining"
            else:
                return " | ⏱️ Almost done!"

        except (ZeroDivisionError, OverflowError, ValueError):
            logger.warning("Error calculating time estimation")
            return ""


def split_message(message: str, max_length: int = 1900) -> List[str]:
    """
    Split a message into multiple parts that fit within Discord's character limit.

    Args:
        message: The message to split
        max_length: Maximum length per message part (default 1900 to stay well under 2000 limit)

    Returns:
        List of message parts
    """
    if len(message) <= max_length:
        return [message]

    parts = []
    current_part = ""

    # Split by lines first to preserve formatting
    lines = message.split("\n")

    for line in lines:
        # If a single line is too long, we need to split it
        if len(line) > max_length:
            # If we have content in current_part, save it first
            if current_part:
                parts.append(current_part.rstrip())
                current_part = ""

            # Split the long line by words
            words = line.split(" ")
            for word in words:
                # If adding this word would exceed limit, start new part
                if len(current_part) + len(word) + 1 > max_length:
                    if current_part:
                        parts.append(current_part.rstrip())
                        current_part = word + " "
                    else:
                        # Single word is too long, truncate it
                        parts.append(word[: max_length - 3] + "...")
                        current_part = ""
                else:
                    current_part += word + " "
        else:
            # Check if adding this line would exceed the limit
            if len(current_part) + len(line) + 1 > max_length:
                # Save current part and start new one
                if current_part:
                    parts.append(current_part.rstrip())
                current_part = line + "\n"
            else:
                current_part += line + "\n"

    # Add any remaining content
    if current_part:
        parts.append(current_part.rstrip())

    return parts


def truncate_message_list(
    items: List[str],
    header: str = "",
    footer_template: str = "\n... and {count} more items!",
    max_length: int = 1900,
) -> str:
    """
    Truncates a list of items to fit within Discord's message limit.

    Args:
        items: List of strings to include in the message
        header: Optional header text to prepend
        footer_template: Template for footer when truncation occurs. Use {count} for remaining items count.
        max_length: Maximum message length (defaults to Discord's limit)

    Returns:
        Formatted message string that fits within the character limit
    """
    if not items:
        return header

    # Build full content first
    full_content = header + "\n".join(items)

    # If it fits, return as-is
    if len(full_content) <= max_length:
        return full_content

    # Calculate available space for items
    sample_footer = footer_template.format(count=999)  # Use max digits for calculation
    available_space = max_length - len(header) - len(sample_footer)

    if available_space <= 0:
        logger.warning(
            f"Header and footer too long for message truncation. Header: {len(header)}, Footer: {len(sample_footer)}"
        )
        return header[:max_length]

    # Add items until we run out of space
    truncated_items = []
    current_length = 0

    for item in items:
        item_length = len(item) + 1  # +1 for newline
        if current_length + item_length > available_space:
            break
        truncated_items.append(item)
        current_length += item_length

    # Build final message
    if len(truncated_items) < len(items):
        remaining_count = len(items) - len(truncated_items)
        footer = footer_template.format(count=remaining_count)
        result = header + "\n".join(truncated_items) + footer
        logger.info(
            f"Message truncated: showing {len(truncated_items)} items, hiding {remaining_count} items"
        )
        return result
    else:
        return header + "\n".join(truncated_items)