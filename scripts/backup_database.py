#!/usr/bin/env python3
"""
Database Backup Script for FamilyBot

Creates a timestamped backup of the SQLite database in the backups/ directory.
Automatically rotates backups to keep the directory clean.
"""

import logging
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

try:
    from familybot.lib.backup_manager import backup_database
except ImportError:
    print(
        "❌ Could not import familybot modules. Make sure you are in the project root."
    )
    sys.exit(1)

if __name__ == "__main__":
    success = backup_database()
    if success:
        sys.exit(0)
    else:
        sys.exit(1)
