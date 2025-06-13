# In src/familybot/lib/utils.py

import requests
import json
import logging
from familybot.config import ITAD_API_KEY # Import ITAD_API_KEY from config

# Setup logging for this specific module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_lowest_price(steam_app_id: int) -> str:
    """Fetches the lowest historical price for a given Steam App ID from IsThereAnyDeal."""
    if not ITAD_API_KEY or ITAD_API_KEY == "YOUR_ITAD_API_KEY_HERE":
        logger.error("ITAD_API_KEY is missing or a placeholder. Cannot fetch lowest price.")
        return "N/A"

    try:
        url_lookup = f"https://api.isthereanydeal.com/games/lookup/v1?key={ITAD_API_KEY}&appid={steam_app_id}"
        lookup_response = requests.get(url_lookup, timeout=5)
        lookup_response.raise_for_status()
        answer_lookup = json.loads(lookup_response.text)

        game_id = answer_lookup.get("game", {}).get("id")
        if not game_id:
            logger.warning(f"No ITAD game_id found for Steam App ID {steam_app_id}. Response: {answer_lookup}")
            return "N/A"

        url_storelow = f"https://api.isthereanydeal.com/games/storelow/v2?key={ITAD_API_KEY}&country=FR&shops=61"
        data = [game_id]
        storelow_response = requests.post(url_storelow, json=data, timeout=5)
        storelow_response.raise_for_status()
        answer_storelow = json.loads(storelow_response.text)

        if answer_storelow and answer_storelow[0].get("lows") and answer_storelow[0]["lows"]:
            price_amount = answer_storelow[0]["lows"][0]["price"]["amount"]
            logger.debug(f"Lowest price for {steam_app_id}: {price_amount}€")
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