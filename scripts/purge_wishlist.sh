#!/bin/bash
# FamilyBot Wishlist Cache Purge Utility
# Purges wishlist cache to force fresh wishlist data

echo "🗑️ FamilyBot Wishlist Cache Purge Utility"
echo "========================================="
echo ""

# Change to the parent directory (where FamilyBot is located)
cd "$(dirname "$0")/.."

# Run the bot with purge-wishlist argument
python -m src.familybot.FamilyBot --purge-wishlist

echo ""
echo "Press any key to continue..."
read -n 1 -s
