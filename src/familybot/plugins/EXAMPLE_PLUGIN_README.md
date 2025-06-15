# Example Plugin for FamilyBot

This example plugin demonstrates best practices for creating FamilyBot plugins. It serves as a comprehensive template and reference for developers who want to create their own plugins for the FamilyBot system.

## 📋 Features Demonstrated

### 🔧 **Core Plugin Structure**

- Proper imports and setup
- Extension class inheritance
- Plugin initialization and cleanup
- Setup function for bot registration

### 💬 **Command Implementation**

- Prefixed commands with help documentation
- Parameter validation and error handling
- Loading messages and user feedback
- Both public and admin-only commands

### 🗄️ **Database Operations**

- SQLite database integration
- Table creation and management
- CRUD operations with proper error handling
- Connection management and cleanup

### 📦 **Caching System**

- In-memory caching with expiration
- Cache hit/miss logic
- Automatic cleanup of expired entries
- Performance optimization

### 🌐 **API Integration**

- External API calls with error handling
- Rate limiting implementation
- Request/response processing
- JSON parsing and validation

### 📝 **Message Management**

- Discord message length limit handling
- Message truncation utility usage
- Proper formatting and structure
- User-friendly error messages

### ⚡ **Scheduled Tasks**

- Background task implementation
- Periodic cleanup operations
- Task lifecycle management
- Error handling in tasks

### 🔐 **Security & Permissions**

- Admin-only command restrictions
- DM-only command enforcement
- Input validation and sanitization
- Error reporting to administrators

## 🎮 Available Commands

### Public Commands

#### `!example_search QUERY`

- **Description**: Search for items using the example API
- **Usage**: `!example_search gaming news`
- **Features**:
  - API caching (15 minutes)
  - Rate limiting (2 seconds between calls)
  - Message truncation for long results
  - Comprehensive error handling

#### `!example_list`

- **Description**: List all items from the example database
- **Usage**: `!example_list`
- **Features**:
  - Database query with proper connection handling
  - Message truncation for large lists
  - Formatted output with item details

#### `!example_add "ITEM_NAME" "DESCRIPTION"`

- **Description**: Add an item to the example database
- **Usage**: `!example_add "Cool Game" "A really fun game to play"`
- **Features**:
  - Input validation
  - Database insertion with error handling
  - Success/failure feedback

### Admin Commands

#### `!example_admin`

- **Description**: Display plugin administration information
- **Usage**: `!example_admin` (DM only, admin only)
- **Features**:
  - Cache statistics
  - Database item count
  - Last API call timestamp
  - System health information

## 🏗️ Architecture Overview

### Class Structure

```python
class example_plugin(Extension):
    """Main plugin class inheriting from interactions.Extension"""
    
    # Constants
    API_RATE_LIMIT = 2.0  # Rate limiting configuration
    
    # Instance variables
    self.bot: FamilyBotClient          # Bot instance
    self._last_api_call: float         # Rate limiting tracker
    self._example_cache: Dict[str, Dict]  # In-memory cache
```

### Helper Methods

#### `_send_admin_dm(message: str)`

- Sends error notifications to the bot administrator
- Includes timestamp for debugging
- Handles DM sending failures gracefully

#### `_rate_limit_api()`

- Enforces minimum time between API calls
- Uses async sleep to prevent blocking
- Configurable rate limit constant

#### `_get_cached_data(key: str)` / `_set_cache_data(key: str, data: Dict)`

- Manages in-memory cache with expiration
- Automatic cleanup of expired entries
- Configurable cache duration

#### `_fetch_example_api_data(query: str)`

- Mock API integration with proper error handling
- Demonstrates request/response patterns
- Includes caching and rate limiting

#### `_get_database_items()` / `_add_database_item()`

- Database operations with connection management
- Proper error handling and logging
- Table creation and data manipulation

### Scheduled Tasks

#### `example_cleanup_task()`

- Runs every hour using `IntervalTrigger`
- Cleans up expired cache entries
- Removes old database records (30+ days)
- Comprehensive error handling

## 🛠️ Implementation Guidelines

