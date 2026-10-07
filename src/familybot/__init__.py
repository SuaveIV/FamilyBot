"""FamilyBot: a Discord bot for Steam families, wishlists, and free-game alerts."""

import warnings

# The `steam` package (1.4.4, last released 2022) has invalid escape sequences in
# steam/steamid.py that Python 3.12+ reports as SyntaxWarning at import time. The
# affected regexes still behave correctly, so silence those warnings. Compile-time
# warnings report no module name, so this can only be scoped by message; our own
# code is covered by ruff's W605 (invalid escape sequence) instead.
warnings.filterwarnings(
    "ignore",
    message="invalid escape sequence",
    category=SyntaxWarning,
)
