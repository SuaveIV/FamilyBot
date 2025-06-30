import os
import sqlite3
from pathlib import Path

# Assuming PROJECT_ROOT is the current working directory as per environment_details
PROJECT_ROOT = Path(os.getcwd())
DATABASE_FILE = PROJECT_ROOT / "bot_data.db"

def inspect_database():
    print(f"Attempting to inspect database at: {DATABASE_FILE}")
    if not DATABASE_FILE.exists():
        print(f"Error: Database file not found at {DATABASE_FILE}")
        return

    conn = None
    try:
        conn = sqlite3.connect(str(DATABASE_FILE))
        cursor = conn.cursor()

        # Get list of all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            print("No tables found in the database.")
            return

        print("\nTables and Row Counts:")
        for table in tables:
            table_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            row_count = cursor.fetchone()[0]
            print(f"- {table_name}: {row_count} rows")

    except sqlite3.Error as e:
        print(f"Database error during inspection: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    inspect_database()