### 1. **Error Handling Pattern**

```python
try:
    # Main operation logic
    result = await some_operation()
    
except SpecificException as e:
    logger.error(f"Specific error: {e}")
    await self._send_admin_dm(f"Error details: {e}")
    
except Exception as e:
    logger.critical(f"Unexpected error: {e}", exc_info=True)
    await self._send_admin_dm(f"Critical error: {e}")
```

### 2. **Command Structure Pattern**

```python
"""
[help]|command_name|description|!command_name ARGS|Additional help info
"""
@prefixed_command(name="command_name")
async def command_function(self, ctx: PrefixedContext, ...):
    # Parameter validation
    if not required_param:
        await ctx.send("❌ Error message with usage example")
        return
    
    # Loading message for long operations
    loading_message = await ctx.send("🔍 Processing...")
    
    try:
        # Main command logic
        result = await self.process_command()
        
        # Success response
        await loading_message.edit(content=result)
        
    except Exception as e:
        # Error handling
        await loading_message.edit(content="❌ Error occurred")
        await self._send_admin_dm(f"Command error: {e}")
```

### 3. **Database Operation Pattern**

```python
async def database_operation(self):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Database operations
        cursor.execute("SQL QUERY", (params,))
        conn.commit()
        
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        await self._send_admin_dm(f"DB error: {e}")
        
    finally:
        if conn:
            conn.close()
```

### 4. **Message Truncation Pattern**

```python
# For long lists that might exceed Discord limits
header = "📋 **Results:**\n\n"
entries = [f"• {item}" for item in items]
footer_template = "\n... and {count} more items!"

final_message = truncate_message_list(entries, header, footer_template)
await ctx.send(final_message)
```

## 🔧 Customization Guide

### Adding New Commands

1. Add help documentation comment above the command
2. Use `@prefixed_command(name="command_name")` decorator
3. Implement proper parameter validation
4. Add error handling and admin notifications
5. Use message truncation for potentially long outputs

### Database Integration

1. Create table schema in `_get_database_items()` or similar method
2. Use parameterized queries to prevent SQL injection
3. Always use try/finally blocks for connection cleanup
4. Log database operations for debugging

### API Integration

1. Implement rate limiting using `_rate_limit_api()`
2. Add caching to reduce API calls
3. Handle all common HTTP errors
4. Parse JSON responses safely

### Scheduled Tasks

1. Use `@Task.create(IntervalTrigger(...))` decorator
2. Start tasks in `on_startup()` event handler
3. Include comprehensive error handling
4. Log task execution for monitoring

## 📚 Dependencies

The example plugin uses these FamilyBot utilities:

- `familybot.lib.types.FamilyBotClient` - Bot client type
- `familybot.lib.types.DISCORD_MESSAGE_LIMIT` - Message length constant
- `familybot.lib.utils.truncate_message_list` - Message truncation utility
- `familybot.lib.database.get_db_connection` - Database connection helper
- `familybot.config.ADMIN_DISCORD_ID` - Admin user configuration

## 🚀 Getting Started

1. **Copy the example plugin** to create your own plugin
2. **Rename the class** and file to match your plugin's purpose
3. **Modify the commands** to implement your desired functionality
4. **Update the help documentation** to reflect your commands
5. **Test thoroughly** with proper error scenarios
6. **Add your plugin** to the bot's plugin loading system

## 💡 Best Practices Demonstrated

- ✅ Comprehensive error handling at all levels
- ✅ Proper logging with appropriate log levels
- ✅ Admin notification system for critical errors
- ✅ Rate limiting for external API calls
- ✅ Caching to improve performance
- ✅ Message truncation to handle Discord limits
- ✅ Input validation and sanitization
- ✅ Resource cleanup (database connections, cache)
- ✅ Scheduled maintenance tasks
- ✅ Type hints for better code maintainability
- ✅ Clear documentation and help text
- ✅ Separation of concerns (helper methods)

This example plugin serves as a complete reference implementation that you can adapt for your specific needs while maintaining the high standards of error handling, performance, and user experience expected in the FamilyBot ecosystem.
