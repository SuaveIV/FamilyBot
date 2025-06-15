# In src/familybot/plugins/example_plugin.py

"""
Example Plugin for FamilyBot

This plugin demonstrates best practices for creating FamilyBot plugins, including:
- Proper imports and setup
- Command structure with help documentation
- Database operations with caching
- Error handling and admin notifications
- Message truncation for long lists
- Rate limiting for API calls
- Scheduled tasks
- Both public and admin-only commands
"""

from interactions import Extension, listen, Task, IntervalTrigger
from interactions.ext.prefixed_commands import prefixed_command, PrefixedContext
import requests
import json
import logging
import sqlite3
import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Import FamilyBot utilities and types
from familybot.config import ADMIN_DISCORD_ID
from familybot.lib.types import FamilyBotClient, DISCORD_MESSAGE_LIMIT
from familybot.lib.utils import truncate_message_list, ProgressTracker
from familybot.lib.database import get_db_connection

# Setup logging for this specific module
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class example_plugin(Extension):
    """
    Example plugin demonstrating FamilyBot plugin development best practices.
    """
    
    # Rate limiting constants
    API_RATE_LIMIT = 2.0  # Minimum seconds between API calls
    
    def __init__(self, bot: FamilyBotClient):
        self.bot: FamilyBotClient = bot
        self._last_api_call = 0.0
        self._example_cache: Dict[str, Dict] = {}
        logger.info("Example Plugin loaded")

    async def _send_admin_dm(self, message: str) -> None:
        """Helper to send error/warning messages to the bot admin via DM."""
        try:
            admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
            if admin_user:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await admin_user.send(f"Example Plugin Error ({now_str}): {message}")
        except Exception as e:
            logger.error(f"Failed to send DM to admin {ADMIN_DISCORD_ID}: {e}")

    async def _rate_limit_api(self) -> None:
        """Enforce rate limiting for API calls."""
        current_time = time.time()
        time_since_last_call = current_time - self._last_api_call
        
        if time_since_last_call < self.API_RATE_LIMIT:
            sleep_time = self.API_RATE_LIMIT - time_since_last_call
            logger.debug(f"Rate limiting API call, sleeping for {sleep_time:.2f} seconds")
            await asyncio.sleep(sleep_time)
        
        self._last_api_call = time.time()

    async def _get_cached_data(self, key: str) -> Optional[Dict]:
        """Get cached data if it exists and is not expired."""
        if key in self._example_cache:
            cache_entry = self._example_cache[key]
            if datetime.now() < cache_entry['expires']:
                logger.debug(f"Using cached data for key: {key}")
                return cache_entry['data']
            else:
                # Remove expired cache
                del self._example_cache[key]
                logger.debug(f"Removed expired cache for key: {key}")
        return None

    async def _set_cache_data(self, key: str, data: Dict, cache_minutes: int = 30) -> None:
        """Cache data with expiration time."""
        expires = datetime.now() + timedelta(minutes=cache_minutes)
        self._example_cache[key] = {
            'data': data,
            'expires': expires
        }
        logger.debug(f"Cached data for key: {key} (expires in {cache_minutes} minutes)")

    async def _fetch_example_api_data(self, query: str) -> Optional[Dict]:
        """
        Example of fetching data from an external API with proper error handling.
        This is a mock function - replace with actual API calls as needed.
        """
        try:
            # Check cache first
            cached_data = await self._get_cached_data(f"api_{query}")
            if cached_data:
                return cached_data

            # Apply rate limiting
            await self._rate_limit_api()
            
            # Mock API call (replace with actual API)
            logger.info(f"Fetching data from API for query: {query}")
            
            # Simulate API response
            mock_data = {
                'query': query,
                'results': [
                    f"Result 1 for {query}",
                    f"Result 2 for {query}",
                    f"Result 3 for {query}"
                ],
                'timestamp': datetime.now().isoformat()
            }
            
            # Cache the results
            await self._set_cache_data(f"api_{query}", mock_data, cache_minutes=15)
            
            return mock_data

        except requests.exceptions.RequestException as e:
            logger.error(f"API request error for query '{query}': {e}")
            await self._send_admin_dm(f"API error for query '{query}': {e}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for query '{query}': {e}")
            await self._send_admin_dm(f"JSON error for query '{query}': {e}")
        except Exception as e:
            logger.critical(f"Unexpected error fetching data for '{query}': {e}", exc_info=True)
            await self._send_admin_dm(f"Critical error for query '{query}': {e}")
        
        return None

    async def _get_database_items(self) -> List[Dict]:
        """Example of database operations with proper error handling."""
        items = []
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Create example table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS example_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Fetch items
            cursor.execute("SELECT id, name, description, created_at FROM example_items ORDER BY created_at DESC")
            for row in cursor.fetchall():
                items.append({
                    'id': row['id'],
                    'name': row['name'],
                    'description': row['description'],
                    'created_at': row['created_at']
                })
            
            logger.debug(f"Retrieved {len(items)} items from database")
            
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            await self._send_admin_dm(f"Database error: {e}")
        finally:
            if conn:
                conn.close()
        
        return items

    async def _add_database_item(self, name: str, description: Optional[str] = None) -> bool:
        """Add an item to the database."""
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "INSERT INTO example_items (name, description) VALUES (?, ?)",
                (name, description)
            )
            conn.commit()
            logger.info(f"Added item to database: {name}")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Error adding item to database: {e}")
            await self._send_admin_dm(f"Database error adding item: {e}")
            return False
        finally:
            if conn:
                conn.close()

    """
    [help]|example_search|search for items using the example API|!example_search QUERY|This command demonstrates API calls, caching, and message truncation. ***This command can be used in bot DM***
    """
    @prefixed_command(name="example_search")
    async def example_search_command(self, ctx: PrefixedContext, *, query: Optional[str] = None):
        if not query:
            await ctx.send("❌ **Missing query!**\n\n**Usage:** `!example_search YOUR_QUERY`\n**Example:** `!example_search gaming news`")
            return

        loading_message = await ctx.send(f"🔍 Searching for: {query}...")

        try:
            # Fetch data from API
            api_data = await self._fetch_example_api_data(query)
            
            if not api_data:
                await loading_message.edit(content="❌ Failed to fetch search results. Please try again later.")
                return

            # Build results list
            results = api_data.get('results', [])
            if not results:
                await loading_message.edit(content=f"No results found for: {query}")
                return

            # Use truncation utility for long result lists
            header = f"🔍 **Search Results for '{query}':**\n\n"
            result_entries = [f"• {result}" for result in results]
            footer_template = "\n... and {count} more results!"
            
            final_message = truncate_message_list(result_entries, header, footer_template)
            await loading_message.edit(content=final_message)

        except Exception as e:
            logger.critical(f"Unexpected error in example_search_command: {e}", exc_info=True)
            await loading_message.edit(content="❌ An unexpected error occurred during search.")
            await self._send_admin_dm(f"Critical error in example_search: {e}")

    """
    [help]|example_list|list all items from the example database|!example_list|Shows all items stored in the example database with proper truncation. ***This command can be used in bot DM***
    """
    @prefixed_command(name="example_list")
    async def example_list_command(self, ctx: PrefixedContext):
        loading_message = await ctx.send("📋 Loading items from database...")

        try:
            # Get items from database
            items = await self._get_database_items()
            
            if not items:
                await loading_message.edit(content="📋 No items found in the database.")
                return

            # Format items for display
            header = f"📋 **Database Items ({len(items)} total):**\n\n"
            item_entries = []
            
            for item in items:
                entry = f"**{item['name']}**"
                if item['description']:
                    entry += f" - {item['description']}"
                entry += f" _(ID: {item['id']})_"
                item_entries.append(entry)

            # Use truncation utility
            footer_template = "\n... and {count} more items!"
            final_message = truncate_message_list(item_entries, header, footer_template)
            
            await loading_message.edit(content=final_message)

        except Exception as e:
            logger.critical(f"Unexpected error in example_list_command: {e}", exc_info=True)
            await loading_message.edit(content="❌ An error occurred while loading items.")
            await self._send_admin_dm(f"Critical error in example_list: {e}")

    """
    [help]|example_add|add an item to the example database|!example_add "ITEM_NAME" "DESCRIPTION"|Adds a new item to the database. Use quotes for multi-word names/descriptions. ***This command can be used in bot DM***
    """
    @prefixed_command(name="example_add")
    async def example_add_command(self, ctx: PrefixedContext, name: Optional[str] = None, description: Optional[str] = None):
        if not name:
            await ctx.send("❌ **Missing item name!**\n\n**Usage:** `!example_add \"ITEM_NAME\" \"DESCRIPTION\"`\n**Example:** `!example_add \"Cool Game\" \"A really fun game to play\"`")
            return

        try:
            success = await self._add_database_item(name, description)
            
            if success:
                response = f"✅ **Item added successfully!**\n**Name:** {name}"
                if description:
                    response += f"\n**Description:** {description}"
                await ctx.send(response)
            else:
                await ctx.send("❌ Failed to add item to database. Please try again.")

        except Exception as e:
            logger.critical(f"Unexpected error in example_add_command: {e}", exc_info=True)
            await ctx.send("❌ An unexpected error occurred while adding the item.")
            await self._send_admin_dm(f"Critical error in example_add: {e}")

    @prefixed_command(name="example_admin")
    async def example_admin_command(self, ctx: PrefixedContext):
        """Admin-only command example."""
        if str(ctx.author_id) != str(ADMIN_DISCORD_ID) or ctx.guild is not None:
            await ctx.send("❌ You do not have permission to use this command, or it must be used in DMs.")
            return

        try:
            # Example admin functionality
            cache_size = len(self._example_cache)
            db_items = await self._get_database_items()
            
            admin_info = f"🔧 **Example Plugin Admin Info:**\n"
            admin_info += f"📊 **Cache entries:** {cache_size}\n"
            admin_info += f"🗄️ **Database items:** {len(db_items)}\n"
            admin_info += f"⏰ **Last API call:** {datetime.fromtimestamp(self._last_api_call).strftime('%H:%M:%S') if self._last_api_call else 'Never'}\n"
            
            await ctx.send(admin_info)

        except Exception as e:
            logger.critical(f"Unexpected error in example_admin_command: {e}", exc_info=True)
            await ctx.send("❌ An error occurred while fetching admin info.")
            await self._send_admin_dm(f"Critical error in example_admin: {e}")

    @Task.create(IntervalTrigger(hours=1))
    async def example_cleanup_task(self):
        """Example scheduled task that runs every hour."""
        logger.info("Running example cleanup task...")
        
        try:
            # Clean up expired cache entries
            expired_keys = []
            for key, cache_entry in self._example_cache.items():
                if datetime.now() >= cache_entry['expires']:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._example_cache[key]
            
            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
            
            # Example: Clean up old database entries (older than 30 days)
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Delete items older than 30 days
                cutoff_date = datetime.now() - timedelta(days=30)
                cursor.execute(
                    "DELETE FROM example_items WHERE created_at < ?",
                    (cutoff_date.isoformat(),)
                )
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old database entries")
                    
            except sqlite3.Error as e:
                logger.error(f"Database cleanup error: {e}")
            finally:
                if conn:
                    conn.close()

        except Exception as e:
            logger.critical(f"Error in example cleanup task: {e}", exc_info=True)
            await self._send_admin_dm(f"Error in example cleanup task: {e}")

    @listen()
    async def on_startup(self):
        """Initialize the plugin when the bot starts."""
        self.example_cleanup_task.start()
        logger.info("--Example Plugin tasks started")


def setup(bot):
    """Setup function called by the bot to load this plugin."""
    example_plugin(bot)
