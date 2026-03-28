#!/usr/bin/env python3
"""
Database Content Fixer for FamilyBot

Identifies and attempts to fix missing or 'Unknown' game names across multiple tables
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
    logger.info("Starting itad_price_cache name fix...")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        try:
            # Find problematic entries in itad_price_cache
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
        return 0, 0, 0, []

    logger.info(
        f"🔍 Found {len(problematic_rows)} entries with missing or 'Unknown' names."
    )

    fixed_count = 0
    internal_fixes = 0
    external_fixes = 0
    failed_fixes = 0

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

    return fixed_count, internal_fixes, external_fixes, failed_entries


def check_game_details_cache():
    """Check game_details_cache for missing or problematic entries."""
    logger.info("Checking game_details_cache for missing info...")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        try:
            # Find entries with NULL or empty names
            cursor.execute("""
                SELECT appid, name, type
                FROM game_details_cache
                WHERE name IS NULL
                   OR name = ''
                   OR name LIKE 'Unknown%'
                   OR name LIKE 'App %'
            """)

            problematic_rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        conn.close()

    if not problematic_rows:
        logger.info("✅ No problematic entries found in game_details_cache.")
        return []

    logger.info(
        f"🔍 Found {len(problematic_rows)} entries with missing or problematic names."
    )
    return [(row["appid"], row["name"], row["type"]) for row in problematic_rows]


def check_family_library_cache():
    """Check family_library_cache for missing info."""
    logger.info("Checking family_library_cache for missing info...")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        try:
            # Find entries with NULL owner_steamids
            cursor.execute("""
                SELECT appid, owner_steamids, exclude_reason
                FROM family_library_cache
                WHERE owner_steamids IS NULL
                   OR owner_steamids = ''
            """)

            problematic_rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        conn.close()

    if not problematic_rows:
        logger.info("✅ No problematic entries found in family_library_cache.")
        return []

    logger.info(f"🔍 Found {len(problematic_rows)} entries with missing owner info.")
    return [
        (row["appid"], row["owner_steamids"], row["exclude_reason"])
        for row in problematic_rows
    ]


def check_steam_itad_mapping():
    """Check steam_itad_mapping for missing ITAD IDs."""
    logger.info("Checking steam_itad_mapping for missing info...")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        try:
            # Find entries with NULL or empty itad_id
            cursor.execute("""
                SELECT appid, itad_id
                FROM steam_itad_mapping
                WHERE itad_id IS NULL
                   OR itad_id = ''
            """)

            problematic_rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        conn.close()

    if not problematic_rows:
        logger.info("✅ No problematic entries found in steam_itad_mapping.")
        return []

    logger.info(f"🔍 Found {len(problematic_rows)} entries with missing ITAD IDs.")
    return [(row["appid"], row["itad_id"]) for row in problematic_rows]


async def fix_game_details_cache_names():
    """Fix missing names in game_details_cache by cross-referencing with itad_price_cache."""
    logger.info("Starting game_details_cache name fix...")

    problematic_rows = check_game_details_cache()
    if not problematic_rows:
        return 0, 0

    fixed_count = 0
    failed_count = 0
    updates_to_apply = []

    # Collect all appids and batch query once
    appids = [appid for appid, _, _ in problematic_rows]
    appid_name_mapping = {}

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        try:
            # Build placeholders for IN clause
            placeholders = ",".join("?" * len(appids))
            cursor.execute(
                f"SELECT appid, steam_game_name FROM itad_price_cache WHERE appid IN ({placeholders})",
                appids,
            )
            for row in cursor.fetchall():
                if row["steam_game_name"] and not row["steam_game_name"].startswith(
                    "Unknown"
                ):
                    appid_name_mapping[row["appid"]] = row["steam_game_name"]
        finally:
            cursor.close()
    finally:
        conn.close()

    for appid, current_name, game_type in problematic_rows:
        found_name = None

        # Try to get name from the pre-fetched mapping
        if appid in appid_name_mapping:
            found_name = appid_name_mapping[appid]
            logger.info(f"   [Cross-ref] Found name for {appid}: '{found_name}'")

        if found_name:
            updates_to_apply.append((found_name, appid))
        else:
            failed_count += 1

    # Apply updates
    if updates_to_apply:
        try:
            with get_write_connection() as write_conn:
                write_cursor = write_conn.cursor()
                write_cursor.executemany(
                    """
                    UPDATE game_details_cache
                    SET name = ?
                    WHERE appid = ?
                """,
                    updates_to_apply,
                )
                write_conn.commit()
                write_cursor.close()

            fixed_count = len(updates_to_apply)
        except sqlite3.Error as e:
            logger.error(f"   ❌ Batch update failed: {e}")
            failed_count += len(updates_to_apply)

    return fixed_count, failed_count


async def interactive_manual_entry(failed_entries, table_name="itad_price_cache"):
    """Interactive manual entry for failed entries."""
    if not failed_entries:
        return 0

    # Validate table_name against whitelist and map to correct column
    allowed_tables = {
        "itad_price_cache": "steam_game_name",
        "game_details_cache": "name",
    }
    if table_name not in allowed_tables:
        logger.error(f"   ❌ Invalid table name: {table_name}")
        return 0
    name_column = allowed_tables[table_name]

    print(f"\n⚠️  {len(failed_entries)} entries could not be resolved automatically.")
    try:
        response = (
            input("Would you like to manually enter names for them? (y/n): ")
            .strip()
            .lower()
        )
    except EOFError:
        response = "n"

    if response != "y":
        return 0

    manual_updates = []
    for appid, current_name in failed_entries:
        print(f"\n  AppID: {appid}")
        print(f"  Current name: {current_name or '(empty)'}")
        try:
            manual_name = input("  Enter game name (or press Enter to skip): ").strip()
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
                # Use validated table_name and name_column from the whitelist
                write_cursor.executemany(
                    f"""
                    UPDATE {table_name}
                    SET {name_column} = ?
                    WHERE appid = ?
                """,
                    manual_updates,
                )
                write_conn.commit()
                write_cursor.close()

            print(f"\n✅ Applied {len(manual_updates)} manual fixes.")
            return len(manual_updates)
        except sqlite3.Error as e:
            logger.error(f"   ❌ Manual update failed: {e}")

    return 0


async def main():
    """Main function to run all database checks and fixes."""
    print("=" * 50)
    print("🔧 FamilyBot Database Content Fixer")
    print("=" * 50)

    # Check all tables
    print("\n📊 Scanning database for missing information...\n")

    # 1. Check itad_price_cache
    print("1️⃣  Checking itad_price_cache...")
    (
        price_fixed,
        price_internal,
        price_external,
        price_failed,
    ) = await fix_missing_names()

    # 2. Check game_details_cache
    print("\n2️⃣  Checking game_details_cache...")
    details_problematic = check_game_details_cache()
    details_fixed, details_failed = 0, 0
    if details_problematic:
        print(f"   Found {len(details_problematic)} entries with missing names.")
        try:
            response = (
                input(
                    "   Attempt to fix by cross-referencing with itad_price_cache? (y/n): "
                )
                .strip()
                .lower()
            )
        except EOFError:
            response = "n"

        if response == "y":
            details_fixed, details_failed = await fix_game_details_cache_names()

    # 3. Check family_library_cache
    print("\n3️⃣  Checking family_library_cache...")
    family_problematic = check_family_library_cache()

    # 4. Check steam_itad_mapping
    print("\n4️⃣  Checking steam_itad_mapping...")
    mapping_problematic = check_steam_itad_mapping()

    # Handle manual entry before summary
    manual_count = 0
    if price_failed:
        manual_count = await interactive_manual_entry(price_failed, "itad_price_cache")

    # Summary
    print("\n" + "=" * 50)
    print("📊 DATABASE FIX SUMMARY")
    print("=" * 50)

    print("\n📝 itad_price_cache:")
    print(f"   - Fixed           : {price_fixed + manual_count}")
    print(f"     - Internal      : {price_internal}")
    print(f"     - External      : {price_external}")
    print(f"     - Manual         : {manual_count}")
    print(
        f"   - Still unresolved: {len(price_failed) - manual_count if price_failed else 0}"
    )

    print("\n📝 game_details_cache:")
    print(f"   - Problematic     : {len(details_problematic)}")
    print(f"   - Fixed           : {details_fixed}")
    print(f"   - Still missing   : {details_failed}")

    print("\n📝 family_library_cache:")
    print(f"   - Missing owners  : {len(family_problematic)}")
    if family_problematic:
        print("   (These may need manual investigation)")

    print("\n📝 steam_itad_mapping:")
    print(f"   - Missing ITAD IDs: {len(mapping_problematic)}")
    if mapping_problematic:
        print("   (Run 'just populate-prices' to resolve ITAD IDs)")

    print("\n" + "=" * 50)

    print("\n✅ Database check complete!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}", exc_info=True)
        sys.exit(1)
