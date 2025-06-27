#!/bin/bash

# .SYNOPSIS
#     Starts the FamilyBot with integrated token sender plugin.
#
# .DESCRIPTION
#     This script automates the process of:
#     1. Finding the virtual environment activation script.
#     2. Launching FamilyBot.py in a new, independent terminal window.
#
#     The token sender now runs as an integrated plugin within the main bot process.
#
# .NOTES
#     - Run this script from the FamilyBot/ project root directory.
#     - Requires Bash shell.
#     - Requires 'uv' to be installed and your virtual environment is set up.
#     - Assumes 'gnome-terminal', 'konsole', or 'xterm' (or 'open' on macOS) is available.
#     - You must manually close the bot window when you want to stop it.
#     - For first-time setup, run 'uv run familybot-setup' to configure Steam login.
# .EXAMPLE
#     ./run_bots.sh

# --- Configuration ---
PROJECT_ROOT=$(pwd)
ACTIVATE_SCRIPT="$PROJECT_ROOT/.venv/bin/activate"
FAMILYBOT_SCRIPT="$PROJECT_ROOT/src/familybot/FamilyBot.py"

# --- Helper function for colored output ---
COLOR_BLUE='\033[0;34m'
COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[0;33m'
COLOR_RED='\033[0;31m'
COLOR_CYAN='\033[0;36m'
COLOR_NC='\033[0m' # No Color

echo -e "${COLOR_CYAN}--- Starting FamilyBot (with integrated token sender) ---${COLOR_NC}"

# --- Verify paths exist ---
if [[ ! -f "$ACTIVATE_SCRIPT" ]]; then
    echo -e "${COLOR_RED}ERROR: Virtual environment activation script not found at $ACTIVATE_SCRIPT. Please run './reinstall_bot.sh' first.${COLOR_NC}"
    exit 1
fi
if [[ ! -f "$FAMILYBOT_SCRIPT" ]]; then
    echo -e "${COLOR_RED}ERROR: FamilyBot script not found at $FAMILYBOT_SCRIPT. Check path and project structure.${COLOR_NC}"
    exit 1
fi

# --- Check if browser profile exists ---
BROWSER_PROFILE_PATH="$PROJECT_ROOT/FamilyBotBrowserProfile"
if [[ ! -d "$BROWSER_PROFILE_PATH" ]]; then
    echo -e "${COLOR_YELLOW}WARNING: Browser profile not found at $BROWSER_PROFILE_PATH${COLOR_NC}"
    echo -e "${COLOR_YELLOW}For token sender functionality, run: uv run familybot-setup${COLOR_NC}"
fi

# --- Function to launch in a new terminal ---
launch_in_new_terminal() {
    local script_to_run="$1"
    local window_title="$2"
    local terminal_command=""

    # Detect terminal type for cross-platform compatibility
    if command -v gnome-terminal &> /dev/null; then
        terminal_command="gnome-terminal --title=\"$window_title\" -- bash -c \"source '$ACTIVATE_SCRIPT' && uv run python '$script_to_run' ; exec bash\""
    elif command -v konsole &> /dev/null; then
        terminal_command="konsole --new-tab -p tabtitle=\"$window_title\" -e bash -c \"source '$ACTIVATE_SCRIPT' && uv run python '$script_to_run' ; exec bash\""
    elif command -v xterm &> /dev/null; then
        terminal_command="xterm -title \"$window_title\" -e bash -c \"source '$ACTIVATE_SCRIPT' && uv run python '$script_to_run' ; exec bash\""
    elif [[ "$OSTYPE" == "darwin"* ]]; then # macOS
        # For macOS, 'open' is generally used to launch new applications (like Terminal.app)
        # We need to construct an AppleScript to ensure it runs in a new tab/window
        osascript -e "tell application \"Terminal\" to do script \"cd '$PROJECT_ROOT'; source '$ACTIVATE_SCRIPT' && uv run python '$script_to_run'\"" -e "tell application \"Terminal\" to set custom title of front window to \"$window_title\""
        return # AppleScript handles launching, so return
    else
        echo -e "${COLOR_RED}WARNING: No supported terminal emulator found (gnome-terminal, konsole, xterm, macOS Terminal). Bots will not launch in new windows.${COLOR_NC}"
        echo -e "${COLOR_YELLOW}To run manually: In a new terminal: cd '$PROJECT_ROOT' && source '$ACTIVATE_SCRIPT' && uv run python '$script_to_run'${COLOR_NC}"
        return
    fi

    # Execute the determined terminal command (for Linux)
    if [[ -n "$terminal_command" ]]; then
        eval "$terminal_command" & disown # '& disown' detaches the process
    fi
}


# --- Launch process ---

echo -e "${COLOR_YELLOW}Launching FamilyBot (main bot with integrated token sender)...${COLOR_NC}"
launch_in_new_terminal "$FAMILYBOT_SCRIPT" "FamilyBot - Main Bot"
echo -e "${COLOR_GREEN}FamilyBot launched in a new window.${COLOR_NC}"

echo -e "${COLOR_CYAN}--- Launch sequence complete ---${COLOR_NC}"
echo -e "${COLOR_CYAN}Check the newly opened terminal window for bot logs.${COLOR_NC}"
echo -e "${COLOR_CYAN}The token sender plugin will run automatically within the main bot process.${COLOR_NC}"
