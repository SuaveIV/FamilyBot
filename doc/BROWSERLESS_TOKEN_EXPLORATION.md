# Browserless Steam Web Token Exploration

## Overview

This note covers how FamilyBot can acquire and refresh its Steam Web API token without keeping a headless browser around.

Currently, FamilyBot uses Camoufox (a Firefox fork stripped of common bot signatures) to load a stored profile, navigate to `store.steampowered.com/pointssummary/ajaxgetasyncconfig`, and pull the `webapi_token` out of the response HTML with regex.

Testing against Steam's servers shows that running a browser isn't required for token renewal. A single HTTP `GET` to Steam's session renewal endpoint with the refresh cookie (`steamRefresh_steam`) issues a new access token and returns the `webapi_token` in roughly 1.2 seconds.

---

## Token Architecture in Steam

FamilyBot needs this token for `IFamilyGroupsService/GetSharedLibraryApps/v1/`. Because family sharing includes private user library data, standard Steamworks Web API keys cannot read it; the endpoint requires an OAuth JWT access token issued to an account inside that family group.

Steam splits modern web auth into two tokens:

| Token | Cookie Name | Scope / Audience | Lifespan | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Refresh Token** | `steamRefresh_steam` | `['web', 'renew', 'derive']` | ~200 days | Renews web sessions on `login.steampowered.com`. |
| **Access Token** | `steamLoginSecure` | `['web:store']` | 24 hours | Short-lived JWT for the store site; contains the `webapi_token`. |

### The Token Structure

The `steamLoginSecure` cookie follows the format `steamid||<JWT>`.

Inspecting the payload reveals:

- `aud`: `["web:store"]`
- `iss`: `r:<refresh_token_jti>` (proves direct derivation from the refresh token)
- `exp`: Epoch timestamp precisely 24 hours from issuance
- `rt_exp`: Epoch timestamp of the underlying refresh token (~200 days)

The `webapi_token` returned by `pointssummary/ajaxgetasyncconfig` is identical to the JWT embedded inside `steamLoginSecure`.

---

## Experimental Findings

We conducted several experiments using Python's standard library (`urllib.request` and `http.cookiejar`) without browser drivers.

### 1. Direct Request With Expired `steamLoginSecure`

Sending a direct HTTP GET request to `https://store.steampowered.com/pointssummary/ajaxgetasyncconfig` with an expired access token returns:

```json
{"success": 1, "data": []}
```

Steam returns a HTTP 200 status code but an empty data array, indicating an unauthenticated state.

### 2. The Native Web Renewal Endpoint

Steam's web infrastructure includes a dedicated redirect endpoint for session renewal:

```text
https://login.steampowered.com/jwt/refresh?redir=https%3A%2F%2Fstore.steampowered.com%2Fpointssummary%2Fajaxgetasyncconfig
```

When requested via plain HTTP with only the `steamRefresh_steam` cookie:

1. `login.steampowered.com` validates the refresh token.
2. The server responds with `Set-Cookie: steamLoginSecure=<new_jwt>; Domain=store.steampowered.com; Secure; HttpOnly`.
3. The client follows the redirect to `ajaxgetasyncconfig`.
4. Steam returns the full JSON object containing a fresh `webapi_token`.

```json
{
  "data": {
    "webapi_token": "eyAidHlwIjogIkpXVCIsICJhbGciOiAiRWREU0Ei..."
  },
  "success": 1
}
```

### 3. End-to-End API Verification

We used the token obtained via this browserless HTTP request to call `IFamilyGroupsService/GetSharedLibraryApps/v1/`:

- **HTTP Status**: 200 OK
- **Apps Returned**: 3,743 family shared games
- **Total Execution Time**: 1.2 seconds (including network round-trips)
- **Memory Consumption**: Standard Python process overhead (< 25MB)

---

## Background: Why Camoufox Replaced Playwright

FamilyBot originally used Selenium, then Playwright, and eventually Camoufox:

