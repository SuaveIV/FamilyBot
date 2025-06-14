#!/bin/bash
# FamilyBot All Cache Purge Utility
# Purges all cache data (game details, wishlist, family library, etc.)

echo "🗑️ FamilyBot All Cache Purge Utility"
echo "===================================="
echo ""

# Change to the parent directory (where FamilyBot is located)
cd "$(dirname "$0")/.."

# Run the bot with purge-all argument
python -m src.familybot.FamilyBot --purge-all

echo ""
echo "Press any key to continue..."
read -n 1 -s
