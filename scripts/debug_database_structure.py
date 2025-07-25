import sqlite3
from pathlib import Path


def debug_database_structure():
    """Debug script to investigate database structure and content"""
    db_path = Path("bot_data.db")

    if not db_path.exists():
        print("Database not found!")
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=== INVESTIGATING DATABASE STRUCTURE ===\n")

    # Check what's actually in game_details_cache
    cursor.execute("SELECT COUNT(*) FROM game_details_cache")
    total_games = cursor.fetchone()[0]
    print(f"Total games in game_details_cache: {total_games}")

    # Check games with price_data
    cursor.execute(
        "SELECT COUNT(*) FROM game_details_cache WHERE price_data IS NOT NULL AND price_data != ''"
    )
    games_with_price_data = cursor.fetchone()[0]
    print(f"Games with price_data: {games_with_price_data}")

    # Check games with price_overview in price_data
    cursor.execute(
        "SELECT COUNT(*) FROM game_details_cache WHERE json_extract(price_data, '$.price_overview') IS NOT NULL"
    )
    games_with_price_overview = cursor.fetchone()[0]
    print(f"Games with price_overview in price_data: {games_with_price_overview}")

    # Sample a few games to see their structure
    cursor.execute("SELECT appid, name, price_data FROM game_details_cache LIMIT 5")
    sample_games = cursor.fetchall()
    print("\nSample games:")
    for game in sample_games:
        has_price_data = bool(game["price_data"])
        print(
            f"  App ID: {game['appid']}, Name: {game['name']}, Has price_data: {has_price_data}"
        )
        if has_price_data:
            print(f"    Price data preview: {str(game['price_data'])[:100]}...")

    # Check if any wishlist games are in the cache
    cursor.execute("""
        SELECT COUNT(*) FROM game_details_cache gdc
        WHERE gdc.appid IN (SELECT DISTINCT appid FROM wishlist_cache)
    """)
    wishlist_games_in_cache = cursor.fetchone()[0]
    print(f"\nWishlist games in game_details_cache: {wishlist_games_in_cache}")

    # Check specific wishlist games
    cursor.execute("""
        SELECT gdc.appid, gdc.name,
               CASE WHEN gdc.price_data IS NOT NULL AND gdc.price_data != '' THEN 'YES' ELSE 'NO' END as has_price_data
        FROM game_details_cache gdc
        WHERE gdc.appid IN (SELECT DISTINCT appid FROM wishlist_cache)
        LIMIT 10
    """)
    wishlist_sample = cursor.fetchall()
    print("\nSample wishlist games in cache:")
    for game in wishlist_sample:
        print(
            f"  App ID: {game['appid']}, Name: {game['name']}, Has price_data: {game['has_price_data']}"
        )

    # Check the database schema for game_details_cache
    cursor.execute("PRAGMA table_info(game_details_cache)")
    schema = cursor.fetchall()
    print("\nGame details cache schema:")
    for column in schema:
        print(f"  {column['name']}: {column['type']}")

    conn.close()


if __name__ == "__main__":
    debug_database_structure()
