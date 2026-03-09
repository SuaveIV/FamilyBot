# In src/familybot/lib/family_utils.py

import json
import logging
import asyncio

import aiohttp

from familybot.config import FAMILY_STEAM_ID  # Import FAMILY_USER_DICT here
from familybot.config import FAMILY_USER_DICT
from familybot.lib.token_manager import get_token  # <<< IMPORT get_token here
from familybot.lib.utils import get_lowest_price


# Setup logging for this specific module
logger = logging.getLogger(__name__)


def get_family_game_list_url() -> str:
    """Generates the URL for the Steamworks GetSharedLibraryApps API using webapi_token."""
    token = get_token()  # Retrieve the webapi_token
    if not token:
        logger.error(
            "webapi_token is empty or not available. Cannot fetch family game list."
        )
        # Consider raising an error to be caught by the calling function
        raise ValueError("webapi_token is missing or invalid.")

    # Use 'access_token' parameter with the webapi_token for this specific endpoint
    url_family_list = (
        f"https://api.steampowered.com/IFamilyGroupsService/GetSharedLibraryApps/v1/"
        f"?access_token={token}"  # <<< Changed back to access_token={token}
        f"&family_groupid={FAMILY_STEAM_ID}"
        f"&include_own=true"  # Changed to true to include games you own in the shared library list
        f"&include_free=false"
        f"&language=french"
        f"&format=json"
    )
    logger.debug(f"Generated family game list URL: {url_family_list}")
    return url_family_list


async def format_message(
    wishlist: list, *, short: bool = False, cached_data: dict | None = None
) -> str:
    """Formats a list of wishlist items into a Discord message."""
    message_parts = ["# 📝 Family Wishlist \n"]
    if not wishlist:
        return "# 📝 Family Wishlist \nNo common wishlist items found to display."

    new_cached_data = cached_data or {}
    async with aiohttp.ClientSession() as session:
        for item in wishlist:
            app_id = str(item[0])
            users_wanting = ", ".join(
                FAMILY_USER_DICT.get(user_steam_id, f"Unknown User({user_steam_id})")
                for user_steam_id in item[1]
            )

            message_parts.append(f"- {users_wanting} want ")

            # Use cached data if available
            if app_id in new_cached_data:
                game_info_data = new_cached_data[app_id]
            else:
                game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=fr"
                game_info_data = None
                try:
                    async with session.get(
                        game_url, timeout=aiohttp.ClientTimeout(total=10)
                    ) as game_info_response:
                        game_info_response.raise_for_status()
                        text_response = await game_info_response.text()
                        game_info_json = json.loads(text_response)

                    if game_info_json.get(app_id, {}).get("success"):
                        game_info_data = game_info_json[app_id]["data"]
                        new_cached_data[app_id] = game_info_data
                    else:
                        logger.warning(
                            f"App details success false for AppID {app_id} in format_message. Response: {game_info_json}"
                        )
                        message_parts.append(
                            f"**Unknown Game ({app_id})** (Details Unavailable) \n"
                        )
                        continue

                except aiohttp.ClientError as e:
                    logger.error(
                        f"Request error fetching app details for {app_id} in format_message: {e}"
                    )
                    message_parts.append(f"**Unknown Game ({app_id})** (API Error) \n")
                    continue
                except json.JSONDecodeError as e:
                    logger.error(
                        f"JSON decode error for app details {app_id} in format_message: {e}."
                    )
                    message_parts.append(f"**Unknown Game ({app_id})** (Data Error) \n")
                    continue
                except KeyError as e:
                    logger.error(
                        f"Missing key in app details for {app_id} in format_message: {e}. Response: {game_info_json}"
                    )
                    message_parts.append(
                        f"**Unknown Game ({app_id})** (Format Error) \n"
                    )
                    continue
                except Exception as e:
                    logger.critical(
                        f"Unexpected error fetching app details for {app_id} in format_message: {e}",
                        exc_info=True,
                    )
                    message_parts.append(
                        f"**Unknown Game ({app_id})** (Unexpected Error) \n"
                    )
                    continue

            game_name = game_info_data.get("name", f"Unknown Game ({app_id})")
            message_parts.append(
                f"[{game_name}](<https://store.steampowered.com/app/{app_id}>) \n"
            )

            price_overview = game_info_data.get("price_overview")
            if price_overview and price_overview.get("discount_percent") != 0:
                final_formatted = price_overview.get("final_formatted", "N/A")
                discount_percent = price_overview.get("discount_percent", 0)
                message_parts.append(
                    f"  **__The game is on sale at {final_formatted} (-{discount_percent}%)__** \n"
                )
                if not short:
                    final_price = price_overview.get("final")  # Price in cents
                    if final_price is not None and item[1]:
                        price_per_person = round(final_price / 100 / len(item[1]), 2)
                        message_parts.append(
                            f" which is {price_per_person}$ per person \n"
                        )
                    try:
                        lowest_price = await asyncio.to_thread(
                            get_lowest_price, int(app_id)
                        )
                        message_parts.append(
                            f"   The lowest price ever was {lowest_price}$ \n"
                        )
                    except Exception as e:
                        logger.warning(f"Could not get lowest price for {app_id}: {e}")
                        message_parts.append("   Lowest price info unavailable. \n")
            else:
                final_formatted = (
                    price_overview.get("final_formatted", "N/A")
                    if price_overview
                    else "N/A"
                )
                message_parts.append(f"  The game is at {final_formatted} \n")
                if not short:
                    final_price = (
                        price_overview.get("final") if price_overview else None
                    )
                    if final_price is not None and item[1]:
                        price_per_person = round(final_price / 100 / len(item[1]), 2)
                        message_parts.append(
                            f" which is {price_per_person}$ per person \n"
                        )
                    try:
                        lowest_price = await asyncio.to_thread(
                            get_lowest_price, int(app_id)
                        )
                        message_parts.append(
                            f"   The lowest price ever was {lowest_price}$ \n"
                        )
                    except Exception as e:
                        logger.warning(f"Could not get lowest price for {app_id}: {e}")
                        message_parts.append("   Lowest price info unavailable. \n")

    final_message = "".join(message_parts)

    if len(final_message) > 1900 and not short:
        logger.warning(
            f"Formatted message too long ({len(final_message)} chars). Retrying with short format."
        )
        return await format_message(wishlist, short=True, cached_data=new_cached_data)
    elif len(final_message) > 1900 and short:
        logger.warning("Shortened message still too long. Sending generic message.")
        return "# 📝 Family Wishlist \n Can't create a message or it will be too long"
    elif not final_message.strip().endswith("\n"):
        final_message += "\n"

    return final_message
