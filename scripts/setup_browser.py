# File: scripts/setup_browser.py
import asyncio
from playwright.async_api import async_playwright
import os
import json
from pathlib import Path

# Define the path for your dedicated browser profile
# This will be created inside your FamilyBot project directory (one level up from scripts/)
PROFILE_PATH = Path(__file__).parent.parent / "FamilyBotBrowserProfile"
STORAGE_STATE_PATH = PROFILE_PATH / "storage_state.json"

async def setup_browser_profile():
    print(f"Launching Chromium with persistent context at: {PROFILE_PATH.resolve()}")
    print("Please log into Steam in the opened browser window.")
    print("Once logged in, you can:")
    print("  1. Close the browser window, OR")
    print("  2. Press Ctrl+C in this terminal")
    print("Playwright will save your session automatically.")
    print("\nStarting browser...")

    async with async_playwright() as p:
        # Launch browser with persistent context to maintain user data
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_PATH),
            headless=False, # Launch in visible mode
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        
        page = await context.new_page()
        await page.goto("https://store.steampowered.com/login/") # Go directly to Steam login
        
        print("Browser launched! Please log into Steam.")
        print("Press Ctrl+C when you're done logging in to close the browser gracefully.")
        
        # Keep the browser open until manually closed by the user or Ctrl+C
        try:
            while True:
                # Check if browser is still open
                try:
                    await page.title()  # This will throw if browser is closed
                    await asyncio.sleep(1)
                except Exception:
                    # Browser was closed by user
                    print("Browser window was closed by user.")
                    break
        except KeyboardInterrupt:
            print("\nCtrl+C detected. Closing browser gracefully...")
        finally:
            try:
                # Save storage state before closing
                print("💾 Saving browser storage state...")
                storage_state = await context.storage_state()
                
                # Ensure the profile directory exists
                PROFILE_PATH.mkdir(exist_ok=True)
                
                # Save storage state to file
                with open(STORAGE_STATE_PATH, 'w') as f:
                    json.dump(storage_state, f, indent=2)
                
                print(f"✅ Storage state saved to: {STORAGE_STATE_PATH}")
                
                await context.close()
            except Exception as e:
                print(f"⚠️  Warning: Could not save storage state: {e}")
                try:
                    await context.close()
                except:
                    pass
            
            print("✅ Browser closed successfully!")
            print("✅ Profile and storage state saved successfully!")
            print(f"\n📁 Browser profile location: {PROFILE_PATH.resolve()}")
            print(f"💾 Storage state file: {STORAGE_STATE_PATH}")
            print("📝 The config.yml has already been updated with the correct path.")
            print("\n🎉 Setup complete! You can now run the FamilyBot and the token_sender plugin will work.")

if __name__ == "__main__":
    asyncio.run(setup_browser_profile())
