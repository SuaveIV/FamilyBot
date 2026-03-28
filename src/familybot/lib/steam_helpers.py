import asyncio
import aiohttp
import re
from datetime import datetime

from familybot.config import ADMIN_DISCORD_ID
from familybot.lib.constants import (
    HIGH_DISCOUNT_THRESHOLD,
    HISTORICAL_LOW_BUFFER,
    LOW_DISCOUNT_THRESHOLD,
)
from familybot.lib.game_details_repository import (
    cache_game_details,
    get_cached_game_details,
)
from familybot.lib.itad_price_repository import get_cached_itad_price
from familybot.lib.logging_config import get_logger
from familybot.lib.types import FamilyBotClient
from familybot.lib.steam_api_manager import SteamAPIManager


def parse_price_string(price: str) -> float | None:
    """Parse a price string (e.g., "$1,234.56", "€9,99") to a float. Returns None on error or N/A."""
    if not price or price == "N/A":
        return None

    # Remove currency symbols and grouping, handle both "." and "," as decimal/grouping
    price_clean = re.sub(r"[^\d.,]", "", price)
    # If both . and , exist, assume . is decimal, , is grouping
    if "." in price_clean and "," in price_clean:
        if price_clean.rfind(".") > price_clean.rfind(","):
            price_clean = price_clean.replace(",", "")
        else:
            price_clean = price_clean.replace(".", "").replace(",", ".")
    # If only , exists, treat as decimal if at end (e.g., "9,99")
    elif "," in price_clean and "." not in price_clean:
        if price_clean.count(",") == 1 and len(price_clean.split(",")[-1]) <= 2:
            price_clean = price_clean.replace(",", ".")
        else:
            price_clean = price_clean.replace(",", "")
    try:
        return float(price_clean)
    except (ValueError, TypeError):
        return None


logger = get_logger(__name__)


async def send_admin_dm(bot: FamilyBotClient, message: str) -> None:
    """Helper to send error/warning messages to the bot admin via DM."""
    try:
        admin_user = await bot.fetch_user(ADMIN_DISCORD_ID)
        if admin_user is not None:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await admin_user.send(f"Steam Family Plugin Error ({now_str}): {message}")
        else:
            logger.error(
                f"Admin user with ID {ADMIN_DISCORD_ID} not found or could not be fetched. Cannot send DM."
            )
    except Exception as e:
        logger.error(
            f"Failed to send DM to admin {ADMIN_DISCORD_ID} (after initial fetch attempt): {e}"
        )


async def fetch_game_details(
    app_id: str,
    steam_api_manager: SteamAPIManager,
    session: aiohttp.ClientSession | None = None,
) -> dict | None:
    """
    Fetch game details from cache or Steam Store API.
    Returns the 'data' dict for the game if found, else None.
    """
    try:
        # Get cached game details first
        cached_game = await asyncio.to_thread(get_cached_game_details, app_id)
        if cached_game:
            return cached_game

        # If not cached, fetch from API with enhanced retry logic
        await steam_api_manager.rate_limit_steam_store_api()
        game_url = (
            f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en"
        )
        app_info_response = await steam_api_manager.make_request_with_retry(
            game_url, session=session
        )

        if app_info_response is None:
            return None

        game_info_json = app_info_response.json()
        if not game_info_json:
            return None

        game_data = game_info_json.get(str(app_id), {}).get("data")
        if not game_data:
            return None

        # Cache the game details (use permanent=False so prices expire with GAME_DETAILS_CACHE_TTL)
        await asyncio.to_thread(cache_game_details, app_id, game_data, permanent=False)
        return game_data

    except Exception as e:
        logger.warning(f"Error fetching game details for {app_id}: {e}")
        return None


