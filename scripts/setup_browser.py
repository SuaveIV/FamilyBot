# File: scripts/setup_browser.py
import asyncio
import os
import sys
from pathlib import Path

from camoufox.async_api import AsyncCamoufox

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            reconf(encoding="utf-8", errors="replace")

# Configuration constants
MAX_RETRIES = 5  # Maximum consecutive errors before giving up

# Define the path for your dedicated browser profile
# This will be created inside your FamilyBot project directory (one level up from scripts/)
PROFILE_PATH = Path(__file__).parent.parent / "FamilyBotBrowserProfile"


async def _wait_for_user_login(page) -> bool:
    """Monitor browser page until user closes it or error limit is reached."""
    consecutive_errors = 0
    while True:
        try:
            await page.title()
            await asyncio.sleep(1)
            consecutive_errors = 0
        except RuntimeError as e:
            if "Target closed" in str(e) or "closed" in str(e).lower():
                print("Browser window was closed by user.")
                return True
            consecutive_errors += 1
            print(f"⚠️  Unexpected browser error: {e}")
            if consecutive_errors >= MAX_RETRIES:
                print(f"❌ Browser check failed {consecutive_errors} times. Giving up.")
                return False
            await asyncio.sleep(3)
        except asyncio.CancelledError:
            print("Browser check task was cancelled.")
            return True
        except Exception as e:
            consecutive_errors += 1
            print(f"⚠️  Unexpected error during browser check: {e}")
            if consecutive_errors >= MAX_RETRIES:
                print(f"❌ Browser check failed {consecutive_errors} times. Giving up.")
                return False
            await asyncio.sleep(3)


async def setup_browser_profile():
    print(f"Launching Camoufox with persistent context at: {PROFILE_PATH.resolve()}")
    print("Please log into Steam in the opened browser window.")
    print("Once logged in, you can:")
    print("  1. Close the browser window, OR")
    print("  2. Press Ctrl+C in this terminal")
    print("Camoufox will save your session automatically.")
    print("\nStarting browser...")

    setup_success = True
    async with AsyncCamoufox(
        persistent_context=True,
        user_data_dir=str(PROFILE_PATH),
        headless=False,
        extra_http_headers={"accept-encoding": "identity"},
    ) as context:
        page = await context.new_page()
        try:
            await page.goto("https://store.steampowered.com/login/")
        except Exception as e:
            print(f"⚠️  Warning: Failed to navigate to login page: {e}")
            print("   Continuing anyway - you may need to navigate manually")

        print("Browser launched! Please log into Steam.")
        print(
            "Press Ctrl+C when you're done logging in to close the browser gracefully."
        )

        try:
            setup_success = await _wait_for_user_login(page)
        except KeyboardInterrupt:
            print("\nCtrl+C detected. Closing browser gracefully...")

    if setup_success:
        print("✅ Browser closed successfully!")

    # Verify PROFILE_PATH was created and is writable
    if not PROFILE_PATH.exists():
        print("❌ ERROR: Profile directory was not created!")
        print(f"   Expected location: {PROFILE_PATH.resolve()}")
        return

    if not PROFILE_PATH.is_dir():
        print("❌ ERROR: Profile path exists but is not a directory!")
        print(f"   Path: {PROFILE_PATH.resolve()}")
        return

    if not os.access(PROFILE_PATH, os.W_OK):
        print("❌ ERROR: Profile directory is not writable!")
        print(f"   Path: {PROFILE_PATH.resolve()}")
        return

    print("✅ Profile saved successfully!")
    print(f"\n📁 Browser profile location: {PROFILE_PATH.resolve()}")

    print("\n🔍 Extracting and verifying Steam tokens...")
    try:
        from familybot.lib.token_service import (
            acquire_fresh_token,
            extract_refresh_token,
            save_refresh_token_file,
            save_token_files,
        )

        refresh_token = extract_refresh_token(profile_path=PROFILE_PATH)
        if refresh_token:
            save_refresh_token_file(refresh_token)
            print("✅ Durable refresh token saved for headless renewals.")
            token, method = await acquire_fresh_token(profile_path=PROFILE_PATH)
            save_token_files(token)
            print(f"✅ Initial access token verified and saved via {method}!")
        else:
            print("⚠️ Could not find steamRefresh_steam in browser cookies.")
            print("   Make sure you logged into Steam completely before closing the browser.")
    except Exception as e:
        print(f"⚠️ Token post-processing note: {e}")

    print(
        "\n🎉 Setup complete! You can now run FamilyBot and the token_sender plugin will work."
    )


if __name__ == "__main__":
    asyncio.run(setup_browser_profile())
