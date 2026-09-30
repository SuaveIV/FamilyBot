#!/usr/bin/env python3
"""Test script for the token_sender plugin.

Tests token acquisition functionality (HTTP renewal with browser fallback)
without running the full Discord bot.
"""

import asyncio
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            reconf(encoding="utf-8", errors="replace")

try:
    from familybot.config import BROWSER_PROFILE_PATH, PROJECT_ROOT, TOKEN_SAVE_PATH
    from familybot.lib.token_service import (
        acquire_fresh_token,
        decode_token_expiry,
        extract_refresh_token,
        save_token_files,
    )
except ImportError as e:
    print(f"❌ Could not import configuration or services: {e}")
    print("Make sure you're running this from the FamilyBot root directory")
    sys.exit(1)


class TokenTester:
    def __init__(self):
        self.actual_token_save_dir = Path(PROJECT_ROOT) / TOKEN_SAVE_PATH
        self.browser_profile_path = (
            Path(PROJECT_ROOT) / BROWSER_PROFILE_PATH if BROWSER_PROFILE_PATH else None
        )
        self.test_token_save_dir = Path(tempfile.mkdtemp())
        print(f"Created temporary directory for test tokens: {self.test_token_save_dir}")

    def cleanup(self):
        if self.test_token_save_dir.exists():
            shutil.rmtree(self.test_token_save_dir)
            print(f"Cleaned up temporary directory: {self.test_token_save_dir}")

    def __del__(self):
        self.cleanup()

    async def test_credentials_source(self):
        """Test if browser profile or stored refresh token exists."""
        print("🔍 Testing credentials and profile availability...")

        refresh_token = extract_refresh_token(
            profile_path=self.browser_profile_path,
            token_dir=self.actual_token_save_dir,
        )
        if refresh_token:
            print("✅ Found durable steamRefresh_steam credential.")
            return True

        if self.browser_profile_path and self.browser_profile_path.exists():
            print(f"✅ Browser profile directory found at: {self.browser_profile_path}")
            return True

        print("❌ No valid credentials or browser profile found.")
        print("   Run 'uv run python scripts/setup_browser.py' first")
        return False

    async def test_token_extraction(self):
        """Test acquiring a fresh token via HTTP or fallback."""
        print("\n🔍 Testing token acquisition...")
        try:
            token, method = await acquire_fresh_token(
                profile_path=self.browser_profile_path,
                token_dir=self.actual_token_save_dir,
                prefer_http=True,
            )
            print(f"✅ Successfully acquired token via '{method}' method!")
            print(f"   Token preview: {token[:20]}...")
            return token, method
        except Exception as e:
            print(f"❌ Error during token acquisition: {e}")
            return None, ""

    def test_token_decoding(self, token: str):
        """Test token decoding and expiry extraction."""
        print("\n🔍 Testing token decoding...")
        try:
            exp_timestamp = decode_token_expiry(token)
            exp_time = datetime.fromtimestamp(exp_timestamp, tz=UTC)
            now = datetime.now(tz=UTC)
            time_remaining = exp_time - now

            print("✅ Token decoded successfully")
            print(f"   Expires at: {exp_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"   Time remaining: {str(time_remaining).split('.')[0]}")

            if time_remaining.total_seconds() > 0:
                print("✅ Token is valid")
                return exp_timestamp

            print("❌ Token has already expired")
            return None
        except Exception as e:
            print(f"❌ Error decoding token: {e}")
            return None

    def test_token_storage(self, token: str, exp_timestamp: float):
        """Test saving token to temporary storage."""
        print("\n🔍 Testing token storage...")
        try:
            changed, saved_exp = save_token_files(token, token_save_dir=self.test_token_save_dir)
            token_file = self.test_token_save_dir / "token"
            exp_file = self.test_token_save_dir / "token_exp"

            if not token_file.is_file() or not exp_file.is_file():
                print("❌ Token files were not created")
                return False

            if int(saved_exp) != int(exp_timestamp):
                print("❌ Token expiry mismatch")
                return False

            print(f"✅ Token saved to: {token_file}")
            print(f"✅ Expiry saved to: {exp_file}")
            return True
        except Exception as e:
            print(f"❌ Error saving token: {e}")
            return False

    async def run_full_test(self):
        """Run the complete test suite."""
        print("🧪 Starting Token Sender Plugin Test")
        print("=" * 50)

        creds_ok = await self.test_credentials_source()

        token, method = await self.test_token_extraction()
        if not token:
            print("\n❌ Token acquisition failed. Cannot continue with remaining tests.")
            return False

        exp_timestamp = self.test_token_decoding(token)
        if not exp_timestamp:
            print("\n❌ Token decoding failed. Cannot continue with remaining tests.")
            return False

        storage_ok = self.test_token_storage(token, exp_timestamp)

        try:
            live_token_path = Path(self.actual_token_save_dir) / "token"
            if live_token_path.is_file():
                live_token = live_token_path.read_text(encoding="utf-8").strip()
                print("\n🔍 Comparing with live bot token...")
                if live_token == token:
                    print("✅ Live token matches the newly fetched token.")
                else:
                    print("⚠️  Live token differs from the newly fetched token.")
                    print("   (This is normal if the live token is older but still valid.)")
            else:
                print("\n- No live token found to compare with.")
        except Exception as e:
            print(f"\n⚠️  Could not compare with live token: {e}")

        print("\n" + "=" * 50)
        if creds_ok and token and exp_timestamp and storage_ok:
            print(f"🎉 All tests passed! Token sender ({method}) is working correctly.")
            print("\nNext steps:")
            print("1. Start FamilyBot: uv run familybot")
            print("2. Test admin commands in Discord DMs:")
            print("   - !token_status (check current token)")
            print("   - !force_token (force token update)")
            return True

        print("❌ Some tests failed. Please check the errors above.")
        return False


async def main():
    tester = TokenTester()
    try:
        success = await tester.run_full_test()
        if not success:
            sys.exit(1)
    finally:
        tester.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
