#!/usr/bin/env python3
"""
FamilyBot JSON Database Importer

This script allows you to import JSON data into the FamilyBot database.
It can handle various types of data and will only add records that match existing users.

Usage:
    python scripts/json_database_importer.py --file data.json
    python scripts/json_database_importer.py --json '{"type": "user", "discord_id": "123", "steam_id": "456"}'
    python scripts/json_database_importer.py --stdin < data.json

Supported JSON formats:
1. User data: {"type": "user", "discord_id": "123456789", "steam_id": "76561198000000000"}
2. Family member: {"type": "family_member", "steam_id": "76561198000000000", "friendly_name": "John", "discord_id": "123456789"}
3. Saved game: {"type": "saved_game", "appid": "730", "detected_at": "2023-01-01T00:00:00Z"}
4. Game details: {"type": "game_details", "appid": "730", "name": "Counter-Strike 2", "type": "game", "is_free": true, ...}
5. Batch operations: {"type": "batch", "data": [{"type": "user", ...}, {"type": "family_member", ...}]}
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from familybot.lib.database import (cache_game_details, get_db_connection,
                                    init_db)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class JSONDatabaseImporter:
    """Handles importing JSON data into the FamilyBot database."""
    
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        """Initialize the importer."""
        self.dry_run = dry_run
        self.verbose = verbose
        self.stats = {
            'processed': 0,
            'added': 0,
            'skipped': 0,
            'errors': 0
        }
        
        if verbose:
            logger.setLevel(logging.DEBUG)
    
    def log_action(self, message: str, level: str = 'info'):
        """Log an action with appropriate level."""
        if level == 'debug' and self.verbose:
            logger.debug(message)
        elif level == 'info':
            logger.info(message)
        elif level == 'warning':
            logger.warning(message)
        elif level == 'error':
            logger.error(message)
    
    def get_existing_users(self) -> Dict[str, Any]:
        """Get all existing users from the database."""
        users: Dict[str, Any] = {'discord_ids': {}, 'steam_ids': {}}
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get users table
            cursor.execute("SELECT discord_id, steam_id FROM users")
            for row in cursor.fetchall():
                users['discord_ids'][row['discord_id']] = row['steam_id']
                users['steam_ids'][row['steam_id']] = row['discord_id']
            
            # Get family members
            cursor.execute("SELECT steam_id, friendly_name, discord_id FROM family_members")
            family_members = {}
            for row in cursor.fetchall():
                family_members[row['steam_id']] = {
                    'friendly_name': row['friendly_name'],
                    'discord_id': row['discord_id']
                }
            
            users['family_members'] = family_members
            conn.close()
            
            self.log_action(f"Loaded {len(users['discord_ids'])} users and {len(family_members)} family members", 'debug')
            
        except Exception as e:
            self.log_action(f"Error loading existing users: {e}", 'error')
        
        return users
    
    def validate_user_data(self, data: Dict[str, Any]) -> bool:
        """Validate user data structure."""
        required_fields = ['discord_id', 'steam_id']
        for field in required_fields:
            if field not in data:
                self.log_action(f"Missing required field '{field}' in user data", 'error')
                return False
        
        # Validate Discord ID format (should be numeric string)
        try:
            int(data['discord_id'])
        except ValueError:
            self.log_action(f"Invalid Discord ID format: {data['discord_id']}", 'error')
            return False
        
        # Validate Steam ID format (should be numeric string, typically 17 digits)
        try:
            steam_id = str(data['steam_id'])
            if len(steam_id) < 10:  # Basic length check
                self.log_action(f"Steam ID seems too short: {steam_id}", 'warning')
        except ValueError:
            self.log_action(f"Invalid Steam ID format: {data['steam_id']}", 'error')
            return False
        
        return True
    
    def validate_family_member_data(self, data: Dict[str, Any]) -> bool:
        """Validate family member data structure."""
        required_fields = ['steam_id', 'friendly_name']
        for field in required_fields:
            if field not in data:
                self.log_action(f"Missing required field '{field}' in family member data", 'error')
                return False
        
        return True
    
    def validate_saved_game_data(self, data: Dict[str, Any]) -> bool:
        """Validate saved game data structure."""
        if 'appid' not in data:
            self.log_action("Missing required field 'appid' in saved game data", 'error')
            return False
        
        return True
    
    def validate_game_details_data(self, data: Dict[str, Any]) -> bool:
        """Validate game details data structure."""
        required_fields = ['appid', 'name']
        for field in required_fields:
            if field not in data:
                self.log_action(f"Missing required field '{field}' in game details data", 'error')
                return False
        
        return True
    
    def import_user(self, data: Dict[str, Any], existing_users: Dict[str, Any]) -> bool:
        """Import a single user record."""
        if not self.validate_user_data(data):
            return False
        
        discord_id = str(data['discord_id'])
        steam_id = str(data['steam_id'])
        
        # Check if user already exists
        if discord_id in existing_users['discord_ids']:
            existing_steam_id = existing_users['discord_ids'][discord_id]
            if existing_steam_id == steam_id:
                self.log_action(f"User {discord_id} already exists with same Steam ID", 'debug')
                self.stats['skipped'] += 1
                return True
            else:
                self.log_action(f"User {discord_id} exists but with different Steam ID ({existing_steam_id} vs {steam_id})", 'warning')
                self.stats['skipped'] += 1
                return False
        
        if steam_id in existing_users['steam_ids']:
            existing_discord_id = existing_users['steam_ids'][steam_id]
            if existing_discord_id != discord_id:
                self.log_action(f"Steam ID {steam_id} already linked to different Discord ID ({existing_discord_id})", 'warning')
                self.stats['skipped'] += 1
                return False
        
        # Add the user
        if self.dry_run:
            self.log_action(f"[DRY RUN] Would add user: Discord {discord_id} -> Steam {steam_id}")
        else:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO users (discord_id, steam_id) VALUES (?, ?)",
                    (discord_id, steam_id)
                )
                conn.commit()
                conn.close()
                self.log_action(f"Added user: Discord {discord_id} -> Steam {steam_id}")
                
                # Update our tracking
                existing_users['discord_ids'][discord_id] = steam_id
                existing_users['steam_ids'][steam_id] = discord_id
                
            except Exception as e:
                self.log_action(f"Error adding user {discord_id}: {e}", 'error')
                return False
        
        self.stats['added'] += 1
        return True
    
    def import_family_member(self, data: Dict[str, Any], existing_users: Dict[str, Any]) -> bool:
        """Import a single family member record."""
        if not self.validate_family_member_data(data):
            return False
        
        steam_id = str(data['steam_id'])
        friendly_name = data['friendly_name']
        discord_id = data.get('discord_id')
        
        # Check if family member already exists
        if steam_id in existing_users['family_members']:
            existing = existing_users['family_members'][steam_id]
            if existing['friendly_name'] == friendly_name and existing['discord_id'] == discord_id:
                self.log_action(f"Family member {steam_id} ({friendly_name}) already exists", 'debug')
                self.stats['skipped'] += 1
                return True
        
        # Add the family member
        if self.dry_run:
            self.log_action(f"[DRY RUN] Would add family member: {friendly_name} (Steam {steam_id})")
        else:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO family_members (steam_id, friendly_name, discord_id) VALUES (?, ?, ?)",
                    (steam_id, friendly_name, discord_id)
                )
                conn.commit()
                conn.close()
                self.log_action(f"Added family member: {friendly_name} (Steam {steam_id})")
                
                # Update our tracking
                existing_users['family_members'][steam_id] = {
                    'friendly_name': friendly_name,
                    'discord_id': discord_id
                }
                
            except Exception as e:
                self.log_action(f"Error adding family member {steam_id}: {e}", 'error')
                return False
        
        self.stats['added'] += 1
        return True
    
    def import_saved_game(self, data: Dict[str, Any], existing_users: Dict[str, Any]) -> bool:
        """Import a saved game record."""
        if not self.validate_saved_game_data(data):
            return False
        
        appid = str(data['appid'])
        detected_at = data.get('detected_at', datetime.utcnow().isoformat() + 'Z')
        
        # Add the saved game
        if self.dry_run:
            self.log_action(f"[DRY RUN] Would add saved game: {appid}")
        else:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO saved_games (appid, detected_at) VALUES (?, ?)",
                    (appid, detected_at)
                )
                conn.commit()
                conn.close()
                self.log_action(f"Added saved game: {appid}")
                
            except Exception as e:
                self.log_action(f"Error adding saved game {appid}: {e}", 'error')
                return False
        
        self.stats['added'] += 1
        return True
    
    def import_game_details(self, data: Dict[str, Any], existing_users: Dict[str, Any]) -> bool:
        """Import game details using the existing cache system."""
        if not self.validate_game_details_data(data):
            return False
        
        appid = str(data['appid'])
        
        # Prepare game data for caching
        game_data = {
            'name': data.get('name'),
            'type': data.get('game_type', 'game'),
            'is_free': data.get('is_free', False),
            'categories': data.get('categories', []),
            'price_overview': data.get('price_overview')
        }
        
        # Add the game details
        if self.dry_run:
            self.log_action(f"[DRY RUN] Would cache game details: {appid} ({game_data['name']})")
        else:
            try:
                cache_game_details(appid, game_data, permanent=True)
                self.log_action(f"Cached game details: {appid} ({game_data['name']})")
                
            except Exception as e:
                self.log_action(f"Error caching game details {appid}: {e}", 'error')
                return False
        
        self.stats['added'] += 1
        return True
    
    def import_single_record(self, data: Dict[str, Any], existing_users: Dict[str, Any]) -> bool:
        """Import a single record based on its type."""
        self.stats['processed'] += 1
        
        record_type = data.get('type')
        if not record_type:
            self.log_action("Record missing 'type' field", 'error')
            self.stats['errors'] += 1
            return False
        
        success = False
        
        if record_type == 'user':
            success = self.import_user(data, existing_users)
        elif record_type == 'family_member':
            success = self.import_family_member(data, existing_users)
        elif record_type == 'saved_game':
            success = self.import_saved_game(data, existing_users)
        elif record_type == 'game_details':
            success = self.import_game_details(data, existing_users)
        else:
            self.log_action(f"Unknown record type: {record_type}", 'error')
            self.stats['errors'] += 1
            return False
        
        if not success:
            self.stats['errors'] += 1
        
        return success
    
    def import_json_data(self, json_data: Any) -> bool:
        """Import JSON data (can be single record or batch)."""
        existing_users = self.get_existing_users()
        
        if isinstance(json_data, dict):
            if json_data.get('type') == 'batch':
                # Handle batch import
                batch_data = json_data.get('data', [])
                if not isinstance(batch_data, list):
                    self.log_action("Batch data must be a list", 'error')
                    return False
                
                self.log_action(f"Processing batch of {len(batch_data)} records")
                success_count = 0
                
                for record in batch_data:
                    if self.import_single_record(record, existing_users):
                        success_count += 1
                
                self.log_action(f"Batch complete: {success_count}/{len(batch_data)} records processed successfully")
                return success_count > 0
            else:
                # Handle single record
                return self.import_single_record(json_data, existing_users)
        
        elif isinstance(json_data, list):
            # Handle list of records
            self.log_action(f"Processing list of {len(json_data)} records")
            success_count = 0
            
            for record in json_data:
                if self.import_single_record(record, existing_users):
                    success_count += 1
            
            self.log_action(f"List complete: {success_count}/{len(json_data)} records processed successfully")
            return success_count > 0
        
        else:
            self.log_action("JSON data must be an object or array", 'error')
            return False
    
    def print_stats(self):
        """Print import statistics."""
        print("\n" + "=" * 50)
        print("📊 Import Statistics")
        print("=" * 50)
        print(f"📝 Records processed: {self.stats['processed']}")
        print(f"✅ Records added: {self.stats['added']}")
        print(f"⏭️  Records skipped: {self.stats['skipped']}")
        print(f"❌ Errors: {self.stats['errors']}")
        
        if self.dry_run:
            print("\n🔍 DRY RUN MODE - No changes were made to the database")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Import JSON data into FamilyBot database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--file", "-f", help="JSON file to import")
    input_group.add_argument("--json", "-j", help="JSON string to import")
    input_group.add_argument("--stdin", action="store_true", help="Read JSON from stdin")
    
    # Options
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    print("🚀 FamilyBot JSON Database Importer")
    print("=" * 50)
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
    
    # Initialize database
    try:
        init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        return 1
    
    # Load JSON data
    json_data = None
    try:
        if args.file:
            print(f"📁 Loading JSON from file: {args.file}")
            with open(args.file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        elif args.json:
            print("📝 Parsing JSON from command line")
            json_data = json.loads(args.json)
        elif args.stdin:
            print("📥 Reading JSON from stdin")
            json_data = json.load(sys.stdin)
    
    except FileNotFoundError:
        print(f"❌ File not found: {args.file}")
        return 1
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error loading JSON: {e}")
        return 1
    
    # Import data
    importer = JSONDatabaseImporter(dry_run=args.dry_run, verbose=args.verbose)
    
    try:
        success = importer.import_json_data(json_data)
        importer.print_stats()
        
        if success:
            print("\n🎉 Import completed successfully!")
            return 0
        else:
            print("\n❌ Import failed or no records were processed")
            return 1
    
    except Exception as e:
        print(f"\n❌ Unexpected error during import: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
