#!/usr/bin/env python3
"""Script to force an immediate update of the Steam webapi_token.

Attempts fast HTTP token refresh first using stored credentials,
falling back to Camoufox browser automation if available.
"""

import argparse
import asyncio
import logging
import sys
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
    from familybot.lib.token_service import acquire_fresh_token, save_token_files
except ImportError as e:
    print(f"❌ Could not import configuration: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def run_force_update(*, prefer_http: bool = True) -> bool:
    """Force an immediate update of the Steam token."""
    logger.info("Starting token force update (prefer_http=%s)...", prefer_http)
    try:
        token, method = await acquire_fresh_token(
            profile_path=BROWSER_PROFILE_PATH,
            token_dir=Path(PROJECT_ROOT) / TOKEN_SAVE_PATH,
            prefer_http=prefer_http,
        )

        changed, exp_timestamp = save_token_files(
            token, token_save_dir=Path(PROJECT_ROOT) / TOKEN_SAVE_PATH
        )
        exp_dt = datetime.fromtimestamp(exp_timestamp, tz=UTC)
        logger.info("✅ Token force update successful using '%s'!", method)
        logger.info("   Token preview: %s...", token[:20])
        logger.info("   Expires at: %s", exp_dt)
        logger.info("   Changed on disk: %s", changed)
        return True
    except Exception as e:
        logger.error("Token update failed: %s", e)
        return False


async def main() -> None:
    parser = argparse.ArgumentParser(description="Force an immediate update of the Steam token.")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Force using Camoufox browser automation instead of fast HTTP renewal",
    )
    args = parser.parse_args()

    success = await run_force_update(prefer_http=not args.browser)
    if success:
        print("\n🎉 Token force update completed successfully.")
        sys.exit(0)

    print("\n❌ Token update failed.")
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
