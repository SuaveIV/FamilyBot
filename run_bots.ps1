<#
.SYNOPSIS
    Starts both the FamilyBot (main bot + WebSocket server) and the Token Sender bot.

.DESCRIPTION
    This script automates the process of:
    1. Finding the virtual environment activation script.
    2. Launching FamilyBot.py in a new, independent PowerShell process.
    3. Launching getToken.py in another new, independent PowerShell process.

    Both bots will run in their own separate windows, allowing them to operate concurrently.

.NOTES
    - Run this script from the FamilyBot/ project root directory.
    - Requires PowerShell 7 or later.
    - Assumes 'uv' is installed and your virtual environment is set up.
    - You must manually close the bot windows when you want to stop them.
.EXAMPLE
    .\run_bots.ps1
#>

# --- Configuration ---
$ProjectRoot = Get-Location
$ActivateScript = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
$FamilyBotScript = Join-Path $ProjectRoot "src\familybot\FamilyBot.py"
$TokenSenderScript = Join-Path $ProjectRoot "src\familybot\Token_Sender\getToken.py"

Write-Host "--- Starting FamilyBot and Token Sender ---" -ForegroundColor Cyan

# --- Verify paths exist ---
if (-not (Test-Path $ActivateScript)) {
    Write-Host "ERROR: Virtual environment activation script not found at $ActivateScript. Please run '.\reinstall_bot.ps1' first." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $FamilyBotScript)) {
    Write-Host "ERROR: FamilyBot script not found at $FamilyBotScript. Check path and project structure." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $TokenSenderScript)) {
    Write-Host "ERROR: Token Sender script not found at $TokenSenderScript. Check path and project structure." -ForegroundColor Red
    exit 1
}

# --- Construct the commands to run each bot ---
# The -Command string will set the ExecutionPolicy for that spawned PowerShell process
# ONLY for the duration of its execution.
# This is generally safer than passing -ExecutionPolicy Bypass as an argument to powershell.exe itself
# as it's within the command string.

# Command for FamilyBot: Set policy for the process, then activate venv, then run python script with uv
$FamilyBotCommand = @"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned -Force; cd '$ProjectRoot'; . '$ActivateScript'; uv run python '$FamilyBotScript'"
"@

# Command for Token Sender: Set policy for the process, then activate venv, then run python script with uv
$TokenSenderCommand = @"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned -Force; cd '$ProjectRoot'; . '$ActivateScript'; uv run python '$TokenSenderScript'"
"@

# --- Launch processes ---

Write-Host "Launching FamilyBot (main bot + WebSocket server)..." -ForegroundColor Yellow
try {
    Start-Process powershell.exe -ArgumentList "-NoProfile", "-Command", "$FamilyBotCommand" -ErrorAction Stop
    Write-Host "FamilyBot launched in a new window." -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to launch FamilyBot." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

Write-Host "Launching Token Sender bot..." -ForegroundColor Yellow
try {
    Start-Process powershell.exe -ArgumentList "-NoProfile", "-Command", "$TokenSenderCommand" -ErrorAction Stop
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Token Sender bot launched in a new window." -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to launch Token Sender bot." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

Write-Host "--- Launch sequence complete ---" -ForegroundColor Cyan
Write-Host "Check the newly opened PowerShell windows for bot logs." -ForegroundColor Cyan