"""IsThereAnyDeal (ITAD) API service for fetching historical low prices."""

import json

import requests

from familybot.config import ITAD_API_KEY, ITAD_CACHE_TTL
from familybot.lib.itad_price_repository import cache_itad_price, get_cached_itad_price
from familybot.lib.logging_config import get_logger

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
            cache_itad_price(
                str(steam_app_id),
                {
                    "lowest_price": "N/A",
                    "lowest_price_formatted": "N/A",
                    "shop_name": "N/A",
                },
                permanent=False,
                cache_hours=72,
            )
            return "N/A"

        # Use the prices/v3 endpoint for comprehensive price data including historical lows
        url_prices = f"https://api.isthereanydeal.com/games/prices/v3?key={ITAD_API_KEY}&country=US"
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
            shop_name = history_low.get("shop", {}).get(
                "name", "Historical Low (All Stores)"
            )

            if price_amount is not None:
                formatted_price = f"${price_amount}"
                # Cache the price data (historical lowest price) with 2-week TTL instead of permanently
                cache_itad_price(
                    str(steam_app_id),
                    {
                        "lowest_price": str(price_amount),
                        "lowest_price_formatted": formatted_price,
                        "shop_name": shop_name,
                    },
                    permanent=False,
                    cache_hours=ITAD_CACHE_TTL,
                )

                logger.debug(
                    f"Cached ITAD price for {steam_app_id} for {ITAD_CACHE_TTL} hours: {formatted_price} from {shop_name}"
                )
                return formatted_price

        logger.info(
            f"No historical lowest price found for Steam App ID {steam_app_id}."
        )
        # Cache failed lookups for 3 days to avoid hammering the API
        cache_itad_price(
            str(steam_app_id),
            {
                "lowest_price": "N/A",
                "lowest_price_formatted": "N/A",
                "shop_name": "N/A",
            },
            permanent=False,
            cache_hours=72,  # 3 days
        )
        return "N/A"

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching ITAD data for {steam_app_id}: {e}")
        return "N/A"
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for ITAD data {steam_app_id}: {e}.")
        return "N/A"
    except KeyError as e:
        logger.error(f"Missing key in ITAD response for {steam_app_id}: {e}.")
        return "N/A"
    except Exception as e:
        logger.critical(
            f"An unexpected error occurred in get_lowest_price for {steam_app_id}: {e}",
            exc_info=True,
        )
        return "N/A"


def prefetch_itad_prices(steam_app_ids: list[str]) -> None:
    """Batch fetches historical low prices for multiple Steam App IDs and caches them."""
    if not ITAD_API_KEY or ITAD_API_KEY == "YOUR_ITAD_API_KEY_HERE":
        return

    # Filter out already cached IDs
    uncached_app_ids = []
    for app_id in steam_app_ids:
        if not get_cached_itad_price(str(app_id)):
            uncached_app_ids.append(str(app_id))

    if not uncached_app_ids:
        return

    # Batch into chunks of 100 to avoid overly large requests
    chunk_size = 100
    for i in range(0, len(uncached_app_ids), chunk_size):
        chunk_app_ids = uncached_app_ids[i : i + chunk_size]
        logger.info(f"Prefetching ITAD prices for {len(chunk_app_ids)} App IDs...")

        uuid_to_appid = {}
        # 1. Resolve Steam App IDs to ITAD UUIDs
        try:
            url_lookup = f"https://api.isthereanydeal.com/lookup/id/shop/61/v1?key={ITAD_API_KEY}"
            shop_queries = [f"app/{app_id}" for app_id in chunk_app_ids]
            lookup_response = requests.post(url_lookup, json=shop_queries, timeout=10)
            lookup_response.raise_for_status()
            answer_lookup = json.loads(lookup_response.text)

            for shop_query, uuid in answer_lookup.items():
                app_id = shop_query.replace("app/", "")
                if uuid:
                    uuid_to_appid[uuid] = app_id
                else:
                    # Cache failed lookups immediately for 3 days
                    cache_itad_price(
                        app_id,
                        {
                            "lowest_price": "N/A",
                            "lowest_price_formatted": "N/A",
                            "shop_name": "N/A",
                        },
                        permanent=False,
                        cache_hours=72,
                    )
        except Exception as e:
            logger.error(f"Error during ITAD lookup phase for batch: {e}")
            for app_id in chunk_app_ids:
                cache_itad_price(
                    app_id,
                    {
                        "lowest_price": "N/A",
                        "lowest_price_formatted": "N/A",
                        "shop_name": "N/A",
                    },
                    permanent=False,
                    cache_hours=72,
                )
            continue

        if not uuid_to_appid:
            continue

        # 2. Fetch prices for resolved UUIDs
        fetched_uuids = set()
        try:
            url_prices = f"https://api.isthereanydeal.com/games/prices/v3?key={ITAD_API_KEY}&country=US"
            uuids_to_fetch = list(uuid_to_appid.keys())
            prices_response = requests.post(url_prices, json=uuids_to_fetch, timeout=10)
            prices_response.raise_for_status()
            answer_prices = json.loads(prices_response.text)

            # Map the responses back to App IDs and cache
            for price_data in answer_prices:
                uuid = price_data.get("id")
                if not uuid or uuid not in uuid_to_appid:
                    continue
                fetched_uuids.add(uuid)
                app_id = uuid_to_appid[uuid]

                if "historyLow" in price_data and price_data["historyLow"]:
                    history_low = price_data["historyLow"].get("all", {})
                    price_amount = history_low.get("amount")
                    shop_name = history_low.get("shop", {}).get(
                        "name", "Historical Low (All Stores)"
                    )

                    if price_amount is not None:
                        formatted_price = f"${price_amount}"
                        cache_itad_price(
                            app_id,
                            {
                                "lowest_price": str(price_amount),
                                "lowest_price_formatted": formatted_price,
                                "shop_name": shop_name,
                            },
                            permanent=False,
                            cache_hours=ITAD_CACHE_TTL,
                        )
                        continue

                # If no history low found, cache as N/A
                cache_itad_price(
                    app_id,
                    {
                        "lowest_price": "N/A",
                        "lowest_price_formatted": "N/A",
                        "shop_name": "N/A",
                    },
                    permanent=False,
                    cache_hours=72,
                )
        except Exception as e:
            logger.error(f"Error during ITAD prices phase for batch: {e}")

        # Mark any UUIDs that didn't return price data as N/A
        for uuid, app_id in uuid_to_appid.items():
            if uuid not in fetched_uuids:
                cache_itad_price(
                    app_id,
                    {
                        "lowest_price": "N/A",
                        "lowest_price_formatted": "N/A",
                        "shop_name": "N/A",
                    },
                    permanent=False,
                    cache_hours=72,
                )
