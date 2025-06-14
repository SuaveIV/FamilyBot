#!/usr/bin/env pwsh
# FamilyBot Family Library Cache Purge Utility
# Purges family library cache to force fresh family game data

Write-Host "🗑️ FamilyBot Family Library Cache Purge Utility" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

# Change to the parent directory (where FamilyBot is located)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ParentDir = Split-Path -Parent $ScriptDir
Set-Location $ParentDir

# Run the bot with purge-family-library argument
python -m src.familybot.FamilyBot --purge-family-library

Write-Host ""
Write-Host "Press any key to continue..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
