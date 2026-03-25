#!/usr/bin/env python3
"""Quick script to check price cache status in the database."""

import os
import sys
from datetime import UTC, datetime

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from familybot.lib.database import get_db_connection


def _print_game_details_cache(cursor, now):
    """Print game_details_cache table contents."""
    print("=" * 80)
    print("GAME DETAILS CACHE (Steam prices)")
    print("=" * 80)

    cursor.execute(
        """
        SELECT appid, name, permanent, cached_at, expires_at,
               CASE
                   WHEN permanent = 1 THEN 'PERMANENT (never expires)'
                   WHEN expires_at > ? THEN 'VALID'
                   ELSE 'EXPIRED'
               END as status
        FROM game_details_cache
        ORDER BY cached_at DESC
        LIMIT 20
    """,
        (now,),
    )

    rows = cursor.fetchall()
    if not rows:
        print("  No entries found in game_details_cache")
    else:
        print(f"  Showing {len(rows)} most recent entries:\n")
        print(
            f"  {'AppID':<12} {'Name':<30} {'Permanent':<10} {'Status':<20} {'Expires At'}"
        )
        print("  " + "-" * 95)
        for row in rows:
            appid = row[0]
            name = (row[1] or "Unknown")[:28]
            permanent = "YES" if row[2] else "NO"
            status = row[5]
            expires = row[4] or "Never"
            if expires != "Never":
                expires = expires[:19]
            print(f"  {appid:<12} {name:<30} {permanent:<10} {status:<20} {expires}")


def _print_itad_price_cache(cursor, now):
    """Print itad_price_cache table contents."""
    print("\n" + "=" * 80)
    print("ITAD PRICE CACHE (Historical lows)")
    print("=" * 80)

    cursor.execute(
        """
        SELECT appid, lowest_price_formatted, permanent, cached_at, expires_at,
               CASE
                   WHEN permanent = 1 THEN 'PERMANENT (never expires)'
                   WHEN expires_at > ? THEN 'VALID'
                   ELSE 'EXPIRED'
               END as status
        FROM itad_price_cache
        ORDER BY cached_at DESC
        LIMIT 20
    """,
        (now,),
    )

    rows = cursor.fetchall()
    if not rows:
        print("  No entries found in itad_price_cache")
    else:
        print(f"  Showing {len(rows)} most recent entries:\n")
        print(
            f"  {'AppID':<12} {'Price':<15} {'Permanent':<10} {'Status':<20} {'Expires At'}"
        )
        print("  " + "-" * 80)
        for row in rows:
            appid = row[0]
            price = row[1] or "N/A"
            permanent = "YES" if row[2] else "NO"
            status = row[5]
            expires = row[4] or "Never"
            if expires != "Never":
                expires = expires[:19]
            print(f"  {appid:<12} {price:<15} {permanent:<10} {status:<20} {expires}")


def _print_summary(cursor):
    """Print summary statistics for both cache tables."""
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    cursor.execute("SELECT COUNT(*) FROM game_details_cache")
    total_game = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM game_details_cache WHERE permanent = 1")
    permanent_game = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM game_details_cache WHERE permanent = 0")
    ttl_game = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM itad_price_cache")
    total_itad = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM itad_price_cache WHERE permanent = 1")
    permanent_itad = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM itad_price_cache WHERE permanent = 0")
    ttl_itad = cursor.fetchone()[0]

    print("\n  Game Details Cache:")
    print(f"    Total entries: {total_game}")
    print(f"    Permanent (never expires): {permanent_game}")
    print(f"    TTL-based (will expire): {ttl_game}")

    print("\n  ITAD Price Cache:")
    print(f"    Total entries: {total_itad}")
    print(f"    Permanent (never expires): {permanent_itad}")
    print(f"    TTL-based (will expire): {ttl_itad}")

    if permanent_game > 0:
        print(
            f"\n  ⚠️  WARNING: {permanent_game} game details entries are still marked as permanent!"
        )
        print("     These will need to be refreshed or will show stale prices.")
    else:
        print("\n  ✅ All game details entries use TTL-based expiration.")


def check_price_cache():
    """Check game_details_cache and itad_price_cache tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        _print_game_details_cache(cursor, now)
        _print_itad_price_cache(cursor, now)
        _print_summary(cursor)
    finally:
        conn.close()


if __name__ == "__main__":
    check_price_cache()