async def process_game_deal(
    app_id: str,
    steam_api_manager: SteamAPIManager,
    session: aiohttp.ClientSession | None = None,
    high_discount_threshold: int = HIGH_DISCOUNT_THRESHOLD,
    low_discount_threshold: int = LOW_DISCOUNT_THRESHOLD,
    historical_low_buffer: float = HISTORICAL_LOW_BUFFER,
    require_family_shared: bool = False,
) -> dict | None:
    """
    Process a game to check for deals.
    Prefers ITAD cached data when available, falls back to Steam API.
    Returns a dict with deal info if found, else None.
    """
    try:
        game_name = f"Unknown Game ({app_id})"
        discount_percent = 0
        current_price = "N/A"
        original_price = "N/A"
        lowest_price = "N/A"
        lowest_price_num = None
        price_source = "none"

        # Try ITAD cache first — it has current price, discount, and historical low
        itad_cache = await asyncio.to_thread(get_cached_itad_price, app_id)

        # Enforce family sharing requirement if needed
        # Note: We don't null out itad_cache here, so downstream code can still
        # read ITAD historical_low even when family sharing is not confirmed.
        # Instead we track the family_shared flag separately for the Steam fallback path.
        itad_family_shared = True
        if require_family_shared and itad_cache:
            is_family_shared = itad_cache.get("is_family_shared")
            if not bool(is_family_shared):
                # Flag is missing, False, or invalid — mark as not confirmed
                itad_family_shared = False

        if itad_cache and itad_cache.get("current_price"):
            # Check family sharing requirement before using ITAD data
            if require_family_shared and not itad_family_shared:
                return None

            game_name = itad_cache.get("steam_game_name") or game_name
            discount_percent = itad_cache.get("discount_percent", 0)
            current_price = itad_cache.get("current_price_formatted", "N/A")
            original_price = itad_cache.get("original_price", "N/A")
            lowest_price = itad_cache.get("lowest_price_formatted") or itad_cache.get(
                "lowest_price", "N/A"
            )
            price_source = "itad"

            # Parse lowest_price for numeric comparison
            lowest_price_num = parse_price_string(lowest_price)
        else:
            # Fallback: fetch from Steam Store API
            game_data = await fetch_game_details(
                app_id, steam_api_manager, session=session
            )
            if not game_data:
                return None

            # Check family sharing if required
            if require_family_shared and not game_data.get("is_family_shared", False):
                return None

            game_name = game_data.get("name", game_name)
            price_overview = game_data.get("price_overview")
            if not price_overview:
                return None

            discount_percent = price_overview.get("discount_percent", 0)
            current_price = price_overview.get("final_formatted", "N/A")
            original_price = price_overview.get("initial_formatted", current_price)
            price_source = "steam"

            # Get historical low from ITAD cache (even if no current price data)
            if itad_cache:
                lowest_price = itad_cache.get(
                    "lowest_price_formatted"
                ) or itad_cache.get("lowest_price", "N/A")
                lowest_price_num = parse_price_string(lowest_price)

        # Early exit if the discount doesn't meet minimum thresholds
        if discount_percent < min(low_discount_threshold, high_discount_threshold):
            return None

        # Fallback for game name if ITAD didn't provide it (e.g. bulk ITAD data)
        # We check both the local cache and Steam API via fetch_game_details
        if game_name.startswith("Unknown Game"):
            game_data = await fetch_game_details(
                app_id, steam_api_manager, session=session
            )
            if game_data and game_data.get("name"):
                game_name = game_data["name"]

        # Determine if this is a good deal
        is_good_deal = False
        deal_reason = ""

        if discount_percent >= high_discount_threshold:
            is_good_deal = True
            deal_reason = f"🔥 **{discount_percent}% OFF**"
        elif (
            discount_percent >= low_discount_threshold and lowest_price_num is not None
        ):
            current_price_num = parse_price_string(current_price)
            if (
                current_price_num is not None
                and current_price_num <= lowest_price_num * historical_low_buffer
            ):
                is_good_deal = True
                if historical_low_buffer > 1.1:
                    deal_reason = (
                        f"💎 **Near Historical Low** ({discount_percent}% off)"
                    )
                else:
                    deal_reason = f"💎 **Historical Low** ({discount_percent}% off)"

        if is_good_deal:
            return {
                "name": game_name,
                "app_id": app_id,
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": discount_percent,
                "lowest_price": lowest_price,
                "deal_reason": deal_reason,
                "price_source": price_source,
            }

    except Exception as e:
        logger.warning(f"Error checking deals for game {app_id}: {e}")
        return None

    return None
