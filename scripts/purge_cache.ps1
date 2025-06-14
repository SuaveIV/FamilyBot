#!/usr/bin/env pwsh
# FamilyBot Cache Purge Utility
# Purges game details cache to force fresh USD pricing and new boolean fields

Write-Host "🗑️ FamilyBot Cache Purge Utility" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan
Write-Host ""

# Change to the parent directory (where FamilyBot is located)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ParentDir = Split-Path -Parent $ScriptDir
Set-Location $ParentDir

# Run the bot with purge-cache argument
python -m src.familybot.FamilyBot --purge-cache

Write-Host ""
Write-Host "Press any key to continue..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
