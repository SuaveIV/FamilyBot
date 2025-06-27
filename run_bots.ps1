<#
.SYNOPSIS
    Starts the FamilyBot with integrated token sender plugin.

.DESCRIPTION
    This script automates the process of:
    1. Finding the virtual environment activation script.
    2. Launching FamilyBot.py in a new, independent PowerShell process.
    
    The token sender now runs as an integrated plugin within the main bot process.

.NOTES
    - Run this script from the FamilyBot/ project root directory.
    - Requires PowerShell 7 or later.
    - Assumes 'uv' is installed and your virtual environment is set up.
    - You must manually close the bot window when you want to stop it.
    - For first-time setup, run 'uv run familybot-setup' to configure Steam login.
.EXAMPLE
    .\run_bots.ps1
#>

# --- Configuration ---
$ProjectRoot = Get-Location
$ActivateScript = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
$FamilyBotScript = Join-Path $ProjectRoot "src\familybot\FamilyBot.py"

Write-Host "--- Starting FamilyBot (with integrated token sender) ---" -ForegroundColor Cyan

# --- Verify paths exist ---
if (-not (Test-Path $ActivateScript)) {
    Write-Host "ERROR: Virtual environment activation script not found at $ActivateScript. Please run '.\reinstall_bot.ps1' first." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $FamilyBotScript)) {
    Write-Host "ERROR: FamilyBot script not found at $FamilyBotScript. Check path and project structure." -ForegroundColor Red
    exit 1
}

# --- Check if browser profile exists ---
$BrowserProfilePath = Join-Path $ProjectRoot "FamilyBotBrowserProfile"
if (-not (Test-Path $BrowserProfilePath)) {
    Write-Host "WARNING: Browser profile not found at $BrowserProfilePath" -ForegroundColor Yellow
    Write-Host "For token sender functionality, run: uv run familybot-setup" -ForegroundColor Yellow
}

# --- Construct the command to run the bot ---
# The -Command string will set the ExecutionPolicy for that spawned PowerShell process
# ONLY for the duration of its execution.

# Command for FamilyBot: Set policy for the process, then activate venv, then run python script with uv
$FamilyBotCommand = @"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned -Force; cd '$ProjectRoot'; . '$ActivateScript'; uv run python '$FamilyBotScript'"
"@

# --- Launch process ---

Write-Host "Launching FamilyBot (main bot with integrated token sender)..." -ForegroundColor Yellow
try {
    Start-Process powershell.exe -ArgumentList "-NoProfile", "-Command", "$FamilyBotCommand" -ErrorAction Stop
    Write-Host "FamilyBot launched in a new window." -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to launch FamilyBot." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
}

Write-Host "--- Launch sequence complete ---" -ForegroundColor Cyan
Write-Host "Check the newly opened PowerShell window for bot logs." -ForegroundColor Cyan
Write-Host "The token sender plugin will run automatically within the main bot process." -ForegroundColor Cyan
