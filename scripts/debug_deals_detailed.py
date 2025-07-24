import sqlite3
import json
from pathlib import Path


def debug_deals_detailed():
    """Detailed debug script to examine wishlist games and their pricing"""
    db_path = Path("bot_data.db")

    if not db_path.exists():
        print("Database not found!")
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=== DETAILED DEALS DEBUGGING ===\n")

    # 1. Check wishlist games that have price data
    print("1. Wishlist games with price data:")
    cursor.execute("""
        SELECT gdc.appid, gdc.name, gdc.price_data,
               json_extract(gdc.price_data, '$.discount_percent') as discount,
               json_extract(gdc.price_data, '$.final_formatted') as current_price,
               json_extract(gdc.price_data, '$.initial_formatted') as original_price
        FROM game_details_cache gdc
        WHERE gdc.appid IN (SELECT DISTINCT appid FROM wishlist_cache)
        AND gdc.price_data IS NOT NULL
        ORDER BY CAST(json_extract(gdc.price_data, '$.discount_percent') AS INTEGER) DESC
        LIMIT 20
    """)

    wishlist_games_with_prices = cursor.fetchall()
    if wishlist_games_with_prices:
        for game in wishlist_games_with_prices:
            print(f"App ID: {game['appid']}, Name: {game['name']}")
            print(
                f"  Discount: {game['discount']}%, Current: {game['current_price']}, Original: {game['original_price']}"
            )
    else:
        print("No wishlist games found with price data!")

    # 2. Check if any wishlist games have discounts at all
    print("\n2. Wishlist games with ANY discount:")
    cursor.execute("""
        SELECT gdc.appid, gdc.name,
               json_extract(gdc.price_data, '$.discount_percent') as discount,
               json_extract(gdc.price_data, '$.final_formatted') as current_price
        FROM game_details_cache gdc
        WHERE gdc.appid IN (SELECT DISTINCT appid FROM wishlist_cache)
        AND gdc.price_data IS NOT NULL
        AND CAST(json_extract(gdc.price_data, '$.discount_percent') AS INTEGER) > 0
        ORDER BY CAST(json_extract(gdc.price_data, '$.discount_percent') AS INTEGER) DESC
        LIMIT 10
    """)

    discounted_wishlist_games = cursor.fetchall()
    if discounted_wishlist_games:
        for game in discounted_wishlist_games:
            print(f"App ID: {game['appid']}, Name: {game['name']}")
            print(f"  Discount: {game['discount']}%, Current: {game['current_price']}")
    else:
        print("No wishlist games found with any discount!")

    # 3. Check sample of wishlist games without price data
    print("\n3. Sample wishlist games WITHOUT price data:")
    cursor.execute("""
        SELECT wc.appid, gdc.name
        FROM wishlist_cache wc
        LEFT JOIN game_details_cache gdc ON wc.appid = gdc.appid
        WHERE gdc.price_data IS NULL OR gdc.price_data = ''
        LIMIT 10
    """)

    games_without_prices = cursor.fetchall()
    if games_without_prices:
        for game in games_without_prices:
            print(f"App ID: {game['appid']}, Name: {game['name'] or 'Unknown'}")
    else:
        print("All wishlist games have price data!")

    # 4. Check total counts
    print("\n4. Summary counts:")

    cursor.execute("SELECT COUNT(*) FROM wishlist_cache")
    total_wishlist = cursor.fetchone()[0]
    print(f"Total wishlist entries: {total_wishlist}")

    cursor.execute("""
        SELECT COUNT(*) FROM wishlist_cache wc
        JOIN game_details_cache gdc ON wc.appid = gdc.appid
        WHERE gdc.price_data IS NOT NULL
    """)
    wishlist_with_prices = cursor.fetchone()[0]
    print(f"Wishlist games with price data: {wishlist_with_prices}")

    cursor.execute("""
        SELECT COUNT(*) FROM wishlist_cache wc
        JOIN game_details_cache gdc ON wc.appid = gdc.appid
        WHERE gdc.price_data IS NOT NULL
        AND CAST(json_extract(gdc.price_data, '$.discount_percent') AS INTEGER) > 0
    """)
    wishlist_with_discounts = cursor.fetchone()[0]
    print(f"Wishlist games with any discount: {wishlist_with_discounts}")

    cursor.execute("""
        SELECT COUNT(*) FROM wishlist_cache wc
        JOIN game_details_cache gdc ON wc.appid = gdc.appid
        WHERE gdc.price_data IS NOT NULL
        AND CAST(json_extract(gdc.price_data, '$.discount_percent') AS INTEGER) >= 30
    """)
    wishlist_with_good_discounts = cursor.fetchone()[0]
    print(f"Wishlist games with 30%+ discount: {wishlist_with_good_discounts}")

    conn.close()


if __name__ == "__main__":
    debug_deals_detailed()
