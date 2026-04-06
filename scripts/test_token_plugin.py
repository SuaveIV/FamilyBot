#!/usr/bin/env python3
"""
Test script for the token_sender plugin.
This script tests the token extraction functionality without running the full bot.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from camoufox.async_api import AsyncCamoufox

    CAMOUFOX_AVAILABLE = True
except ImportError:
    CAMOUFOX_AVAILABLE = False
    print("❌ Camoufox not available. Please install with: uv add camoufox")
    sys.exit(1)

# Import configuration
try:
    from familybot.config import BROWSER_PROFILE_PATH, PROJECT_ROOT, TOKEN_SAVE_PATH
except ImportError as e:
    print(f"❌ Could not import configuration: {e}")
    print("Make sure you're running this from the FamilyBot root directory")
    sys.exit(1)

import base64
import binascii
import json
import re
import tempfile
import shutil
from datetime import datetime


class TokenTester:
    def __init__(self):
        self.actual_token_save_dir = os.path.join(PROJECT_ROOT, TOKEN_SAVE_PATH)
        self.browser_profile_path = (
            os.path.join(PROJECT_ROOT, BROWSER_PROFILE_PATH)
            if BROWSER_PROFILE_PATH
            else None
        )
        # Create a temporary directory for test token storage
        self.test_token_save_dir = tempfile.mkdtemp()
        print(
            f"Created temporary directory for test tokens: {self.test_token_save_dir}"
        )

    def __del__(self):
        # Clean up the temporary directory when the object is deleted
        if os.path.exists(self.test_token_save_dir):
            shutil.rmtree(self.test_token_save_dir)
            print(f"Cleaned up temporary directory: {self.test_token_save_dir}")

    async def test_browser_profile(self):
        """Test if the browser profile exists and is accessible."""
        print("🔍 Testing browser profile...")

        if not self.browser_profile_path:
            print("⚠️  No browser profile path configured")
            return False

        if not os.path.exists(self.browser_profile_path):
            print(f"❌ Browser profile not found at: {self.browser_profile_path}")
            print("   Run 'uv run python scripts/setup_browser.py' first")
            return False

        print(f"✅ Browser profile found at: {self.browser_profile_path}")
        return True

    async def test_token_extraction(self):
        """Test the token extraction process."""
        print("\n🔍 Testing token extraction...")

        if self.browser_profile_path:
            if not os.path.exists(self.browser_profile_path):
                print(f"❌ Saved browser profile missing at: {self.browser_profile_path}")
                print("   Please run test_browser_profile() or setup first.")
                sys.exit(1)
            print(f"   Using browser profile: {self.browser_profile_path}")
            camoufox_kwargs = {
                "persistent_context": True,
                "user_data_dir": self.browser_profile_path,
                "headless": True,
            }
        else:
            print("   Using default browser (no profile)")
            camoufox_kwargs = {
                "headless": True,
            }

        try:
            async with AsyncCamoufox(**camoufox_kwargs) as context:
                page = await context.new_page()

                # Navigate to Steam points summary page
                print("   Navigating to Steam API endpoint...")
                await page.goto(
                    "https://store.steampowered.com/pointssummary/ajaxgetasyncconfig"
                )
                await page.wait_for_load_state("networkidle")

                # Get page content
                content = await page.content()

                # Check for empty JSON response
                if '{"success":1,"data":[]}' in content or (
                    len(content) < 200 and '"success":1' in content
                ):
                    print("❌ CRITICAL: Steam returned empty data response.")
                    print("   This means your session is expired or invalid.")
                    print(
                        "   Run 'uv run python scripts/setup_browser.py' to refresh login."
                    )
                    return False

                # Try to click rawdata-tab if it exists
                try:
                    rawdata_tab = page.locator("#rawdata-tab")
                    if await rawdata_tab.count() > 0:
                        print("   Found rawdata-tab, clicking...")
                        await rawdata_tab.click()
                        await page.wait_for_timeout(1000)
                        content = await page.content()
                except Exception as e:
                    print(f"   No rawdata-tab found (this is normal): {e}")

                # Extract token from page content
                print("   Searching for webapi_token...")
                token_pattern = r'"webapi_token"\s*:\s*"([^"]+)"'
                match = re.search(token_pattern, content)

                if not match:
                    print("❌ Could not find 'webapi_token' in page source")
                    print("   This usually means you're not logged into Steam")
                    print("   Run 'uv run python scripts/setup_browser.py' to log in")
                    return False

                extracted_key = match.group(1)

                if not extracted_key:
                    print("❌ Extracted token is empty")
                    return False

                print(f"✅ Successfully extracted token: {extracted_key[:20]}...")
                return extracted_key

        except Exception as e:
            print(f"❌ Error during token extraction: {e}")
            return False

    def test_token_decoding(self, token):
        """Test token decoding and expiry extraction."""
        print("\n🔍 Testing token decoding...")

        try:
            coded_string = token.split(".")[1]
            padded_coded_string = coded_string.replace("-", "+").replace("_", "/")
            padded_coded_string += "=" * (-len(padded_coded_string) % 4)

            key_info = json.loads(base64.b64decode(padded_coded_string).decode("utf-8"))
            exp_timestamp = key_info["exp"]

            exp_time = datetime.fromtimestamp(exp_timestamp)
            now = datetime.now()
            time_remaining = exp_time - now

            print("✅ Token decoded successfully")
            print(f"   Expires at: {exp_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Time remaining: {str(time_remaining).split('.')[0]}")

            if time_remaining.total_seconds() < 0:
                print("⚠️  Token has already expired!")
            elif time_remaining.total_seconds() < 3600:
                print("⚠️  Token expires soon!")
            else:
                print("✅ Token is valid")

            return exp_timestamp

        except (IndexError, json.JSONDecodeError, binascii.Error) as e:
            print(f"❌ Error decoding token: {e}")
            return None

    def test_token_storage(self, token, exp_timestamp):
        """Test saving token to files."""
        print("\n🔍 Testing token storage...")

        try:
            token_file_path = os.path.join(self.test_token_save_dir, "token")
            with open(token_file_path, "w") as token_file:
                token_file.write(token)

            exp_file_path = os.path.join(self.test_token_save_dir, "token_exp")
            with open(exp_file_path, "w") as exp_time_file:
                exp_time_file.write(str(exp_timestamp))

            print(f"✅ Token saved to: {token_file_path}")
            print(f"✅ Expiry saved to: {exp_file_path}")

            # Verify files can be read back
            with open(token_file_path, "r") as f:
                saved_token = f.read().strip()
            with open(exp_file_path, "r") as f:
                saved_exp = f.read().strip()

            if saved_token == token and saved_exp == str(exp_timestamp):
                print("✅ Token files verified successfully")
                return True
            else:
                print("❌ Token file verification failed")
                return False

        except Exception as e:
            print(f"❌ Error saving token: {e}")
            return False

    async def run_full_test(self):
        """Run the complete test suite."""
        print("🧪 Starting Token Sender Plugin Test")
        print("=" * 50)

        # Test 1: Check browser profile
        profile_ok = await self.test_browser_profile()

        # Test 2: Extract token
        token = await self.test_token_extraction()
        if not token:
            print("\n❌ Token extraction failed. Cannot continue with remaining tests.")
            return False

        # Test 3: Decode token
        exp_timestamp = self.test_token_decoding(token)
        if not exp_timestamp:
            print("\n❌ Token decoding failed. Cannot continue with remaining tests.")
            return False

        # Test 4: Save token
        storage_ok = self.test_token_storage(token, exp_timestamp)

        # Optional: Compare with live token
        try:
            live_token_path = os.path.join(self.actual_token_save_dir, "token")
            if os.path.exists(live_token_path):
                with open(live_token_path, "r") as f:
                    live_token = f.read().strip()

                print("\n🔍 Comparing with live bot token...")
                if live_token == token:
                    print("✅ Live token matches the newly fetched token.")
                else:
                    print("⚠️  Live token differs from the newly fetched token.")
                    print(
                        "   (This is normal if the live token is older but still valid,"
                    )
                    print("    or if the live token has expired and needs a refresh.)")
            else:
                print("\nℹ️  No live token found to compare with.")
        except Exception as e:
            print(f"\n⚠️  Could not compare with live token: {e}")

        print("\n" + "=" * 50)
        if profile_ok and token and exp_timestamp and storage_ok:
            print("🎉 All tests passed! Token sender plugin is working correctly.")
            print("\nNext steps:")
            print("1. Start the FamilyBot: uv run familybot")
            print("2. Test admin commands in Discord DMs:")
            print("   - !token_status (check current token)")
            print("   - !force_token (force token update)")
            return True
        else:
            print("❌ Some tests failed. Please check the errors above.")
            return False


async def main():
    tester = TokenTester()
    success = await tester.run_full_test()

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
