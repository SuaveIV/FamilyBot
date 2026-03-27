"""API utility functions for Steam and other external services."""

import json
import aiohttp

from familybot.lib.logging_config import get_logger

logger = get_logger("api_utils")


async def handle_api_response(
    api_name: str, response: aiohttp.ClientResponse
) -> dict | None:
    """Process API responses, handle errors, and return JSON data.

    Args:
        api_name: Name of the API for logging purposes
        response: The aiohttp response object to process

    Returns:
        Parsed JSON dict on success, None on failure
    """
    try:
        response.raise_for_status()
        body = await response.text()
    except aiohttp.ClientResponseError as e:
        logger.error(f"Request error for {api_name}: {e}. URL: {e.request_info.url}")
        return None
    except aiohttp.ClientError as e:
        logger.error(f"Client connection error for {api_name}: {e}")
        return None
    except Exception as e:
        logger.critical(
            f"An unexpected error occurred processing {api_name} response: {e}",
            exc_info=True,
        )
        return None

    try:
        json_data = json.loads(body)
        return json_data
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for {api_name}: {e}. Raw: {body[:200]}")
        return None
