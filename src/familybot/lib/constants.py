# In src/familybot/lib/constants.py

# --- Rate Limiting Constants ---
STEAM_API_RATE_LIMIT = 3.0  # Minimum seconds between Steam API calls (e.g., GetOwnedGames, GetFamilySharedApps)
STEAM_STORE_API_RATE_LIMIT = (
    2.0  # Minimum seconds between Steam Store API calls (e.g., appdetails)
)
FULL_SCAN_RATE_LIMIT = (
    5.0  # Minimum seconds between Steam Store API calls for full wishlist scans
)

# --- Steam API & Logic Constants ---
MAX_WISHLIST_GAMES_TO_PROCESS = 100  # Limit appdetails calls to 100 games per run
HIGH_DISCOUNT_THRESHOLD = 30  # % discount for high discount categorization
LOW_DISCOUNT_THRESHOLD = 15  # % discount for low discount categorization
HISTORICAL_LOW_BUFFER = (
    1.2  # Allow price up to 20% above historical low for "great deal"
)

# --- Discord Constants ---
DISCORD_MESSAGE_LIMIT = (
    1950  # Maximum characters allowed in a Discord message (with safety buffer)
)
DISCORD_EMBED_LIMIT = 6000  # Maximum characters allowed in a Discord embed

# --- UI & Progress Constants ---
DEFAULT_PROGRESS_INTERVAL = 10  # Percentage interval for reporting progress
MIN_ELAPSED_TIME_FOR_ESTIMATION = (
    1  # Minimum seconds elapsed before showing time estimation
)
SECONDS_PER_MINUTE = 60  # Number of seconds in a minute
