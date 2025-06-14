# In src/familybot/lib/utils.py

import requests
import json
import logging
import time
from typing import Optional
from familybot.config import ITAD_API_KEY # Import ITAD_API_KEY from config
from familybot.lib.database import get_cached_itad_price, cache_itad_price

# Setup logging for this specific module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_lowest_price(steam_app_id: int) -> str:
    """Fetches the lowest historical price for a given Steam App ID from IsThereAnyDeal with caching."""
    if not ITAD_API_KEY or ITAD_API_KEY == "YOUR_ITAD_API_KEY_HERE":
        logger.error("ITAD_API_KEY is missing or a placeholder. Cannot fetch lowest price.")
        return "N/A"

    # Try to get cached price first
    cached_price = get_cached_itad_price(str(steam_app_id))
    if cached_price:
        logger.debug(f"Using cached ITAD price for {steam_app_id}: {cached_price['lowest_price_formatted'] or cached_price['lowest_price']}")
        return cached_price['lowest_price_formatted'] or cached_price['lowest_price'] or "N/A"

    # If not cached, fetch from ITAD API
    try:
        logger.info(f"Fetching ITAD price from API for Steam App ID: {steam_app_id}")
        url_lookup = f"https://api.isthereanydeal.com/games/lookup/v1?key={ITAD_API_KEY}&appid={steam_app_id}"
        lookup_response = requests.get(url_lookup, timeout=5)
        lookup_response.raise_for_status()
        answer_lookup = json.loads(lookup_response.text)

        game_id = answer_lookup.get("game", {}).get("id")
        if not game_id:
            logger.warning(f"No ITAD game_id found for Steam App ID {steam_app_id}. Response: {answer_lookup}")
            return "N/A"

        url_storelow = f"https://api.isthereanydeal.com/games/storelow/v2?key={ITAD_API_KEY}&country=US&shops=61"
        data = [game_id]
        storelow_response = requests.post(url_storelow, json=data, timeout=5)
        storelow_response.raise_for_status()
        answer_storelow = json.loads(storelow_response.text)

        if answer_storelow and answer_storelow[0].get("lows") and answer_storelow[0]["lows"]:
            price_amount = answer_storelow[0]["lows"][0]["price"]["amount"]
            shop_name = answer_storelow[0]["lows"][0].get("shop", {}).get("name", "Unknown Store")
            
            # Cache the price data for 6 hours
            cache_itad_price(str(steam_app_id), {
                'lowest_price': str(price_amount),
                'lowest_price_formatted': f"${price_amount}",
                'shop_name': shop_name
            }, cache_hours=6)
            
            logger.debug(f"Cached ITAD price for {steam_app_id}: ${price_amount} from {shop_name}")
            return str(price_amount)
        else:
            logger.info(f"No historical lowest price found for Steam App ID {steam_app_id}.")
            return "N/A"

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching ITAD data for {steam_app_id}: {e}")
        return "N/A"
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for ITAD data {steam_app_id}: {e}. Raw: {lookup_response.text[:200] if 'lookup_response' in locals() else ''} {storelow_response.text[:200] if 'storelow_response' in locals() else ''}")
        return "N/A"
    except KeyError as e:
        logger.error(f"Missing key in ITAD response for {steam_app_id}: {e}. Response: {answer_lookup or answer_storelow}")
        return "N/A"
    except Exception as e:
        logger.critical(f"An unexpected error occurred in get_lowest_price for {steam_app_id}: {e}", exc_info=True)
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
    
    def __init__(self, total_items: int, progress_interval: int = DEFAULT_PROGRESS_INTERVAL) -> None:
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
        return current_percent // self.progress_interval > self.last_reported_percent // self.progress_interval
    
    def get_progress_message(self, processed_count: int, context_info: str = "") -> str:
        """Generate formatted progress message with time estimation."""
        if self.total_items == 0:
            return "No items to process"
            
        # Calculate once and reuse
        progress_ratio = processed_count / self.total_items
        current_percent = min(100, int(progress_ratio * 100))
        elapsed_time = time.time() - self.start_time
        
        # Build base message
        progress_msg = f"📊 **Progress: {current_percent}%** ({processed_count}/{self.total_items}"
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
