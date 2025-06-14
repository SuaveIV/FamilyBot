#!/usr/bin/env pwsh
# FamilyBot All Cache Purge Utility
# Purges all cache data (game details, wishlist, family library, etc.)

Write-Host "🗑️ FamilyBot All Cache Purge Utility" -ForegroundColor Red
Write-Host "====================================" -ForegroundColor Red
Write-Host ""

# Change to the parent directory (where FamilyBot is located)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ParentDir = Split-Path -Parent $ScriptDir
Set-Location $ParentDir

# Run the bot with purge-all argument
python -m src.familybot.FamilyBot --purge-all

Write-Host ""
Write-Host "Press any key to continue..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
