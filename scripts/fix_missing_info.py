#!/usr/bin/env python3
"""
Database Content Fixer for FamilyBot

Identifies and attempts to fix missing or 'Unknown' game names in the itad_price_cache
by cross-referencing with other tables and falling back to the Steam API.
"""

import asyncio
import logging
import sqlite3
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("fix_missing_info")

try:
    from familybot.lib.database import get_db_connection, get_write_connection
    from familybot.lib.game_details_repository import get_cached_game_details
    from familybot.lib.steam_helpers import fetch_game_details
    from familybot.lib.steam_api_manager import SteamAPIManager
except ImportError as e:
    logger.error(f"Could not import familybot modules: {e}")
    sys.exit(1)


async def fix_missing_names():
    """Identifies and fixes 'Unknown' or NULL names in itad_price_cache."""
    logger.info("Starting database content fix...")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        try:
            # Find problematic entries in itad_price_cache
            # Matches NULL, empty strings, or names starting with 'Unknown Game'
            cursor.execute("""
                SELECT appid, steam_game_name
                FROM itad_price_cache
                WHERE steam_game_name IS NULL
                   OR steam_game_name = ''
                   OR steam_game_name LIKE 'Unknown Game%'
            """)

            problematic_rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        conn.close()

    if not problematic_rows:
        logger.info("✅ No problematic game names found in itad_price_cache.")
        return

    logger.info(
        f"🔍 Found {len(problematic_rows)} entries with missing or 'Unknown' names."
    )

    fixed_count = 0
    internal_fixes = 0
    external_fixes = 0
    failed_fixes = 0
    manual_fixes = 0

    steam_api_manager = SteamAPIManager()

    # Collect updates for batch processing
    updates_to_apply = []

    # Track entries that couldn't be resolved automatically
    failed_entries = []

    # Process each problematic entry
    for row in problematic_rows:
        appid = row["appid"]
        current_name = row["steam_game_name"]
        found_name = None
        found_source = None

        # Phase 1: Try local game_details_cache
        cached_details = get_cached_game_details(appid)
        if (
            cached_details
            and cached_details.get("name")
            and not cached_details["name"].startswith("Unknown")
        ):
            found_name = cached_details["name"]
            found_source = "internal"
            logger.info(f"   [Internal] Found name for {appid}: '{found_name}'")

        # Phase 2: Try Steam Store API fallback if Phase 1 failed
        if not found_name:
            logger.info(f"   [External] Fetching Steam details for {appid}...")
            try:
                # fetch_game_details handles its own caching
                game_data = await fetch_game_details(appid, steam_api_manager)
                if game_data and game_data.get("name"):
                    found_name = game_data["name"]
                    found_source = "external"
                    logger.info(
                        f"   [External] Successfully fetched name for {appid}: '{found_name}'"
                    )
            except Exception as e:
                logger.warning(
                    f"   [External] Failed to fetch details for {appid}: {e}"
                )

        # Phase 2: Collect update if we found a name
        if found_name:
            updates_to_apply.append((found_name, appid, found_source))
        else:
            logger.warning(f"   ⚠️ Could not resolve name for AppID {appid}")
            failed_fixes += 1
            failed_entries.append((appid, current_name))

    # Phase 3: Batch update the database
    if updates_to_apply:
        try:
            with get_write_connection() as write_conn:
                write_cursor = write_conn.cursor()
                write_cursor.executemany(
                    """
                    UPDATE itad_price_cache
                    SET steam_game_name = ?
                    WHERE appid = ?
                """,
                    [(name, appid) for name, appid, _ in updates_to_apply],
                )
                write_conn.commit()
                write_cursor.close()

            # Count fixes by source only after successful commit
            for _, _, source in updates_to_apply:
                if source == "internal":
                    internal_fixes += 1
                else:
                    external_fixes += 1
                fixed_count += 1
        except sqlite3.Error as e:
            logger.error(f"   ❌ Batch database update failed: {e}")
            failed_fixes += len(updates_to_apply)

    # Summary
    print("\n" + "=" * 40)
    print("📊 CONTENT FIX SUMMARY:")
    print(f"   - Total checked     : {len(problematic_rows)}")
    print(f"   - Total fixed       : {fixed_count}")
    print(f"     - Internal fixes  : {internal_fixes}")
    print(f"     - External fixes  : {external_fixes}")
    print(f"   - Failed to resolve : {failed_fixes}")
    print("=" * 40 + "\n")

    # Interactive manual entry for failed entries
    if failed_entries:
        print(
            f"\n⚠️  {len(failed_entries)} entries could not be resolved automatically."
        )
        try:
            response = (
                input("Would you like to manually enter names for them? (y/n): ")
                .strip()
                .lower()
            )
        except EOFError:
            response = "n"

        if response == "y":
            manual_updates = []
            for appid, current_name in failed_entries:
                print(f"\n  AppID: {appid}")
                print(f"  Current name: {current_name or '(empty)'}")
                try:
                    manual_name = input(
                        "  Enter game name (or press Enter to skip): "
                    ).strip()
                except EOFError:
                    manual_name = ""

                if manual_name:
                    manual_updates.append((manual_name, appid))
                    print(f"  ✅ Will update to: '{manual_name}'")
                else:
                    print("  ⏭️  Skipped")

            # Apply manual updates
            if manual_updates:
                try:
                    with get_write_connection() as write_conn:
                        write_cursor = write_conn.cursor()
                        write_cursor.executemany(
                            """
                            UPDATE itad_price_cache
                            SET steam_game_name = ?
                            WHERE appid = ?
                        """,
                            manual_updates,
                        )
                        write_conn.commit()
                        write_cursor.close()

                    manual_fixes = len(manual_updates)
                    fixed_count += manual_fixes
                    failed_fixes -= manual_fixes

                    print(f"\n✅ Applied {manual_fixes} manual fixes.")
                except sqlite3.Error as e:
                    logger.error(f"   ❌ Manual update failed: {e}")

            # Final summary
            print("\n" + "=" * 40)
            print("📊 FINAL SUMMARY:")
            print(f"   - Total checked     : {len(problematic_rows)}")
            print(f"   - Total fixed       : {fixed_count}")
            print(f"     - Internal fixes  : {internal_fixes}")
            print(f"     - External fixes  : {external_fixes}")
            print(f"     - Manual fixes    : {manual_fixes}")
            print(f"   - Still unresolved  : {failed_fixes}")
            print("=" * 40 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(fix_missing_names())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}", exc_info=True)
        sys.exit(1)
