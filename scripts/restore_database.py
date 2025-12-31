#!/usr/bin/env python3
"""
Database Restore Script for FamilyBot

This script allows restoring the database from a backup file.
It should only be run when the bot is offline.
"""

import logging
import os
import shutil
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("db_restore")

try:
    from familybot.config import PROJECT_ROOT
    from familybot.lib.database import DATABASE_FILE
except ImportError:
    print(
        "❌ Could not import familybot modules. Make sure you are in the project root."
    )
    sys.exit(1)

BACKUP_DIR = os.path.join(PROJECT_ROOT, "backups")


def list_backups() -> list:
    """Lists available database backups."""
    if not os.path.exists(BACKUP_DIR):
        logger.error(f"Backup directory not found: {BACKUP_DIR}")
        return []

    backups = []
    for f in os.listdir(BACKUP_DIR):
        if f.startswith("bot_data_") and f.endswith(".db"):
            full_path = os.path.join(BACKUP_DIR, f)
            backups.append(full_path)

    # Sort by modification time (newest first)
    backups.sort(key=os.path.getmtime, reverse=True)
    return backups


def restore_database():
    """Interactive script to restore the database from a backup."""
    logger.info("Starting database restore process...")
    logger.warning("🛑 Please ensure the bot is OFFLINE before proceeding.")

    available_backups = list_backups()
    if not available_backups:
        logger.error("No backups found to restore.")
        return False

    print("\nAvailable backups (newest first):")
    for i, backup_path in enumerate(available_backups):
        print(f"  [{i + 1}] {os.path.basename(backup_path)}")

    try:
        choice = input("\nEnter the number of the backup to restore (or 'q' to quit): ")
        if choice.lower() == "q":
            print("Restore cancelled.")
            return False

        choice_index = int(choice) - 1
        if not 0 <= choice_index < len(available_backups):
            raise ValueError("Invalid choice")

        backup_to_restore = available_backups[choice_index]

    except (ValueError, IndexError):
        logger.error("Invalid selection. Please enter a valid number.")
        return False

    print("\n" + "=" * 50)
    print("⚠️  WARNING: This will OVERWRITE the current database file.")
    print(f"    Current DB: {DATABASE_FILE}")
    print(f"    Restore from: {os.path.basename(backup_to_restore)}")
    print("=" * 50)

    confirm = input("Are you sure you want to proceed? (y/N): ").strip().lower()
    if confirm not in ["y", "yes"]:
        print("Restore cancelled.")
        return False

    try:
        # 1. Backup the current (potentially corrupted) database as a safety measure
        if os.path.exists(DATABASE_FILE):
            safety_backup_path = f"{DATABASE_FILE}.before_restore"
            shutil.copy2(DATABASE_FILE, safety_backup_path)
            logger.info(
                f"Safety backup of current database created at: {safety_backup_path}"
            )

        # 2. Perform the restore
        shutil.copy2(backup_to_restore, DATABASE_FILE)
        logger.info(
            f"✅ Database successfully restored from: {os.path.basename(backup_to_restore)}"
        )

        return True

    except Exception as e:
        logger.error(f"❌ Restore failed: {e}")
        return False


if __name__ == "__main__":
    success = restore_database()
    if success:
        print("\n🎉 Restore complete. You can now start the bot.")
        sys.exit(0)
    else:
        sys.exit(1)
