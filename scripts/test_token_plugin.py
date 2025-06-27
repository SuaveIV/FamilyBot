#!/usr/bin/env python3
"""
Test script for the token_sender plugin.
This script tests the token extraction functionality without running the full bot.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("❌ Playwright not available. Please install with: uv add playwright")
    sys.exit(1)

# Import configuration
try:
    from familybot.config import PROJECT_ROOT, TOKEN_SAVE_PATH, BROWSER_PROFILE_PATH
except ImportError as e:
    print(f"❌ Could not import configuration: {e}")
    print("Make sure you're running this from the FamilyBot root directory")
    sys.exit(1)

import json
import base64
import binascii
from datetime import datetime

class TokenTester:
    def __init__(self):
        self.actual_token_save_dir = os.path.join(PROJECT_ROOT, TOKEN_SAVE_PATH)
        self.browser_profile_path = os.path.join(PROJECT_ROOT, BROWSER_PROFILE_PATH) if BROWSER_PROFILE_PATH else None
        
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
        
        async with async_playwright() as p:
            try:
                # Launch browser with profile if available
                if self.browser_profile_path and os.path.exists(self.browser_profile_path):
                    print(f"   Using browser profile: {self.browser_profile_path}")
                    
                    # Check if storage state file exists for better session persistence
                    storage_state_path = os.path.join(self.browser_profile_path, "storage_state.json")
                    storage_state = None
                    
                    if os.path.exists(storage_state_path):
                        try:
                            with open(storage_state_path, 'r') as f:
                                storage_state = json.load(f)
                            print("   Loaded storage state for session persistence")
                        except Exception as e:
                            print(f"   Warning: Could not load storage state: {e}")
                    
                    browser = await p.chromium.launch_persistent_context(
                        user_data_dir=self.browser_profile_path,
                        headless=True,
                        args=['--no-sandbox', '--disable-dev-shm-usage']
                    )
                    page = await browser.new_page()
                    
                    # If we have storage state, apply it to the context
                    if storage_state:
                        try:
                            await browser.add_cookies(storage_state.get('cookies', []))
                            print("   Applied cookies from storage state")
                        except Exception as e:
                            print(f"   Warning: Could not apply storage state cookies: {e}")
                else:
                    print("   Using default browser (no profile)")
                    browser = await p.chromium.launch(headless=True)
                    context = await browser.new_context()
                    page = await context.new_page()
                
                # Navigate to Steam points summary page
                print("   Navigating to Steam API endpoint...")
                await page.goto("https://store.steampowered.com/pointssummary/ajaxgetasyncconfig")
                await page.wait_for_load_state('networkidle')
                
                # Get page content
                content = await page.content()
                
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
                start_token_marker = '"webapi_token":"'
                end_token_marker = '"}'
                
                start_index = content.find(start_token_marker)
                if start_index == -1:
                    print("❌ Could not find 'webapi_token' in page source")
                    print("   This usually means you're not logged into Steam")
                    print("   Run 'uv run python scripts/setup_browser.py' to log in")
                    return False
                
                key_start = start_index + len(start_token_marker)
                key_end = content.find(end_token_marker, key_start)
                if key_end == -1:
                    print("❌ Could not find end of webapi_token")
                    return False
                
                extracted_key = content[key_start:key_end]
                
                if not extracted_key:
                    print("❌ Extracted token is empty")
                    return False
                
                print(f"✅ Successfully extracted token: {extracted_key[:20]}...")
                return extracted_key
                
            except Exception as e:
                print(f"❌ Error during token extraction: {e}")
                return False
            finally:
                await browser.close()
    
    def test_token_decoding(self, token):
        """Test token decoding and expiry extraction."""
        print("\n🔍 Testing token decoding...")
        
        try:
            # Decode token to get expiry time
            coded_string = token.split('.')[1]
            # Pad and replace URL-safe chars for base64 decoding
            padded_coded_string = coded_string.replace('-', '+').replace('_', '/')
            padded_coded_string += '=' * (-len(padded_coded_string) % 4)
            
            key_info = json.loads(base64.b64decode(padded_coded_string).decode('utf-8'))
            exp_timestamp = key_info['exp']
            
            exp_time = datetime.fromtimestamp(exp_timestamp)
            now = datetime.now()
            time_remaining = exp_time - now
            
            print(f"✅ Token decoded successfully")
            print(f"   Expires at: {exp_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Time remaining: {str(time_remaining).split('.')[0]}")
            
            if time_remaining.total_seconds() < 0:
                print("⚠️  Token has already expired!")
            elif time_remaining.total_seconds() < 3600:  # Less than 1 hour
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
            # Ensure directory exists
            os.makedirs(self.actual_token_save_dir, exist_ok=True)
            
            # Save token
            token_file_path = os.path.join(self.actual_token_save_dir, "token")
            with open(token_file_path, 'w') as token_file:
                token_file.write(token)
            
            # Save expiry time
            exp_file_path = os.path.join(self.actual_token_save_dir, "token_exp")
            with open(exp_file_path, "w") as exp_time_file:
                exp_time_file.write(str(exp_timestamp))
            
            print(f"✅ Token saved to: {token_file_path}")
            print(f"✅ Expiry saved to: {exp_file_path}")
            
            # Verify files can be read back
            with open(token_file_path, 'r') as f:
                saved_token = f.read().strip()
            with open(exp_file_path, 'r') as f:
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
        
        print("\n" + "=" * 50)
        if profile_ok and token and exp_timestamp and storage_ok:
            print("🎉 All tests passed! Token sender plugin is working correctly.")
            print("\nNext steps:")
            print("1. Start the FamilyBot: uv run python src/familybot/FamilyBot.py")
            print("2. Test admin commands in Discord DMs:")
            print("   - !token_status (check current token)")
            print("   - !force_token (force token update)")
            return True
        else:
            print("❌ Some tests failed. Please check the errors above.")
            return False

async def main():
    """Main test function."""
    if not PLAYWRIGHT_AVAILABLE:
        return
    
    tester = TokenTester()
    success = await tester.run_full_test()
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
