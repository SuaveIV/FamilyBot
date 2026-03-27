import asyncio
import aiohttp
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
from familybot.lib.logging_config import get_logger
from familybot.lib.types import FamilyBotClient
from familybot.lib.utils import get_lowest_price
from familybot.lib.steam_api_manager import SteamAPIManager

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
    Returns a dict with deal info if found, else None.
    """
    try:
        game_data = await fetch_game_details(app_id, steam_api_manager, session=session)
        if not game_data:
            return None

        # Check family sharing if required
        if require_family_shared and not game_data.get("is_family_shared", False):
            return None

        game_name = game_data.get("name", f"Unknown Game ({app_id})")
        # Handle fresh API data and cached data (normalized)
        price_overview = game_data.get("price_overview")

        if not price_overview:
            return None

        # Check if game is on sale
        discount_percent = price_overview.get("discount_percent", 0)
        current_price = price_overview.get("final_formatted", "N/A")
        original_price = price_overview.get("initial_formatted", current_price)

        # Early exit if the discount doesn't meet minimum thresholds
        if discount_percent < min(low_discount_threshold, high_discount_threshold):
            return None

        # Get historical low price
        lowest_price_raw = await asyncio.to_thread(get_lowest_price, int(app_id))
        lowest_price = lowest_price_raw

        # Sanitize lowest_price to a numeric value for comparison
        lowest_price_num = None
        if lowest_price_raw != "N/A":
            try:
                # Strip currency symbols and commas
                clean_price = lowest_price_raw.replace("$", "").replace(",", "").strip()
                lowest_price_num = float(clean_price)
            except (ValueError, TypeError):
                logger.warning(
                    f"Could not parse lowest_price '{lowest_price_raw}' for AppID {app_id}"
                )

        # Determine if this is a good deal
        is_good_deal = False
        deal_reason = ""

        if discount_percent >= high_discount_threshold:
            is_good_deal = True
            deal_reason = f"🔥 **{discount_percent}% OFF**"
        elif (
            discount_percent >= low_discount_threshold and lowest_price_num is not None
        ):
            # Check if current price is close to historical low
            try:
                current_price_num = float(price_overview.get("final", 0)) / 100
                if current_price_num <= lowest_price_num * historical_low_buffer:
                    is_good_deal = True
                    if historical_low_buffer > 1.1:
                        deal_reason = (
                            f"💎 **Near Historical Low** ({discount_percent}% off)"
                        )
                    else:
                        deal_reason = f"💎 **Historical Low** ({discount_percent}% off)"
            except (ValueError, TypeError):
                pass

        if is_good_deal:
            return {
                "name": game_name,
                "app_id": app_id,
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": discount_percent,
                "lowest_price": lowest_price,
                "deal_reason": deal_reason,
            }

    except Exception as e:
        logger.warning(f"Error checking deals for game {app_id}: {e}")
        return None

    return None
