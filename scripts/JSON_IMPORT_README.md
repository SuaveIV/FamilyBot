# FamilyBot JSON Import Tools

This directory contains tools for importing JSON data into the FamilyBot database, including support for raw Steamworks API responses.

## Scripts Overview

### 1. `json_database_importer.py`

Main script for importing structured JSON data into the FamilyBot database.

### 2. `steamworks_json_converter.py`

Converter script that transforms raw Steamworks API responses into the format expected by the importer.

### 3. Example Files

- `example_import.json` - Example of properly formatted import data
- `example_steamworks_owned_games.json` - Example Steamworks GetOwnedGames API response

## Quick Start

### Import Custom JSON Data

```bash
# Import from file
python scripts/json_database_importer.py --file data.json

# Import from command line
python scripts/json_database_importer.py --json '{"type": "user", "discord_id": "123", "steam_id": "456"}'

# Dry run to see what would be imported
python scripts/json_database_importer.py --file data.json --dry-run
```

### Convert and Import Steamworks Data

```bash
# Step 1: Convert Steamworks API response
python scripts/steamworks_json_converter.py \
  --api-type owned_games \
  --steam-id "76561198000000000" \
  --file steamworks_response.json \
  --output converted_data.json

# Step 2: Import converted data
python scripts/json_database_importer.py --file converted_data.json
```

### One-liner for Steamworks Data

```bash
# Convert and import in one command
python scripts/steamworks_json_converter.py \
  --api-type owned_games \
  --steam-id "76561198000000000" \
  --file steamworks_response.json | \
python scripts/json_database_importer.py --stdin
```

## Supported Data Types

### User Records

Links Discord users to Steam accounts.

```json
{
    "type": "user",
    "discord_id": "123456789012345678",
    "steam_id": "76561198000000000"
}
```

### Family Members

Adds family members to the database.

```json
{
    "type": "family_member",
    "steam_id": "76561198000000000",
    "friendly_name": "John Doe",
    "discord_id": "123456789012345678"
}
```

### Saved Games

Records games that have been detected/saved.

```json
{
    "type": "saved_game",
    "appid": "730",
    "detected_at": "2023-12-01T10:30:00Z"
}
```

### Game Details

Caches detailed game information.

```json
{
    "type": "game_details",
    "appid": "440",
    "name": "Team Fortress 2",
    "game_type": "game",
    "is_free": true,
    "categories": [{ "id": 1, "description": "Multi-player" }],
    "price_overview": null
}
```

### Batch Operations

Import multiple records at once.

```json
{
    "type": "batch",
    "data": [
        { "type": "user", "discord_id": "123", "steam_id": "456" },
        { "type": "family_member", "steam_id": "789", "friendly_name": "Jane" }
    ]
}
```

## Steamworks API Support

The converter supports these Steamworks API endpoints:

### GetOwnedGames (`owned_games`)

```bash
python scripts/steamworks_json_converter.py \
  --api-type owned_games \
  --steam-id "76561198000000000" \
  --file owned_games_response.json
```

### GetPlayerSummaries (`player_summaries`)

```bash
python scripts/steamworks_json_converter.py \
  --api-type player_summaries \
  --file player_summaries_response.json
```

### GetWishlist (`wishlist`)

```bash
python scripts/steamworks_json_converter.py \
  --api-type wishlist \
  --steam-id "76561198000000000" \
  --file wishlist_response.json
```

### Steam Store API (`app_details`)

```bash
python scripts/steamworks_json_converter.py \
  --api-type app_details \
  --file app_details_response.json
```

### GetSharedLibraryApps (`family_library`)

```bash
python scripts/steamworks_json_converter.py \
  --api-type family_library \
  --file family_library_response.json
```

## Command Line Options

### JSON Database Importer

```shell
--file, -f          JSON file to import
--json, -j          JSON string to import
--stdin             Read JSON from stdin
--dry-run, -n       Show what would be done without making changes
--verbose, -v       Enable verbose logging
```

### Steamworks JSON Converter

```shell
--file, -f          JSON file to convert
--json, -j          JSON string to convert
--stdin             Read JSON from stdin
--api-type, -t      Type of Steamworks API response (required)
--steam-id, -s      Steam ID (required for some API types)
--output, -o        Output file (default: stdout)
--pretty, -p        Pretty print JSON output
```

## Usage Examples

### Example 1: Import User Data

```bash
# Create a simple user mapping
echo '{"type": "user", "discord_id": "123456789", "steam_id": "76561198000000000"}' | \
python scripts/json_database_importer.py --stdin --verbose
```

### Example 2: Convert Steamworks Owned Games

```bash
# Convert owned games API response
python scripts/steamworks_json_converter.py \
  --api-type owned_games \
  --steam-id "76561198000000000" \
  --file scripts/example_steamworks_owned_games.json \
  --pretty
```

### Example 3: Batch Import with Dry Run

```bash
# Test import without making changes
python scripts/json_database_importer.py \
  --file scripts/example_import.json \
  --dry-run \
  --verbose
```

### Example 4: Pipeline Processing

```bash
# Fetch from API, convert, and import
curl "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key=$API_KEY&steamid=$STEAM_ID&include_appinfo=1" | \
python scripts/steamworks_json_converter.py \
  --api-type owned_games \
  --steam-id "$STEAM_ID" \
  --stdin | \
python scripts/json_database_importer.py --stdin
```

## Data Validation

The importer performs validation on all input data:

- **Discord IDs**: Must be numeric strings
- **Steam IDs**: Must be numeric strings (basic length check)
- **App IDs**: Must be present for game-related records
- **Required Fields**: All required fields must be present
- **Duplicate Detection**: Prevents duplicate entries

## Error Handling

Both scripts provide detailed error messages and logging:

- **Validation Errors**: Clear messages about missing or invalid fields
- **Database Errors**: Information about database connection or query issues
- **JSON Errors**: Detailed parsing error messages
- **API Conversion Errors**: Specific errors for each API type

## Safety Features

- **Dry Run Mode**: Test imports without making database changes
- **Duplicate Prevention**: Skips records that already exist
- **Transaction Safety**: Database operations are committed safely
- **Verbose Logging**: Detailed information about what's happening

## Integration with FamilyBot

These tools integrate seamlessly with the existing FamilyBot database structure:

- Uses existing database connection functions
- Leverages existing caching mechanisms
- Follows established data validation patterns
- Maintains compatibility with existing bot functionality

## Troubleshooting

### Common Issues

1. **"Steam ID is required"**: Some API types need `--steam-id` parameter
2. **"Invalid JSON"**: Check JSON syntax and structure
3. **"Database connection error"**: Ensure database is initialized
4. **"Missing required field"**: Check that all required fields are present

### Getting Help

Run scripts with `--help` for detailed usage information:

```bash
python scripts/json_database_importer.py --help
python scripts/steamworks_json_converter.py --help
```

Use `--verbose` flag for detailed logging:

```bash
python scripts/json_database_importer.py --file data.json --verbose
```

Use `--dry-run` to test without making changes:

```bash
python scripts/json_database_importer.py --file data.json --dry-run
```
