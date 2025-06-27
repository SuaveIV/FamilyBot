# Token Sender Migration: Selenium to Playwright Plugin

This document outlines the migration of the Token Sender from a standalone Selenium-based script to a Playwright-based plugin integrated into the main FamilyBot.

## Overview

The Token Sender has been successfully converted from:

- **From**: Standalone Python script using Selenium WebDriver
- **To**: FamilyBot plugin using Playwright for browser automation

## Key Changes

### 1. Architecture Changes

- **Integration**: Now runs as a plugin within the main FamilyBot process
- **No WebSocket Communication**: Direct token management within the bot (no need for external WebSocket server communication)
- **Unified Configuration**: Configuration moved to main `config.yml` file
- **Shared Logging**: Uses FamilyBot's logging system

### 2. Technology Stack

- **Browser Automation**: Selenium → Playwright
- **Browser**: Firefox (geckodriver) → Chromium (built-in)
- **Execution**: Standalone process → Plugin within bot process

### 3. Configuration Changes

#### Old Configuration (`src/familybot/Token_Sender/config.yaml`)

```yaml
server_ip: "127.0.0.1"
token_save_path: "tokens/"
firefox_profile_path: ""
shutdown: false
```

#### New Configuration (added to main `config.yml`)

```yaml
token_sender:
  token_save_path: "tokens/"
  browser_profile_path: ""
  update_buffer_hours: 1
```

### 4. New Features

#### Admin Commands

- `!force_token` - Force immediate token update (admin only, DM only)
- `!token_status` - Check current token status and expiry (admin only, DM only)

#### Improved Scheduling

- Hourly checks instead of minute-based scheduling
- Smart scheduling based on token expiry time with configurable buffer
- 24-hour token lifecycle awareness

#### Better Error Handling

- Graceful handling of missing Playwright installation
- Admin notifications via DM for errors and successful updates
- Comprehensive logging with different log levels

## Installation Requirements

### 1. Install Playwright

```bash
uv add playwright
uv run playwright install chromium
```

### 2. Update Configuration

Add the token_sender section to your main `config.yml`:

```yaml
token_sender:
  token_save_path: "tokens/"  # Directory for token storage
  browser_profile_path: ""    # Optional: Path to browser profile logged into Steam
  update_buffer_hours: 1      # Hours before expiry to update token
```

### 3. Browser Profile (Optional)

If you want to use a specific browser profile logged into Steam:

1. Create a Chromium profile and log into Steam
2. Set the `browser_profile_path` to the profile directory path
3. If left empty, the plugin will use a default headless browser (requires manual Steam login handling)

## Migration Steps

### 1. Stop the Old Token Sender

- Stop any running instances of the standalone `getToken.py` script
- Disable any scheduled tasks or services running the old token sender

### 2. Install Dependencies

```bash
uv add playwright
uv run playwright install chromium
```

### 3. Update Configuration

- Add the `token_sender` section to your main `config.yml`
- Configure the browser profile path if needed

### 4. Test the Plugin

- Start the FamilyBot with the new plugin
- Use `!token_status` to check current token status
- Use `!force_token` to test token fetching functionality

### 5. Verify Operation

- Check logs for successful plugin loading
- Verify token files are being created/updated in the configured directory
- Confirm admin DM notifications are working

## Plugin Features

### Automatic Token Management

- **Scheduled Updates**: Checks every hour for token expiry
- **Smart Timing**: Updates token 1 hour before expiry (configurable)
- **Duplicate Prevention**: Only updates when token actually changes
- **Persistence**: Saves token and expiry information to files

### Browser Automation

- **Headless Operation**: Runs without visible browser window
- **Profile Support**: Can use existing browser profiles logged into Steam
- **Robust Navigation**: Handles Steam's points summary page navigation
- **Error Recovery**: Graceful handling of page loading issues

### Monitoring and Control

- **Admin Commands**: Force updates and check status via Discord DMs
- **Comprehensive Logging**: Detailed logs for debugging and monitoring
- **Error Notifications**: Automatic admin notifications for issues
- **Status Reporting**: Real-time token status with expiry information

### Security and Reliability

- **Admin-Only Access**: Commands restricted to configured admin user
- **DM-Only Commands**: Sensitive commands only work in direct messages
- **Error Isolation**: Plugin errors don't crash the main bot
- **Graceful Degradation**: Handles missing dependencies appropriately

## File Structure

### New Files

- `src/familybot/plugins/token_sender.py` - Main plugin file
- `TOKEN_SENDER_MIGRATION.md` - This documentation

### Modified Files

- `requirements.txt` - Added Playwright dependency
- `config.yml` - Added token_sender configuration section
- `src/familybot/config.py` - Added token_sender config variables

### Preserved Files

- `src/familybot/Token_Sender/` - Original implementation (kept for reference)
- `tokens/` directory - Token storage location (unchanged)

## Troubleshooting

### Common Issues

#### 1. Playwright Not Installed

**Error**: `Playwright not installed. Please install with: uv add playwright`
**Solution**:

```bash
uv add playwright
uv run playwright install chromium
```

#### 2. Browser Profile Issues

**Error**: Token extraction fails with authentication errors
**Solution**:

- Ensure the browser profile path is correct
- Verify the profile is logged into Steam
- Try using an empty `browser_profile_path` for default behavior

#### 3. Token Extraction Failures

**Error**: Cannot find webapi_token in page source
**Solution**:

- Check if Steam's page structure has changed
- Verify network connectivity to Steam
- Check browser profile authentication status

#### 4. Permission Errors

**Error**: Commands don't work or return permission denied
**Solution**:

- Ensure commands are used in DMs only
- Verify admin Discord ID is correctly configured
- Check that the user ID matches the configured admin ID

### Logging

The plugin uses FamilyBot's logging system. Check logs for:

- Plugin loading status
- Token update attempts
- Error messages and stack traces
- Playwright availability status

### Testing Commands

Use these commands in DMs with the bot (admin only):

- `!token_status` - Check current token status
- `!force_token` - Force immediate token update

## Benefits of the Migration

### 1. Simplified Architecture

- No separate process management
- No WebSocket server dependency
- Unified configuration and logging

### 2. Better Reliability

- Modern browser automation with Playwright
- Improved error handling and recovery
- Integrated monitoring and alerting

### 3. Enhanced Features

- Real-time status checking
- Force update capability
- Better scheduling logic
- Admin notifications

### 4. Easier Maintenance

- Single codebase to maintain
- Consistent with other bot plugins
- Better integration with bot lifecycle

## Future Enhancements

Potential improvements for future versions:

- Support for multiple Steam accounts
- Token validation and testing
- Backup token storage options
- Integration with external monitoring systems
- Support for other browser engines
- Automated profile management

## Support

For issues or questions regarding the Token Sender plugin:

1. Check the logs for error messages
2. Verify Playwright installation and browser setup
3. Test with `!token_status` and `!force_token` commands
4. Review this documentation for troubleshooting steps

The plugin is designed to be robust and self-healing, with comprehensive error handling and admin notifications to ensure reliable token management.
