import os
import shutil
from datetime import datetime

from familybot.config import PROJECT_ROOT
from familybot.lib.database import DATABASE_FILE
from familybot.lib.logging_config import get_logger

logger = get_logger(__name__)

BACKUP_DIR = os.path.join(PROJECT_ROOT, "backups")


def cleanup_old_backups(keep_count=10):
    """Keeps only the N most recent backups."""
    try:
        files = []
        if not os.path.exists(BACKUP_DIR):
            return

        for f in os.listdir(BACKUP_DIR):
            if f.startswith("bot_data_") and f.endswith(".db"):
                full_path = os.path.join(BACKUP_DIR, f)
                files.append(full_path)

        # Sort by modification time (newest first)
        files.sort(key=os.path.getmtime, reverse=True)

        if len(files) > keep_count:
            files_to_delete = files[keep_count:]
            for f in files_to_delete:
                os.remove(f)
                logger.info(f"🗑️ Removed old backup: {os.path.basename(f)}")

    except Exception as e:
        logger.warning(f"Error cleaning up old backups: {e}")


def backup_database() -> bool:
    """Creates a backup of the database file."""
    if not os.path.exists(DATABASE_FILE):
        logger.error(f"Database file not found at: {DATABASE_FILE}")
        return False

    # Ensure backup directory exists
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create backup directory: {e}")
        return False

    # Generate backup filename
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"bot_data_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)

    try:
        # Perform the copy
        shutil.copy2(DATABASE_FILE, backup_path)
        logger.info(f"✅ Database backed up successfully to: {backup_path}")

        # Clean up old backups
        cleanup_old_backups()

        return True
    except IOError as e:
        logger.error(f"❌ Failed to backup database: {e}")
        return False
