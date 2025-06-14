#!/bin/bash
# FamilyBot Cache Purge Utility
# Purges game details cache to force fresh USD pricing and new boolean fields

echo "🗑️ FamilyBot Cache Purge Utility"
echo "================================="
echo ""

# Change to the parent directory (where FamilyBot is located)
cd "$(dirname "$0")/.."

# Run the bot with purge-cache argument
python -m src.familybot.FamilyBot --purge-cache

echo ""
echo "Press any key to continue..."
read -n 1 -s
