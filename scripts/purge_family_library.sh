#!/bin/bash
# FamilyBot Family Library Cache Purge Utility
# Purges family library cache to force fresh family game data

echo "🗑️ FamilyBot Family Library Cache Purge Utility"
echo "==============================================="
echo ""

# Change to the parent directory (where FamilyBot is located)
cd "$(dirname "$0")/.."

# Run the bot with purge-family-library argument
python -m src.familybot.FamilyBot --purge-family-library

echo ""
echo "Press any key to continue..."
read -n 1 -s
