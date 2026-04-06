# File: scripts/setup_browser.py
import asyncio
import os
from pathlib import Path

from camoufox.async_api import AsyncCamoufox

# Configuration constants
MAX_RETRIES = 5  # Maximum consecutive errors before giving up

# Define the path for your dedicated browser profile
# This will be created inside your FamilyBot project directory (one level up from scripts/)
PROFILE_PATH = Path(__file__).parent.parent / "FamilyBotBrowserProfile"


async def setup_browser_profile():
    print(f"Launching Camoufox with persistent context at: {PROFILE_PATH.resolve()}")
    print("Please log into Steam in the opened browser window.")
    print("Once logged in, you can:")
    print("  1. Close the browser window, OR")
    print("  2. Press Ctrl+C in this terminal")
    print("Camoufox will save your session automatically.")
    print("\nStarting browser...")

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

        consecutive_errors = 0
        try:
            while True:
                try:
                    await page.title()  # Throws if browser is closed
                    await asyncio.sleep(1)
                    consecutive_errors = 0  # Reset counter on successful iteration
                except RuntimeError as e:
                    # Browser-closed events typically raise RuntimeError with specific messages
                    if "Target closed" in str(e) or "closed" in str(e).lower():
                        print("Browser window was closed by user.")
                        break
                    else:
                        # Unexpected RuntimeError, track and check retry limit
                        consecutive_errors += 1
                        print(f"⚠️  Unexpected browser error: {e}")
                        if consecutive_errors >= MAX_RETRIES:
                            print(
                                f"❌ Browser check failed {consecutive_errors} consecutive times. Giving up."
                            )
                            break
                        await asyncio.sleep(3)  # Brief delay before retry

                except asyncio.CancelledError:
                    # Task was cancelled, break the loop immediately
                    print("Browser check task was cancelled.")
                    raise  # Re-raise to propagate cancellation
                except Exception as e:
                    # Catch other unexpected errors, track and check retry limit
                    consecutive_errors += 1
                    print(f"⚠️  Unexpected error during browser check: {e}")
                    if consecutive_errors >= MAX_RETRIES:
                        print(
                            f"❌ Browser check failed {consecutive_errors} consecutive times. Giving up."
                        )
                        break
                    await asyncio.sleep(3)  # Brief delay before retry

        except KeyboardInterrupt:
            print("\nCtrl+C detected. Closing browser gracefully...")

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
    print(
        "\n🎉 Setup complete! You can now run the FamilyBot and the token_sender plugin will work."
    )


if __name__ == "__main__":
    asyncio.run(setup_browser_profile())
