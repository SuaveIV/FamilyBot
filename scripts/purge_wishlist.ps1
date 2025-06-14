#!/usr/bin/env pwsh
# FamilyBot Wishlist Cache Purge Utility
# Purges wishlist cache to force fresh wishlist data

Write-Host "🗑️ FamilyBot Wishlist Cache Purge Utility" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Change to the parent directory (where FamilyBot is located)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ParentDir = Split-Path -Parent $ScriptDir
Set-Location $ParentDir

# Run the bot with purge-wishlist argument
python -m src.familybot.FamilyBot --purge-wishlist

Write-Host ""
Write-Host "Press any key to continue..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
