"""Backward-compatible re-exports for plugin admin actions.

This module re-exports functions from the new service modules for backward
compatibility. New code should import directly from the service modules:
- family_library_service: Family library fetching and new game detection
- wishlist_service: Wishlist collection and duplicate detection
- deal_service: Deal finding and notifications
- cache_service: Cache management operations
- api_utils: API utility functions
"""

# Re-export from family_library_service
from familybot.lib.family_library_service import (
    check_new_game as check_new_game_action,
    fetch_family_library_from_api as _fetch_family_library_from_api,
    force_new_game as force_new_game_action,
    process_new_games as _process_new_games,
)

# Re-export from wishlist_service
from familybot.lib.wishlist_service import (
    check_wishlist as check_wishlist_action,
    collect_wishlists as _collect_wishlists,
    force_wishlist as force_wishlist_action,
    process_wishlist_duplicates as _process_wishlist_duplicates,
)

# Re-export from deal_service
from familybot.lib.deal_service import (
    force_deals as force_deals_action,
)

# Re-export from cache_service
from familybot.lib.cache_service import (
    purge_game_details_cache as purge_game_details_cache_action,
)

# Re-export from api_utils
from familybot.lib.api_utils import (
    handle_api_response as _handle_api_response,
)

__all__ = [
    # Family library functions
    "check_new_game_action",
    "force_new_game_action",
    "_fetch_family_library_from_api",
    "_process_new_games",
    # Wishlist functions
    "check_wishlist_action",
    "force_wishlist_action",
    "_collect_wishlists",
    "_process_wishlist_duplicates",
    # Deal functions
    "force_deals_action",
    # Cache functions
    "purge_game_details_cache_action",
    # API utilities
    "_handle_api_response",
]
