<#
.SYNOPSIS
    Performs a complete clean reinstall of the FamilyBot's virtual environment and dependencies.

.DESCRIPTION
    This script automates the process of:
    1. Deactivating the current virtual environment (if active).
    2. Deleting the existing virtual environment folder (.venv).
    3. Deleting all __pycache__ folders within the project.
    4. Creating a new virtual environment using uv.
    5. Activating the newly created virtual environment.
    6. Installing all project dependencies from pyproject.toml in editable mode using uv.

.NOTES
    - Run this script from the FamilyBot/ project root directory.
    - Requires PowerShell 7 or later.
    - Requires 'uv' to be installed and in your system's PATH.
    - This script will delete the .venv folder and __pycache__ folders.
.EXAMPLE
    .\reinstall_bot.ps1
#>

# --- Configuration ---
$ProjectRoot = Get-Location
$VenvPath = Join-Path $ProjectRoot ".venv"
$PythonExecutable = Join-Path $VenvPath "Scripts" "python.exe"
$ActivateScript = Join-Path $VenvPath "Scripts" "Activate.ps1"

Write-Host "--- Starting FamilyBot Reinstall Process ---" -ForegroundColor Cyan

# 1. Deactivate current virtual environment if active
Write-Host "1. Deactivating virtual environment (if active)..." -ForegroundColor Yellow
if ($env:VIRTUAL_ENV) {
    if (Get-Command "deactivate" -ErrorAction SilentlyContinue) {
        deactivate
        Write-Host "   Deactivated." -ForegroundColor Green
    } else {
        Write-Host "   'deactivate' command not found, attempting manual path cleanup." -ForegroundColor Yellow
        $env:VIRTUAL_ENV = $null
        $env:PATH = ($env:PATH -split ';') | Where-Object { -not ($_ -like "*\.venv\Scripts") } | Join-String -Separator ';'
    }
} else {
    Write-Host "   No virtual environment active." -ForegroundColor Green
}

# 2. Deleting existing virtual environment folder
Write-Host "2. Deleting existing virtual environment folder: $VenvPath" -ForegroundColor Yellow
if (Test-Path $VenvPath) {
    try {
        Remove-Item -Path $VenvPath -Recurse -Force -ErrorAction Stop # PowerShell cmdlet error handling
        Write-Host "   Deleted .venv folder." -ForegroundColor Green
    } catch {
        Write-Host "   ERROR: Failed to delete .venv folder. Please close any processes using files in .venv and try again." -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "   .venv folder not found, skipping deletion." -ForegroundColor Green
}

# 3. Deleting all __pycache__ folders
Write-Host "3. Deleting all __pycache__ folders..." -ForegroundColor Yellow
try {
    Get-ChildItem -Path $ProjectRoot -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction Stop # PowerShell cmdlet error handling
    Write-Host "   Deleted __pycache__ folders." -ForegroundColor Green
} catch {
    Write-Host "   ERROR: Failed to delete __pycache__ folders." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# 4. Creating a new virtual environment using uv
Write-Host "4. Creating a new virtual environment using uv..." -ForegroundColor Yellow
try {
    # Call uv venv directly without any additional PowerShell parameters
    # The try/catch block will rely on uv's exit code for error detection
    uv venv # <<< Clean call
    Write-Host "   New virtual environment created." -ForegroundColor Green
} catch {
    Write-Host "   ERROR: Failed to create virtual environment with uv." -ForegroundColor Red
    Write-Host "   Error message from uv: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Verifying Activate.ps1 exists
Write-Host "   Verifying Activate.ps1 script..." -ForegroundColor Yellow
if (Test-Path $ActivateScript) {
    Write-Host "   Activate.ps1 found." -ForegroundColor Green
} else {
    Write-Host "   ERROR: Activate.ps1 script NOT found after uv venv. Something went wrong." -ForegroundColor Red
    Write-Host "   Please try running 'uv venv' manually and check for errors." -ForegroundColor Red
    exit 1
}

# 5. Activating the new virtual environment
Write-Host "5. Activating the new virtual environment..." -ForegroundColor Yellow
try {
    . $ActivateScript -ErrorAction Stop # This is a PowerShell script, so -ErrorAction Stop applies here
    if ($env:VIRTUAL_ENV -like "*\.venv") {
        Write-Host "   Virtual environment activated." -ForegroundColor Green
    } else {
        Write-Host "   WARNING: Virtual environment activation seemed to fail. Check your prompt for '(.)venv'." -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ERROR: Failed to activate virtual environment." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# 6. Installing all project dependencies
Write-Host "6. Installing all project dependencies with 'uv pip install -e .'..." -ForegroundColor Yellow
try {
    # Call uv pip install with the -- to separate uv's arguments from pip's arguments
    # Let PowerShell's try/catch handle errors based on uv's exit code
    uv pip install -e . # <<< Clean call for uv pip install
    Write-Host "   All dependencies installed successfully." -ForegroundColor Green
} catch {
    Write-Host "   ERROR: Failed to install project dependencies." -ForegroundColor Red
    Write-Host "   Error message from uv: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "--- Reinstall Process Complete ---" -ForegroundColor Cyan
Write-Host "You can now run your bot: uv run python .\src\familybot\FamilyBot.py" -ForegroundColor Cyan
Write-Host "And your token sender: uv run python .\src\familybot\Token_Sender\getToken.py" -ForegroundColor Cyan