#!/usr/bin/env python3
"""Database Integrity Checker for FamilyBot.

This script performs a deep integrity check on the SQLite database
to identify corruption, malformed records, or consistency errors.
"""

import logging
import sqlite3
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("db_integrity")

try:
    from familybot.lib.database import DATABASE_FILE, get_db_connection
except ImportError:
    print("❌ Could not import familybot modules. Make sure you are in the project root.")
    sys.exit(1)


def _run_quick_check(cursor) -> bool:
    logger.info("Running PRAGMA quick_check...")
    cursor.execute("PRAGMA quick_check")
    quick_result = cursor.fetchone()[0]
    if quick_result != "ok":
        logger.error(f"Quick check failed: {quick_result}")
        return False
    logger.info("✅ Quick check passed.")
    return True


def _run_full_integrity_check(cursor) -> bool:
    logger.info("Running PRAGMA integrity_check (this may take a moment)...")
    cursor.execute("PRAGMA integrity_check")
    rows = cursor.fetchall()

    integrity_errors = [row[0] for row in rows if row[0] != "ok"]

    if integrity_errors:
        logger.error(f"❌ Integrity check failed with {len(integrity_errors)} errors:")
        for err in integrity_errors:
            logger.error(f"   - {err}")
        return False

    logger.info("✅ Full integrity check passed.")
    return True


def _run_foreign_key_check(cursor) -> bool:
    logger.info("Running PRAGMA foreign_key_check...")
    cursor.execute("PRAGMA foreign_key_check")
    fk_errors = cursor.fetchall()

    if fk_errors:
        logger.error(f"❌ Foreign key check failed with {len(fk_errors)} errors.")
        for err in fk_errors:
            # table_name, rowid, parent, fkid
            logger.error(f"   - Table: {err[0]}, RowID: {err[1]}, Parent: {err[2]}")
        return False

    logger.info("✅ Foreign key check passed.")
    return True


def _print_database_stats(cursor):
    logger.info("Gathering database statistics...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()

    print("\n📊 Database Statistics:")
    for table in tables:
        table_name = table[0]
        try:
            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')  # noqa: S608
            count = cursor.fetchone()[0]
            print(f"   - {table_name:<25}: {count:>5} rows")
        except sqlite3.Error:
            print(f"   - {table_name:<25}: (error reading count)")


def check_database_integrity():
    """Run SQLite integrity checks."""
    logger.info(f"Target Database: {DATABASE_FILE}")

    if not Path(DATABASE_FILE).exists():
        logger.error("Database file does not exist.")
        return False

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not _run_quick_check(cursor):
            return False

        if not _run_full_integrity_check(cursor):
            return False

        if not _run_foreign_key_check(cursor):
            return False

        _print_database_stats(cursor)

        return True

    except sqlite3.Error as e:
        logger.error(f"SQLite error during check: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    success = check_database_integrity()
    if success:
        print("\n🎉 Database is healthy!")
        sys.exit(0)
    else:
        print("\n⚠️  Database has integrity issues.")
        sys.exit(1)
