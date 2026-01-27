#!/usr/bin/env python3
"""
Script to force an immediate update of the Steam webapi_token.
This script launches Playwright, extracts the token, and saves it to the live tokens directory.
Useful for manual updates or cron jobs.
"""

import asyncio
import base64
import json
import logging
import re
import os
import sys
from datetime import datetime
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("❌ Playwright not available. Please install with: uv add playwright")
    sys.exit(1)

# Import configuration
try:
    from familybot.config import BROWSER_PROFILE_PATH, PROJECT_ROOT, TOKEN_SAVE_PATH
except ImportError as e:
    print(f"❌ Could not import configuration: {e}")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def get_token_with_playwright() -> str:
    """Extract Steam webapi_token using Playwright with optimized settings."""
    logger.info("Starting token extraction...")

    profile_path = (
        os.path.join(PROJECT_ROOT, BROWSER_PROFILE_PATH)
        if BROWSER_PROFILE_PATH
        else None
    )

    if not profile_path or not os.path.exists(profile_path):
        logger.error(f"Browser profile not found at {profile_path}")
        logger.error("Run 'uv run python scripts/setup_browser.py' first.")
        return ""

    # Load storage state if available
    storage_state_path = os.path.join(profile_path, "storage_state.json")
    storage_state = None
    if os.path.exists(storage_state_path):
        try:
            with open(storage_state_path, "r") as f:
                storage_state = json.load(f)
            logger.info("Loaded storage state for session persistence")
        except Exception as e:
            logger.warning(f"Could not load storage state: {e}")

    async with async_playwright() as p:
        # Launch with optimized arguments (same as plugin)
        logger.info("Launching headless browser...")
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-gpu",
                "--blink-settings=imagesEnabled=false",
            ],
        )

        # Apply cookies if available
        if storage_state:
            try:
                await browser.add_cookies(storage_state.get("cookies", []))
                logger.info("Applied cookies from storage state")
            except Exception as e:
                logger.warning(f"Could not apply storage state cookies: {e}")

        page = await browser.new_page()

        # Block unnecessary resources
        await page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ["image", "stylesheet", "font", "media"]
            else route.continue_(),
        )

        try:
            # Navigate
            logger.info("Navigating to Steam...")
            await page.goto(
                "https://store.steampowered.com/pointssummary/ajaxgetasyncconfig"
            )
            await page.wait_for_load_state("networkidle")

            content = await page.content()

            # Click rawdata-tab if present
            try:
                rawdata_tab = page.locator("#rawdata-tab")
                if await rawdata_tab.count() > 0:
                    await rawdata_tab.click()
                    await page.wait_for_timeout(1000)
                    content = await page.content()
            except Exception:
                pass

            # Check for empty JSON response
            if '{"success":1,"data":[]}' in content or (
                len(content) < 200 and '"success":1' in content
            ):
                logger.error(
                    "Steam returned empty data response. Session expired. Run setup_browser.py."
                )
                return ""

            # Extract using regex
            token_pattern = r'"webapi_token"\s*:\s*"([^"]+)"'
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
        finally:
            await browser.close()


def save_token(token: str) -> bool:
    """Save the token and its expiration to the live tokens directory."""
    token_save_dir = os.path.join(PROJECT_ROOT, TOKEN_SAVE_PATH)

    try:
        os.makedirs(token_save_dir, exist_ok=True)

        # 1. Save Token
        token_path = os.path.join(token_save_dir, "token")
        with open(token_path, "w") as f:
            f.write(token)

        # 2. Decode & Save Expiry
        coded_string = token.split(".")[1]
        padded = coded_string.replace("-", "+").replace("_", "/")
        padded += "=" * (-len(padded) % 4)

        key_info = json.loads(base64.b64decode(padded).decode("utf-8"))
        exp_ts = key_info["exp"]

        exp_path = os.path.join(token_save_dir, "token_exp")
        with open(exp_path, "w") as f:
            f.write(str(exp_ts))

        exp_dt = datetime.fromtimestamp(exp_ts)
        logger.info(f"✅ Token updated! Expires at: {exp_dt}")
        return True

    except Exception as e:
        logger.error(f"Failed to save token: {e}")
        return False


async def main():
    token = await get_token_with_playwright()
    if token:
        if save_token(token):
            print("\n🎉 Token force update completed successfully.")
            sys.exit(0)

    print("\n❌ Token update failed.")
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
