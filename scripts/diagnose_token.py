#!/usr/bin/env python3
"""
Diagnostic script to test Steam token extraction and debug issues.
This script is designed to run from your FamilyBot project directory.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
import re

# Configuration - automatically detect project root
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR

# Check if we're in the scripts directory, if so go up one level
if SCRIPT_DIR.name == "scripts":
    PROJECT_ROOT = SCRIPT_DIR.parent

print(f"🏠 Project root: {PROJECT_ROOT}")

# Try to find browser profile in common locations
BROWSER_PROFILE_PATHS = [
    PROJECT_ROOT / "FamilyBotBrowserProfile",
    Path.home() / "FamilyBotBrowserProfile",
]

BROWSER_PROFILE_PATH = None
for path in BROWSER_PROFILE_PATHS:
    if path.exists():
        BROWSER_PROFILE_PATH = path
        break

# Output directory for debug files
OUTPUT_DIR = PROJECT_ROOT
if not os.access(OUTPUT_DIR, os.W_OK):
    OUTPUT_DIR = Path.home()

try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("❌ Playwright not available. Please install with:")
    print("   pip install playwright")
    print("   playwright install chromium")
    print("\n   Or if using uv:")
    print("   uv pip install playwright")
    print("   uv run playwright install chromium")
    sys.exit(1)


async def diagnose_token_extraction():
    """Diagnose token extraction issues with detailed logging."""
    print("\n" + "=" * 60)
    print("🔍 Steam Token Diagnostic Tool")
    print("=" * 60)

    print(f"\n📁 Configuration:")
    print(f"   Project root: {PROJECT_ROOT}")
    print(
        f"   Browser profile: {BROWSER_PROFILE_PATH if BROWSER_PROFILE_PATH else 'Not found'}"
    )
    print(f"   Output directory: {OUTPUT_DIR}")

    if not BROWSER_PROFILE_PATH:
        print("\n⚠️  WARNING: No browser profile found!")
        print("   Checked locations:")
        for path in BROWSER_PROFILE_PATHS:
            print(f"   - {path}")
        print("\n   You may need to run the setup script first:")
        print("   just setup-browser")
        print("   OR: python scripts/setup_browser.py")

        # Ask if user wants to continue without profile
        response = input("\n❓ Continue without profile? (y/N): ").strip().lower()
        if response not in ["y", "yes"]:
            print("Exiting...")
            return

    async with async_playwright() as p:
        try:
            # Launch with profile if available
            if BROWSER_PROFILE_PATH and BROWSER_PROFILE_PATH.exists():
                print(f"\n🌐 Launching browser with profile...")
                print(f"   Profile: {BROWSER_PROFILE_PATH}")

                # Check for storage state
                storage_state_path = BROWSER_PROFILE_PATH / "storage_state.json"
                storage_state = None
                if storage_state_path.exists():
                    try:
                        with open(storage_state_path, "r") as f:
                            storage_state = json.load(f)
                        print("   ✅ Found storage_state.json")
                    except Exception as e:
                        print(f"   ⚠️  Could not load storage_state.json: {e}")

                context = await p.chromium.launch_persistent_context(
                    user_data_dir=str(BROWSER_PROFILE_PATH),
                    headless=False,  # Non-headless for debugging
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )

                # Apply cookies if available
                if storage_state:
                    try:
                        await context.add_cookies(storage_state.get("cookies", []))
                        print("   ✅ Applied cookies from storage_state.json")
                    except Exception as e:
                        print(f"   ⚠️  Could not apply cookies: {e}")

                page = await context.new_page()
            else:
                print("\n🌐 Launching browser without profile...")
                print("   ⚠️  You will need to log in manually")
                browser = await p.chromium.launch(headless=False)
                context = await browser.new_context()
                page = await context.new_page()

            # Navigate to the points summary page
            print("\n📄 Navigating to Steam points summary page...")
            print(
                "   URL: https://store.steampowered.com/pointssummary/ajaxgetasyncconfig"
            )

            try:
                await page.goto(
                    "https://store.steampowered.com/pointssummary/ajaxgetasyncconfig",
                    wait_until="networkidle",
                    timeout=30000,
                )
            except Exception as e:
                print(f"   ⚠️  Navigation warning: {e}")
                print("   Continuing anyway...")

            # Get page content
            content = await page.content()
            print(f"\n📝 Page content length: {len(content):,} characters")

            # Check for empty JSON response (Steam specific issue)
            if '{"success":1,"data":[]}' in content or (
                len(content) < 200 and '"success":1' in content
            ):
                print("\n   ⚠️  CRITICAL: Steam returned an empty data response.")
                print(f"   Response content: {content.strip()}")
                print("   This indicates the session is invalid or not logged in.")
                print("   The browser profile might need to be refreshed.")

            # Save content for inspection
            debug_file = OUTPUT_DIR / "steam_page_content.html"
            try:
                debug_file.write_text(content, encoding="utf-8")
                print(f"💾 Saved page content to: {debug_file}")
            except Exception as e:
                print(f"⚠️  Could not save content: {e}")

            # Check for login indicators
            print("\n🔐 Login status check:")
            login_indicators = ["login", "sign in", "signin", "join steam"]
            found_indicators = [
                ind for ind in login_indicators if ind in content.lower()
            ]

            if found_indicators:
                print(f"   ⚠️  Page appears to show login form")
                print(f"   Found indicators: {', '.join(found_indicators)}")
                print("   ❌ You are likely NOT logged into Steam")
            else:
                print("   ✅ No obvious login indicators found")

            # Try to find the webapi_token using multiple methods
            print("\n🔍 Searching for webapi_token...")
            print("-" * 60)

            found_token = False

            # Method 1: Original marker search with variations
            print("\n📌 Method 1: String pattern search")
            patterns = [
                ('"webapi_token":"', '"}'),
                ('"webapi_token": "', '"'),
                ('webapi_token":"', '"'),
                ('webapi_token": "', '"'),
                ("'webapi_token':'", "'}"),
                ("'webapi_token': '", "'"),
            ]

            for i, (start_marker, end_marker) in enumerate(patterns, 1):
                start_index = content.find(start_marker)
                if start_index != -1:
                    key_start = start_index + len(start_marker)
                    key_end = content.find(end_marker, key_start)
                    if key_end != -1:
                        token = content[key_start:key_end]
                        print(f"   ✅ Found token with pattern {i}: {start_marker}")
                        print(f"   Token preview: {token[:30]}...")
                        print(f"   Token length: {len(token)} characters")
                        found_token = True
                        break

            if not found_token:
                print("   ❌ Could not find token with any string pattern")

            # Method 2: Regex search for JSON
            print("\n📌 Method 2: Regex JSON search (Production Logic)")
            try:
                # More flexible regex patterns
                json_patterns = [
                    r'"webapi_token"\s*:\s*"([^"]+)"',
                    r"'webapi_token'\s*:\s*'([^']+)'",
                    r'webapi_token\s*:\s*"([^"]+)"',
                ]

                for i, pattern in enumerate(json_patterns, 1):
                    matches = re.findall(pattern, content)
                    if matches:
                        print(f"   ✅ Found {len(matches)} token(s) with pattern {i}")
                        for j, match in enumerate(matches[:3], 1):
                            print(f"   Token {j} preview: {match[:30]}...")
                        found_token = True
                        break

                if not found_token:
                    print("   ❌ No tokens found with regex patterns")
            except Exception as e:
                print(f"   ⚠️  Regex search error: {e}")

            # Method 3: Search for any occurrence of "webapi"
            print("\n📌 Method 3: General 'webapi' search")
            webapi_count = content.lower().count("webapi")
            print(f"   Found 'webapi' {webapi_count} times in page")

            if webapi_count > 0:
                # Find context around webapi mentions
                webapi_contexts = []
                for match in re.finditer(
                    r".{0,50}webapi.{0,50}", content, re.IGNORECASE
                ):
                    webapi_contexts.append(match.group())

                if webapi_contexts:
                    print(f"   Showing first 3 contexts:")
                    for i, ctx in enumerate(webapi_contexts[:3], 1):
                        # Clean up for display
                        ctx_clean = ctx.replace("\n", " ").replace("\r", "")
                        print(f"   {i}. ...{ctx_clean[:80]}...")

            # Method 4: Page metadata
            print("\n📌 Method 4: Page metadata")
            title = await page.title()
            print(f"   Page title: {title}")

            url = page.url
            print(f"   Current URL: {url}")

            # Method 5: JavaScript evaluation
            print("\n📌 Method 5: JavaScript evaluation")
            try:
                js_result = await page.evaluate("""
                    () => {
                        const results = {};

                        // Check scripts for webapi_token
                        const scripts = document.getElementsByTagName('script');
                        results.scriptCount = scripts.length;
                        results.scriptsWithToken = 0;

                        for (let script of scripts) {
                            if (script.textContent.includes('webapi_token')) {
                                results.scriptsWithToken++;
                                const match = script.textContent.match(/"webapi_token"\\s*:\\s*"([^"]+)"/);
                                if (match && match[1]) {
                                    results.token = match[1];
                                    results.tokenLength = match[1].length;
                                    break;
                                }
                            }
                        }

                        // Check for common Steam global variables
                        results.hasWindowG = typeof window.g_rgLoyaltyRewardDefs !== 'undefined';
                        results.hasSessionID = typeof g_sessionID !== 'undefined';

                        return results;
                    }
                """)

                print(f"   Scripts on page: {js_result.get('scriptCount', 0)}")
                print(
                    f"   Scripts with 'webapi_token': {js_result.get('scriptsWithToken', 0)}"
                )
                print(
                    f"   Has window.g_rgLoyaltyRewardDefs: {js_result.get('hasWindowG', False)}"
                )
                print(f"   Has g_sessionID: {js_result.get('hasSessionID', False)}")

                if "token" in js_result:
                    print(f"   ✅ Found token via JavaScript!")
                    print(f"   Token preview: {js_result['token'][:30]}...")
                    print(f"   Token length: {js_result['tokenLength']} characters")
                    found_token = True
                else:
                    print("   ❌ No token found via JavaScript")

            except Exception as e:
                print(f"   ⚠️  JavaScript evaluation error: {e}")

            # Take a screenshot for visual debugging
            screenshot_path = OUTPUT_DIR / "steam_page_screenshot.png"
            try:
                await page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"\n📸 Screenshot saved to: {screenshot_path}")
            except Exception as e:
                print(f"\n⚠️  Could not save screenshot: {e}")

            # Final summary
            print("\n" + "=" * 60)
            if found_token:
                print("✅ SUCCESS: Token was found!")
            else:
                print("❌ FAILURE: No token found")
            print("=" * 60)

            # Wait for user to inspect
            print("\n⏸️  Browser will stay open for 15 seconds...")
            print("   Check the browser window to see what Steam returned")
            await asyncio.sleep(15)

        except Exception as e:
            print(f"\n❌ Error during diagnosis: {e}")
            import traceback

            traceback.print_exc()
        finally:
            print("\n🔒 Closing browser...")
            await context.close()


async def main():
    """Main diagnostic function."""
    if not PLAYWRIGHT_AVAILABLE:
        return

    try:
        await diagnose_token_extraction()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")

    print("\n" + "=" * 60)
    print("Diagnosis complete!")
    print("=" * 60)

    print("\n📋 Next steps:")
    print(f"1. Check the saved HTML file: {OUTPUT_DIR}/steam_page_content.html")
    print(f"2. Look at the screenshot: {OUTPUT_DIR}/steam_page_screenshot.png")
    print("3. Review the output above for any findings")

    print("\n💡 If no token was found:")
    print("   a) You may not be logged into Steam - run the setup script")
    print("   b) Steam may have changed their API - check the HTML file")
    print("   c) Your browser profile may have expired - delete and recreate it")

    print("\n🔧 Common fixes:")
    print("   - Delete profile: rm -rf FamilyBotBrowserProfile/")
    print("   - Setup again: just setup-browser")
    print("   - Or manually: python scripts/setup_browser.py")


if __name__ == "__main__":
    print("🚀 Starting Steam Token Diagnostics\n")
    asyncio.run(main())
