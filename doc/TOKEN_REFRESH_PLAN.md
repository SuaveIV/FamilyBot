# Token Refresh Mechanism Update Plan

## 1. Objective

Optimize the existing Playwright-based token refresh mechanism to reduce resource consumption and improve efficiency, while retaining the robustness and authenticity of using a real browser. Playwright will continue to be used for both the initial user login and subsequent token refreshes.

## 2. Problem

The previous Playwright implementation, while robust, launched a full Chromium instance with default settings every time a token refresh was needed. This led to:

- **Higher Resource Usage**: More CPU and RAM than necessary due to loading unused browser features and resources.
- **Slower Execution**: Longer refresh times due to loading all page assets (images, fonts, CSS).

## 3. Solution: Optimized Playwright Usage

### Phase 1: Initial Setup (Existing & Unchanged)

- User runs `scripts/setup_browser.py`.
- Playwright opens a browser.
- User logs in manually (2FA, etc.).
- Session cookies (specifically `steamLoginSecure`) are saved to `FamilyBotBrowserProfile/storage_state.json`.
- **Status**: _Implemented and working._

### Phase 2: Daily Refresh (Optimized Playwright)

- The bot wakes up to check token expiry.
- It launches Playwright with **optimized browser arguments** and **resource blocking** to speed up page load and reduce resource usage.
    1.  Launches a headless Chromium browser instance.
    2.  Uses persistent context from `FamilyBotBrowserProfile`.
    3.  Navigates to `https://store.steampowered.com/pointssummary/ajaxgetasyncconfig`.
    4.  Extracts the `webapi_token` from the page content.
- **Status**: _Implemented._

## 4. Implementation Details

### Changes in `token_sender.py` (Completed)

1.  **Optimized Playwright Launch Arguments**:
    - Added `--disable-extensions`, `--disable-gpu`, and `--blink-settings=imagesEnabled=false` to the `p.chromium.launch_persistent_context` arguments.
2.  **Resource Blocking**:
    - Implemented `page.route` to `abort()` requests for `image`, `stylesheet`, `font`, and `media` resource types.

These changes were applied to the `_get_token_with_playwright` method within `src/familybot/plugins/token_sender.py`.

### Related Tools / Scripts (Completed)

1.  **`scripts/test_token_plugin.py`**:
    - Modified to use a temporary directory for test token storage, ensuring non-destructive testing.
    - Updated with the same Playwright optimization arguments and resource blocking for consistency.
    - Added logic to compare the newly fetched token with the bot's live token for enhanced diagnostic information.
2.  **`scripts/force_token_update.py`**:
    - New script created to allow manual command-line execution of the optimized token refresh process, saving the result to the live `tokens/` directory.

## 5. Verification Plan

1.  **Run `just test-token`**:
    - Verify that tests pass.
    - Observe the output for the "Comparing with live bot token..." message and its result.
    - Confirm that the temporary directory is used and cleaned up.
2.  **Run `just force-token`**:
    - Verify that the token is updated in `tokens/token` and `tokens/token_exp`.
    - Check logs for confirmation that optimizations are applied (e.g., faster execution times).
3.  **Monitor Bot Operation**:
    - Ensure the bot continues to refresh its token successfully every day without issues.

## 6. Benefits

- **Enhanced Stability**: Retains the reliability of using a full browser.
- **Improved Performance**: Faster token refresh cycles due to reduced page load and optimized browser launch.
- **Lower Resource Consumption**: Uses less CPU and RAM during refreshes.
- **Safer Testing**: Test scripts no longer interfere with live bot data.
- **New Management Tools**: `force-token` script provides more control for administrators.
