#!/usr/bin/env python3
"""
Script to force an immediate update of the Steam webapi_token.
This script launches Camoufox, extracts the token, and saves it to the live tokens directory.
Useful for manual updates or cron jobs.
"""

import asyncio
import base64
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from camoufox.async_api import AsyncCamoufox
except ImportError:
    print("❌ Camoufox not available. Please install with: uv add camoufox")
    sys.exit(1)

# Import configuration
try:
    from familybot.config import BROWSER_PROFILE_PATH, PROJECT_ROOT, TOKEN_SAVE_PATH
except ImportError as e:
    print(f"❌ Could not import configuration: {e}")
    sys.exit(1)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def get_token_with_camoufox() -> str:
    """Extract Steam webapi_token using Camoufox."""
    logger.info("Starting token extraction...")

    profile_path = Path(PROJECT_ROOT) / BROWSER_PROFILE_PATH if BROWSER_PROFILE_PATH else None

    if not profile_path or not profile_path.exists():
        logger.error(f"Browser profile not found at {profile_path}")
        logger.error("Run 'uv run python scripts/setup_browser.py' first.")
        return ""

    logger.info("Launching headless browser...")
    async with AsyncCamoufox(
        persistent_context=True,
        user_data_dir=str(profile_path),
        headless=True,
    ) as context:
        page = await context.new_page()
        try:
            logger.info("Navigating to Steam...")
            await page.goto("https://store.steampowered.com/pointssummary/ajaxgetasyncconfig")
            await page.wait_for_load_state("networkidle")

            content = await page.content()

            # Click rawdata-tab if present
            try:
                rawdata_tab = page.locator("#rawdata-tab")
                if await rawdata_tab.count() > 0:
                    await rawdata_tab.click()
                    await page.wait_for_timeout(1000)
                    content = await page.content()
            except Exception as e:
                logger.debug(f"Could not click rawdata-tab: {e}")

            # Check for empty JSON response
            if '{"success":1,"data":[]}' in content or (
                len(content) < 200 and '"success":1' in content
            ):
                logger.error(
                    "Steam returned empty data response. Session expired. Run setup_browser.py."
                )
                return ""

            # Extract using regex
            token_pattern = r'"webapi_token"\s*:\s*"([^"]+)"'  # noqa: S105
            match = re.search(token_pattern, content)

            if not match:
                logger.error("Could not find webapi_token. Are you logged in?")
                return ""

            token = match.group(1)
            if not token:
                logger.error("Extracted token is empty")
                return ""

            logger.info(f"Token extracted successfully (starts with {token[:5]}...)")
            return token

        except Exception as e:
            logger.error(f"Error extracting token: {e}")
            return ""


def save_token(token: str) -> bool:
    """Save the token and its expiration to the live tokens directory."""
    token_save_dir = Path(PROJECT_ROOT) / TOKEN_SAVE_PATH

    try:
        token_save_dir.mkdir(parents=True, exist_ok=True)

        # 1. Save Token
        token_path = token_save_dir / "token"
        with token_path.open("w") as f:
            f.write(token)

        # 2. Decode & Save Expiry
        coded_string = token.split(".")[1]
        padded = coded_string.replace("-", "+").replace("_", "/")
        padded += "=" * (-len(padded) % 4)

        key_info = json.loads(base64.b64decode(padded).decode("utf-8"))
        exp_ts = key_info["exp"]

        exp_path = token_save_dir / "token_exp"
        with exp_path.open("w") as f:
            f.write(str(exp_ts))

        exp_dt = datetime.fromtimestamp(exp_ts, tz=UTC)
        logger.info(f"✅ Token updated! Expires at: {exp_dt}")
        return True

    except Exception as e:
        logger.error(f"Failed to save token: {e}")
        return False


async def main():
    token = await get_token_with_camoufox()
    if token and save_token(token):
        print("\n🎉 Token force update completed successfully.")
        sys.exit(0)

    print("\n❌ Token update failed.")
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
