import sqlite3
import json
from pathlib import Path


def debug_deals():
    """Debug script to examine price data and deal detection logic"""
    db_path = Path("bot_data.db")

    if not db_path.exists():
        print("Database not found!")
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=== DEBUGGING DEALS DETECTION ===\n")

    # 1. Check game_details_cache structure and sample data
    print("1. Checking game_details_cache structure:")
    cursor.execute("PRAGMA table_info(game_details_cache)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"   - {col['name']}: {col['type']}")

    print("\n2. Sample game_details_cache entries with price data:")
    cursor.execute("""
        SELECT appid, name, price_data
        FROM game_details_cache
        WHERE price_data IS NOT NULL AND price_data != ''
        LIMIT 5
    """)

    games_with_prices = cursor.fetchall()
    for game in games_with_prices:
        print(f"\nApp ID: {game['appid']}")
        print(f"Name: {game['name']}")
        if game["price_data"]:
            price_data = json.loads(game["price_data"])
            print(f"Price Data: {price_data}")

    # 3. Check itad_price_cache
    print("\n3. Checking itad_price_cache structure:")
    cursor.execute("PRAGMA table_info(itad_price_cache)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"   - {col['name']}: {col['type']}")

    print("\n4. Sample itad_price_cache entries:")
    cursor.execute("SELECT * FROM itad_price_cache LIMIT 5")
    itad_prices = cursor.fetchall()
    for price in itad_prices:
        print(f"App ID: {price['appid']}, Lowest Price: {price['lowest_price']}")

    # 5. Check for games with discounts
    print("\n5. Games with current discounts:")
    cursor.execute("""
        SELECT appid, name,
               json_extract(price_data, '$.discount_percent') as discount,
               json_extract(price_data, '$.final_formatted') as current_price,
               json_extract(price_data, '$.initial_formatted') as original_price
        FROM game_details_cache
        WHERE price_data IS NOT NULL
        AND CAST(json_extract(price_data, '$.discount_percent') AS INTEGER) > 0
        LIMIT 10
    """)

    discounted_games = cursor.fetchall()
    if discounted_games:
        for game in discounted_games:
            print(f"App ID: {game['appid']}, Name: {game['name']}")
            print(
                f"  Discount: {game['discount']}%, Current: {game['current_price']}, Original: {game['original_price']}"
            )
    else:
        print("No games with discounts found in cache!")

    # 6. Check wishlist data
    print("\n6. Checking wishlist_cache:")
    cursor.execute("SELECT COUNT(*) as total FROM wishlist_cache")
    wishlist_count = cursor.fetchone()["total"]
    print(f"Total wishlist entries: {wishlist_count}")

    cursor.execute(
        "SELECT steam_id, COUNT(*) as game_count FROM wishlist_cache GROUP BY steam_id"
    )
    wishlist_by_user = cursor.fetchall()
    for user in wishlist_by_user:
        print(f"  Steam ID {user['steam_id']}: {user['game_count']} games")

    # 7. Check for games that should qualify for deals
    print("\n7. Potential deal candidates (discount >= 30%):")
    cursor.execute("""
        SELECT gdc.appid,
               gdc.name,
               json_extract(gdc.price_data, '$.discount_percent') as discount,
               json_extract(gdc.price_data, '$.final_formatted') as current_price,
               ipc.lowest_price
        FROM game_details_cache gdc
        LEFT JOIN itad_price_cache ipc ON gdc.appid = ipc.appid
        WHERE gdc.price_data IS NOT NULL
        AND CAST(json_extract(gdc.price_data, '$.discount_percent') AS INTEGER) >= 30
        AND gdc.appid IN (SELECT DISTINCT appid FROM wishlist_cache)
        LIMIT 10
    """)

    deal_candidates = cursor.fetchall()
    if deal_candidates:
        for game in deal_candidates:
            print(f"App ID: {game['appid']}, Name: {game['name']}")
            print(
                f"  Discount: {game['discount']}%, Current: {game['current_price']}, Historical Low: {game['lowest_price']}"
            )
    else:
        print("No deal candidates found!")

    conn.close()


if __name__ == "__main__":
    debug_deals()
