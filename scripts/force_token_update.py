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

            # Extract
            start_marker = '"webapi_token":"' # Corrected escaping for the string literal
            end_marker = '"}' # Corrected escaping for the string literal
            
            start_idx = content.find(start_marker)
            if start_idx == -1:
                logger.error("Could not find webapi_token. Are you logged in?")
                return ""
                
            key_start = start_idx + len(start_marker)
            key_end = content.find(end_marker, key_start)
            
            if key_end == -1:
                logger.error("Could not find end of webapi_token")
                return ""
                
            token = content[key_start:key_end]
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