1. **Playwright Detection**: Headless Chromium has well-known browser fingerprints. Akamai Bot Manager on `store.steampowered.com` flagged Playwright requests, returning empty responses or bot challenges.
2. **Camoufox Workaround**: Camoufox bypasses Akamai by modifying Firefox internals directly. But keeping browser binaries around creates overhead: 10 to 15 seconds per launch, 200MB+ RAM usage, and pinned dependencies like `playwright<1.61`.
3. **HTTP Behavior**: Akamai's checks target browser execution (canvas, WebGL, navigator properties). Plain HTTP requests to `login.steampowered.com/jwt/refresh` with an existing `steamRefresh_steam` cookie pass through as standard session renewals without triggering bot checks.

---

## Architectural Options

### Option 1: Hybrid (Implemented)

Keep the interactive browser login for initial setup, but run scheduled refreshes over HTTP.

- **Initial Setup**: Run `scripts/setup_browser.py` once every few months to log into Steam in a real window. This saves the profile cookies (including `steamRefresh_steam`).
- **Recurring Bot Execution**: `token_sender.py` reads `steamRefresh_steam` from the profile or tokens directory and sends an async `aiohttp` GET request to `login.steampowered.com/jwt/refresh`.
- **Trade-off**: The bot never launches a browser during normal operation. Setup still needs Camoufox installed for that initial login window.

### Option 2: Fully Headless (QR-Code Login)

Drop browser dependencies entirely, including setup.

- **Flow**:
  1. Setup script calls `IAuthenticationService/BeginAuthSessionViaQR` on `api.steampowered.com`.
  2. The script prints a QR code in the terminal.
  3. You scan the code in the Steam Mobile App and tap "Approve".
  4. The script polls `PollAuthSessionStatus`, gets the `refresh_token` and `access_token`, and stores them.
  5. Refreshes continue over HTTP.
- **Trade-off**: Drops `camoufox`, `playwright`, and Firefox binaries completely, freeing hundreds of megabytes from the environment. Requires implementing the QR polling handshake.

---

## Comparison Matrix

| Metric / Feature | Current (Camoufox) | Option 1: HTTP Refresh (Hybrid) | Option 2: Fully Headless (QR + HTTP) |
| :--- | :--- | :--- | :--- |
| **Daily Refresh Execution** | Launches browser (~12s) | `aiohttp.get()` (~1s) | `aiohttp.get()` (~1s) |
| **Runtime Memory Spike** | 200MB – 350MB | < 1MB additional | < 1MB additional |
| **External Dependencies** | `camoufox`, `playwright<1.61`, Firefox binaries | Lightweight HTTP only | Lightweight HTTP + `qrcode` (for CLI display) |
| **Initial Login Method** | Interactive GUI browser window | Interactive GUI browser window | Mobile App QR scan in terminal |
| **Maintenance Risk** | Upstream browser/driver compatibility bugs | Steam web redirect changes | Steam auth protobuf/API changes |

---

## Minimal Proof of Concept Implementation

Below is the verified logic required to perform a token refresh purely via HTTP:

```python
import re
import urllib.parse
from http.cookiejar import Cookie, CookieJar
import aiohttp

async def refresh_steam_token(steam_refresh_cookie_value: str) -> str:
    """
    Exchange a durable steamRefresh_steam cookie value for a fresh webapi_token
    via Steam's native JWT refresh redirect.
    """
    url = (
        "https://login.steampowered.com/jwt/refresh?"
        "redir=https%3A%2F%2Fstore.steampowered.com%2Fpointssummary%2Fajaxgetasyncconfig"
    )
    
    cookies = {
        "steamRefresh_steam": steam_refresh_cookie_value
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:
        async with session.get(url, allow_redirects=True) as response:
            text = await response.text()
            
            match = re.search(r'"webapi_token"\s*:\s*"([^"]+)"', text)
            if not match:
                raise ValueError("Could not find webapi_token in refresh response")
                
            return match.group(1)
```
