#!/usr/bin/env python3
"""
Steamworks JSON Converter for FamilyBot

This script converts raw Steamworks API JSON responses into the format expected by
the FamilyBot JSON Database Importer.

Supported Steamworks API responses:
- GetOwnedGames (IPlayerService/GetOwnedGames/v1)
- GetPlayerSummaries (ISteamUser/GetPlayerSummaries/v2)
- GetWishlist (IWishlistService/GetWishlist/v1)
- Steam Store API (store.steampowered.com/api/appdetails)

Usage:
    python scripts/steamworks_json_converter.py --api-type owned_games --file steamworks_response.json
    python scripts/steamworks_json_converter.py --api-type player_summaries --json '{"response": {...}}'
    python scripts/steamworks_json_converter.py --api-type app_details --stdin < steam_store_response.json
"""

import sys
import os
import json
import argparse
import requests
import time
from typing import Dict, List, Any, Optional
from datetime import datetime

def convert_owned_games(data: Dict[str, Any], steam_id: Optional[str] = None) -> Dict[str, Any]:
    """Convert GetOwnedGames API response to FamilyBot format."""
    response = data.get('response', {})
    games = response.get('games', [])
    
    if not steam_id:
        # Try to extract from the response if available
        steam_id = response.get('steamid') or response.get('steam_id')
    
    if not steam_id:
        raise ValueError("Steam ID is required for owned games conversion. Use --steam-id parameter.")
    
    converted_games = []
    for game in games:
        appid = str(game.get('appid'))
        if appid:
            # Create a saved game entry
            converted_games.append({
                "type": "saved_game",
                "appid": appid,
                "detected_at": datetime.utcnow().isoformat() + 'Z'
            })
            
            # If the game has name info, create a basic game details entry
            if game.get('name'):
                converted_games.append({
                    "type": "game_details",
                    "appid": appid,
                    "name": game['name'],
                    "type": "game",
                    "is_free": False,  # Default, will be updated if we have price info
                    "categories": []
                })
    
    return {
        "type": "batch",
        "data": converted_games
    }

def convert_player_summaries(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert GetPlayerSummaries API response to FamilyBot format."""
    response = data.get('response', {})
    players = response.get('players', [])
    
    converted_users = []
    for player in players:
        steam_id = player.get('steamid')
        persona_name = player.get('personaname')
        
        if steam_id:
            # Create family member entry
            converted_users.append({
                "type": "family_member",
                "steam_id": steam_id,
                "friendly_name": persona_name or f"User_{steam_id[-4:]}",
                "discord_id": None  # Will need to be filled manually
            })
    
    return {
        "type": "batch",
        "data": converted_users
    }

def convert_wishlist(data: Dict[str, Any], steam_id: Optional[str] = None) -> Dict[str, Any]:
    """Convert GetWishlist API response to FamilyBot format."""
    response = data.get('response', {})
    items = response.get('items', [])
    
    if not steam_id:
        raise ValueError("Steam ID is required for wishlist conversion. Use --steam-id parameter.")
    
    converted_items = []
    for item in items:
        appid = str(item.get('appid'))
        if appid:
            # Create a saved game entry for wishlist items
            converted_items.append({
                "type": "saved_game",
                "appid": appid,
                "detected_at": datetime.utcnow().isoformat() + 'Z'
            })
    
    return {
        "type": "batch",
        "data": converted_items
    }

def convert_app_details(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Steam Store API appdetails response to FamilyBot format."""
    converted_games = []
    
    # Steam Store API returns data keyed by appid
    for appid, app_data in data.items():
        if isinstance(app_data, dict) and app_data.get('success'):
            game_data = app_data.get('data', {})
            
            if game_data:
                converted_game = {
                    "type": "game_details",
                    "appid": appid,
                    "name": game_data.get('name', ''),
                    "type": game_data.get('type', 'game'),
                    "is_free": game_data.get('is_free', False),
                    "categories": game_data.get('categories', [])
                }
                
                # Add price information if available
                price_overview = game_data.get('price_overview')
                if price_overview:
                    converted_game['price_overview'] = price_overview
                
                converted_games.append(converted_game)
    
    return {
        "type": "batch",
        "data": converted_games
    }

def convert_family_library(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert GetSharedLibraryApps API response to FamilyBot format."""
    response = data.get('response', {})
    apps = response.get('apps', [])
    
    converted_games = []
    for app in apps:
        appid = str(app.get('appid'))
        if appid:
            converted_games.append({
                "type": "saved_game",
                "appid": appid,
                "detected_at": datetime.utcnow().isoformat() + 'Z'
            })
    
    return {
        "type": "batch",
        "data": converted_games
    }

def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Convert Steamworks API JSON to FamilyBot import format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--file", "-f", help="JSON file to convert")
    input_group.add_argument("--json", "-j", help="JSON string to convert")
    input_group.add_argument("--stdin", action="store_true", help="Read JSON from stdin")
    
    # API type
    parser.add_argument("--api-type", "-t", required=True,
                       choices=['owned_games', 'player_summaries', 'wishlist', 'app_details', 'family_library'],
                       help="Type of Steamworks API response")
    
    # Additional options
    parser.add_argument("--steam-id", "-s", help="Steam ID (required for some API types)")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument("--pretty", "-p", action="store_true", help="Pretty print JSON output")
    
    args = parser.parse_args()
    
    print("🔄 Steamworks JSON Converter", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    
    # Load JSON data
    json_data = None
    try:
        if args.file:
            print(f"📁 Loading JSON from file: {args.file}", file=sys.stderr)
            with open(args.file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        elif args.json:
            print("📝 Parsing JSON from command line", file=sys.stderr)
            json_data = json.loads(args.json)
        elif args.stdin:
            print("📥 Reading JSON from stdin", file=sys.stderr)
            json_data = json.load(sys.stdin)
    
    except FileNotFoundError:
        print(f"❌ File not found: {args.file}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Error loading JSON: {e}", file=sys.stderr)
        return 1
    
    # Convert based on API type
    try:
        print(f"🔄 Converting {args.api_type} data...", file=sys.stderr)
        
        if not isinstance(json_data, dict):
            print("❌ JSON data must be a dictionary", file=sys.stderr)
            return 1
        
        if args.api_type == 'owned_games':
            converted_data = convert_owned_games(json_data, args.steam_id)
        elif args.api_type == 'player_summaries':
            converted_data = convert_player_summaries(json_data)
        elif args.api_type == 'wishlist':
            converted_data = convert_wishlist(json_data, args.steam_id)
        elif args.api_type == 'app_details':
            converted_data = convert_app_details(json_data)
        elif args.api_type == 'family_library':
            converted_data = convert_family_library(json_data)
        else:
            print(f"❌ Unsupported API type: {args.api_type}", file=sys.stderr)
            return 1
        
        # Output converted data
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                if args.pretty:
                    json.dump(converted_data, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(converted_data, f, ensure_ascii=False)
            print(f"✅ Converted data saved to: {args.output}", file=sys.stderr)
        else:
            if args.pretty:
                print(json.dumps(converted_data, indent=2, ensure_ascii=False))
            else:
                print(json.dumps(converted_data, ensure_ascii=False))
        
        print(f"🎉 Conversion completed! Found {len(converted_data.get('data', []))} records", file=sys.stderr)
        return 0
    
    except Exception as e:
        print(f"❌ Error during conversion: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user", file=sys.stderr)
        sys.exit(1)
