"""Steam Web API token acquisition and renewal service.

Provides pure HTTP token renewal using the durable `steamRefresh_steam`
cookie as well as browser-based fallback extraction via Camoufox.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp
from yarl import URL

from familybot.config import (
    BROWSER_PROFILE_PATH,
    PROJECT_ROOT,
    TOKEN_SAVE_PATH,
)
from familybot.lib.logging_config import get_logger

try:
    from camoufox.async_api import AsyncCamoufox

    CAMOUFOX_AVAILABLE = True
except ImportError:
    CAMOUFOX_AVAILABLE = False
    AsyncCamoufox = None  # type: ignore[assignment, misc]

logger = get_logger("token_service")

# Regex to extract webapi_token from Steam page/JSON responses
TOKEN_PATTERN = re.compile(r'"webapi_token"\s*:\s*"([^"]+)"')
STEAM_REFRESH_ENDPOINT = (
    "https://login.steampowered.com/jwt/refresh?"
    "redir=https%3A%2F%2Fstore.steampowered.com%2Fpointssummary%2Fajaxgetasyncconfig"
)
STORE_POINTS_URL = "https://store.steampowered.com/pointssummary/ajaxgetasyncconfig"


def resolve_token_save_dir(token_dir: Path | str | None = None) -> Path:
    """Resolve the directory used for storing token files.

    Args:
        token_dir: Optional explicit path. Defaults to configured TOKEN_SAVE_PATH.

    Returns:
        Absolute Path to the token storage directory.

    """
    if token_dir:
        path = Path(token_dir)
        return path if path.is_absolute() else Path(PROJECT_ROOT) / path
    configured = Path(TOKEN_SAVE_PATH) if TOKEN_SAVE_PATH else Path("tokens")
    return configured if configured.is_absolute() else Path(PROJECT_ROOT) / configured


def resolve_browser_profile_path(profile_path: Path | str | None = None) -> Path | None:
    """Resolve the path to the browser profile directory.

    Args:
        profile_path: Optional explicit profile path.

    Returns:
        Resolved Path if configured, else None.

    """
    raw_path = profile_path or BROWSER_PROFILE_PATH
    if not raw_path:
        return None
    path = Path(raw_path)
    return path if path.is_absolute() else Path(PROJECT_ROOT) / path


def _extract_from_sqlite(sqlite_path: Path) -> str | None:
    """Read steamRefresh_steam cookie from a Firefox/Camoufox cookies.sqlite."""
    if not sqlite_path.is_file():
        return None
    try:
        uri = f"file:{sqlite_path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM moz_cookies WHERE name = 'steamRefresh_steam' "
                "ORDER BY expiry DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row and row[0]:
                logger.debug("Loaded steamRefresh_steam from cookies.sqlite")
                return str(row[0])
    except sqlite3.Error as e:
        logger.warning("Failed reading cookies.sqlite in %s: %s", sqlite_path.parent, e)
    return None


def _extract_from_storage_state(storage_json: Path) -> str | None:
    """Read steamRefresh_steam cookie from Playwright storage_state.json."""
    if not storage_json.is_file():
        return None
    try:
        data = json.loads(storage_json.read_text(encoding="utf-8"))
        for cookie in data.get("cookies", []):
            if cookie.get("name") == "steamRefresh_steam" and cookie.get("value"):
                logger.debug("Loaded steamRefresh_steam from storage_state.json")
                return str(cookie["value"])
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed reading storage_state.json in %s: %s", storage_json.parent, e)
    return None


def extract_refresh_token(
    profile_path: Path | str | None = None,
    token_dir: Path | str | None = None,
) -> str | None:
    """Extract the durable steamRefresh_steam value from files or browser profile.

    Checks sources in order:
    1. tokens/refresh_token file.
    2. cookies.sqlite in the browser profile.
    3. storage_state.json in the browser profile.

    Args:
        profile_path: Optional browser profile path.
        token_dir: Optional token directory path.

    Returns:
        The refresh token string if found, else None.

    """
    save_dir = resolve_token_save_dir(token_dir)
    refresh_file = save_dir / "refresh_token"
    if refresh_file.is_file():
        try:
            val = refresh_file.read_text(encoding="utf-8").strip()
            if val:
                logger.debug("Loaded steamRefresh_steam from %s", refresh_file)
                return val
        except OSError as e:
            logger.warning("Could not read %s: %s", refresh_file, e)

    resolved_profile = resolve_browser_profile_path(profile_path)
    if not resolved_profile or not resolved_profile.is_dir():
        logger.debug("No browser profile directory found at %s", resolved_profile)
        return None

    from_sqlite = _extract_from_sqlite(resolved_profile / "cookies.sqlite")
    if from_sqlite:
        return from_sqlite

    return _extract_from_storage_state(resolved_profile / "storage_state.json")


async def refresh_webapi_token_http(
    refresh_token: str,
    *,
    session: aiohttp.ClientSession | None = None,
    timeout_seconds: float = 15.0,
) -> str:
    """Exchange a steamRefresh_steam cookie for a fresh webapi_token via HTTP.

    Args:
        refresh_token: The steamRefresh_steam cookie value.
        session: Optional existing ClientSession.
        timeout_seconds: Timeout for the HTTP request.

    Returns:
        The extracted webapi_token string.

    Raises:
        ValueError: If token was not found or Steam session is expired.
        aiohttp.ClientError: If network request fails.

    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    jar = aiohttp.CookieJar()
    jar.update_cookies(
        {"steamRefresh_steam": refresh_token},
        response_url=URL("https://login.steampowered.com"),
    )

    async def _perform_request(sess: aiohttp.ClientSession) -> str:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with sess.get(
            STEAM_REFRESH_ENDPOINT,
            headers=headers,
            allow_redirects=True,
            timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            text = await resp.text()

        if '{"success":1,"data":[]}' in text or (len(text) < 200 and '"success":1' in text):
            msg = "Steam returned empty data response. Session expired or refresh token invalid."
            raise ValueError(msg)

        match = TOKEN_PATTERN.search(text)
        if not match:
            msg = "Could not find 'webapi_token' in Steam response."
            raise ValueError(msg)

        extracted = match.group(1).strip()
        if not extracted:
            msg = "Extracted webapi_token is empty."
            raise ValueError(msg)

        return extracted

    if session:
        session.cookie_jar.update_cookies(
            {"steamRefresh_steam": refresh_token},
            response_url=URL("https://login.steampowered.com"),
        )
        return await _perform_request(session)

    async with aiohttp.ClientSession(cookie_jar=jar) as new_session:
        return await _perform_request(new_session)


async def refresh_webapi_token_browser(
    profile_path: Path | str | None = None,
) -> str:
    """Extract Steam webapi_token using Camoufox browser automation.

    Args:
        profile_path: Path to the browser profile directory.

    Returns:
        The extracted webapi_token string.

    Raises:
        RuntimeError: If Camoufox is not available or extraction fails.

    """
    if not CAMOUFOX_AVAILABLE or AsyncCamoufox is None:
        msg = "Camoufox is not installed. Run 'uv add camoufox && uv run camoufox install'."
        raise RuntimeError(msg)

    resolved_profile = resolve_browser_profile_path(profile_path)
    kwargs: dict[str, Any] = {"headless": True}
    if resolved_profile and resolved_profile.is_dir():
        kwargs["persistent_context"] = True
        kwargs["user_data_dir"] = str(resolved_profile)
        logger.info("Launching Camoufox with profile: %s", resolved_profile)
    else:
        logger.info("Launching Camoufox without profile")

    async with AsyncCamoufox(**kwargs) as context:
        page = await context.new_page()
        try:
            await page.goto(STORE_POINTS_URL)
            await page.wait_for_load_state("networkidle")
            content = await page.content()

            if '{"success":1,"data":[]}' in content or (
                len(content) < 200 and '"success":1' in content
            ):
                msg = (
                    "Steam returned empty data response in browser. "
                    "Session expired. Run setup_browser.py."
                )
                raise ValueError(msg)

            try:
                rawdata_tab = page.locator("#rawdata-tab")
                if await rawdata_tab.count() > 0:
                    await rawdata_tab.click()
                    await page.wait_for_timeout(1000)
                    content = await page.content()
            except Exception as e:
                logger.debug("Could not click rawdata-tab: %s", e)

            match = TOKEN_PATTERN.search(content)
            if not match:
                msg = "Could not find 'webapi_token' in browser page content."
                raise ValueError(msg)

            extracted = match.group(1).strip()
            if not extracted:
                msg = "Extracted webapi_token from browser is empty."
                raise ValueError(msg)

            return extracted
        finally:
            await page.close()


async def acquire_fresh_token(
    profile_path: Path | str | None = None,
    token_dir: Path | str | None = None,
    *,
    prefer_http: bool = True,
) -> tuple[str, str]:
    """Acquire a fresh Steam webapi_token using HTTP first, with browser fallback.

    Args:
        profile_path: Optional browser profile path.
        token_dir: Optional token storage directory.
        prefer_http: If True, attempts HTTP refresh before browser fallback.

    Returns:
        Tuple of (token_string, method_used), where method_used is 'http' or 'camoufox'.

    Raises:
        RuntimeError: If all token acquisition methods fail.

    """
    if prefer_http:
        refresh_token = extract_refresh_token(profile_path=profile_path, token_dir=token_dir)
        if refresh_token:
            try:
                logger.info("Attempting fast HTTP token refresh...")
                token = await refresh_webapi_token_http(refresh_token)
                logger.info("Successfully refreshed Steam token via HTTP")
                return token, "http"
            except Exception as e:
                logger.warning("HTTP token refresh failed: %s. Falling back to browser...", e)
        else:
            logger.info("No refresh token found. Falling back to browser...")

        if CAMOUFOX_AVAILABLE:
            try:
                logger.info("Attempting token extraction via Camoufox...")
                token = await refresh_webapi_token_browser(profile_path=profile_path)
                logger.info("Successfully extracted Steam token via Camoufox")
                return token, "camoufox"
            except Exception as e:
                logger.error("Browser token extraction failed: %s", e)
    else:
        if CAMOUFOX_AVAILABLE:
            try:
                token = await refresh_webapi_token_browser(profile_path=profile_path)
                return token, "camoufox"
            except Exception as e:
                logger.warning("Browser token extraction failed: %s. Trying HTTP...", e)

        refresh_token = extract_refresh_token(profile_path=profile_path, token_dir=token_dir)
        if refresh_token:
            token = await refresh_webapi_token_http(refresh_token)
            return token, "http"

    msg = (
        "Failed to acquire Steam token. Please log into Steam using "
        "'uv run python scripts/setup_browser.py'."
    )
    raise RuntimeError(msg)


def decode_token_expiry(token: str) -> float:
    """Decode a Steam JWT token and return its expiration Unix timestamp.

    Args:
        token: The raw JWT string.

    Returns:
        Expiration timestamp as a float.

    Raises:
        ValueError: If token cannot be decoded or lacks 'exp' field.

    """
    parts = token.split(".")
    if len(parts) < 2:
        msg = "Token is not a valid JWT (missing segments)."
        raise ValueError(msg)

    padded = parts[1].replace("-", "+").replace("_", "/")
    padded += "=" * (-len(padded) % 4)

    try:
        data = json.loads(base64.b64decode(padded).decode("utf-8"))
        if "exp" not in data:
            msg = "JWT payload missing 'exp' field."
            raise ValueError(msg)
        return float(data["exp"])
    except (json.JSONDecodeError, binascii.Error, UnicodeDecodeError) as e:
        msg = f"Failed to decode token JWT: {e}"
        raise ValueError(msg) from e


def save_token_files(
    token: str,
    token_save_dir: Path | str | None = None,
) -> tuple[bool, float]:
    """Save webapi_token and token_exp files to disk.

    Args:
        token: The raw webapi_token string.
        token_save_dir: Path to directory for saving token files.

    Returns:
        Tuple of (has_token_changed: bool, exp_timestamp: float).

    """
    save_dir = resolve_token_save_dir(token_save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    token_path = save_dir / "token"
    exp_path = save_dir / "token_exp"

    existing_token = ""
    if token_path.is_file():
        try:
            existing_token = token_path.read_text(encoding="utf-8").strip()
        except OSError as e:
            logger.warning("Could not read existing token from %s: %s", token_path, e)

    exp_timestamp = decode_token_expiry(token)

    if existing_token == token:
        logger.debug("Token unchanged. No disk write required.")
        return False, exp_timestamp

    token_path.write_text(token, encoding="utf-8")
    exp_path.write_text(str(int(exp_timestamp)), encoding="utf-8")
    exp_dt = datetime.fromtimestamp(exp_timestamp, tz=UTC)
    logger.info("Saved new Steam token (expires: %s)", exp_dt)
    return True, exp_timestamp


def save_refresh_token_file(
    refresh_token: str,
    token_save_dir: Path | str | None = None,
) -> Path:
    """Save the durable steamRefresh_steam value to disk for headless renewals.

    Args:
        refresh_token: The raw steamRefresh_steam cookie string.
        token_save_dir: Path to directory for saving token files.

    Returns:
        Path to the saved refresh_token file.

    """
    save_dir = resolve_token_save_dir(token_save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    refresh_file = save_dir / "refresh_token"
    refresh_file.write_text(refresh_token.strip(), encoding="utf-8")
    logger.info("Saved durable refresh token to %s", refresh_file)
    return refresh_file
