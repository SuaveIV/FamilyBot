"""Fetch free-game listings from multiple sources and normalize them.

Each source implements :class:`FreeGameSource` and returns a list of
:class:`FreeGame` objects. The free-games plugin fans these in, dedupes them,
and renders notifications, so sources can be added or removed without touching
the filtering/embed logic.

Sources:

* ``BlueskySource`` - the FreeGameFindings bot account (@freegamefindings.bsky.social).
* ``GamerPowerSource`` - the GamerPower giveaway API (free, no key, attribution required).
* ``EpicStoreSource`` - the Epic Games Store free-games promotions feed.
"""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

import aiohttp

from familybot.lib.logging_config import get_logger

logger = get_logger(__name__)

# --- Platform tokens (keep in sync with the embed logic in the plugin) ---
PLATFORM_STEAM = "steam"
PLATFORM_EPIC = "epic"
PLATFORM_AMAZON = "amazon"
PLATFORM_GOG = "gog"
PLATFORM_ITCH = "itch"

_PLATFORM_ALIASES = {
    "steam": PLATFORM_STEAM,
    "epic": PLATFORM_EPIC,
    "epic games": PLATFORM_EPIC,
    "epic games store": PLATFORM_EPIC,
    "egs": PLATFORM_EPIC,
    "amazon": PLATFORM_AMAZON,
    "amazon prime gaming": PLATFORM_AMAZON,
    "prime gaming": PLATFORM_AMAZON,
    "luna": PLATFORM_AMAZON,
    "gog": PLATFORM_GOG,
    "gog.com": PLATFORM_GOG,
    "itch": PLATFORM_ITCH,
    "itch.io": PLATFORM_ITCH,
    "itchio": PLATFORM_ITCH,
}

# --- Source endpoints ---
BLUESKY_FEED_URL = (
    "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
    "?actor=freegamefindings.bsky.social&limit=20"
)
GAMERPOWER_GIVEAWAYS_URL = "https://www.gamerpower.com/api/giveaways?type=game"
EPIC_FREE_GAMES_URL = (
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
    "?locale=en-US&country=US&allowCountries=US"
)

# Browser-like UA to reduce the chance of being treated as a bot.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _BROWSER_UA}

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY = 5
_DEFAULT_TIMEOUT = 30

# Noise words stripped when building a cross-source title key, so that
# "BURIED STARS (Epic Games) Giveaway" collapses onto "BURIED STARS".
_TITLE_NOISE = {
    "game", "games", "giveaway", "key", "free", "steam", "gog", "itch", "itchio",
    "amazon", "prime", "gaming", "luna", "mobile", "dlc", "pc", "fanatical",
    "indiegala", "humble", "alienware", "gamesplanet", "gamerpower", "store", "other",
}

# Phrases that mark a giveaway as requiring extra actions (newsletter sign-ups,
# social follows, surveys, point thresholds, ...) rather than a plain claim.
_TASK_KEYWORDS = (
    "newsletter",
    "subscribe",
    "subscription",
    "follow us",
    "follow our",
    "follow on",
    "following us",
    "retweet",
    "repost",
    "share the",
    "survey",
    "complete a task",
    "complete the task",
    "complete tasks",
    "complete a survey",
    "tasks to",
    "points required",
    "arp required",
    "reach level",
    "level up",
    "invite friends",
    "refer a friend",
    "gleam",
    "givee.club",
    "woovit",
    "keymailer",
    "watch a video",
    "watch the video",
    "join our discord",
    "join the discord",
    "daily check",
    "check-in",
    "leave a review",
    "leave a comment",
    "wishlist our",
    "wishlist the",
)



@dataclass(slots=True)
class FreeGame:
    """A normalized free-game listing from any source."""

    source: str
    source_id: str
    title: str
    url: str
    platforms: set[str] = field(default_factory=set)
    text: str = ""
    expires_at: str | None = None

    @property
    def dedupe_key(self) -> str:
        """Stable key used to remember listings across runs."""
        return f"{self.source}:{self.source_id}"

    @property
    def title_key(self) -> str:
        """Loose title key used to collapse the same game across sources.

        Parenthetical notes and noise words (platform, "giveaway", "key", ...)
        are removed so the same title from two sources maps to one key.
        """
        text = re.sub(r"[(\[].*?[)\]]", " ", self.title.lower())
        words = re.findall(r"[a-z0-9]+", text)
        return "".join(word for word in words if word not in _TITLE_NOISE)

    @property
    def requires_tasks(self) -> bool:
        """True when a giveaway demands actions beyond a plain claim.

        Detects newsletter sign-ups, social follows, surveys, point thresholds
        and similar "do this to get the key" mechanics across the listing text.
        """
        text = self.text.lower()
        return any(keyword in text for keyword in _TASK_KEYWORDS)


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (optionally ending in ``Z``)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _normalize_platform(value: str) -> str | None:
    """Map a free-form platform label to one of the platform tokens."""
    return _PLATFORM_ALIASES.get(value.strip().lower())


def _normalize_platforms(values: list[str]) -> set[str]:
    """Map a list of platform labels to the set of recognized tokens."""
    return {token for value in values if (token := _normalize_platform(value))}


async def _fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    retry_delay: int = _DEFAULT_RETRY_DELAY,
    timeout_seconds: int = _DEFAULT_TIMEOUT,
) -> object | None:
    """GET ``url`` and return parsed JSON, retrying on transient failures."""
    for attempt in range(max_retries):
        try:
            async with session.get(
                url,
                headers=headers or _HEADERS,
                timeout=aiohttp.ClientTimeout(total=timeout_seconds),
            ) as response:
                if response.status == 200:
                    return await response.json()
                logger.warning("Request to %s returned status %s", url, response.status)
                # Only transient server errors are worth retrying.
                if not 500 <= response.status < 600:
                    return None
        except (TimeoutError, aiohttp.ClientError) as e:
            logger.warning(
                "Attempt %s/%s failed to fetch %s: %s",
                attempt + 1,
                max_retries,
                url,
                e,
            )
        except Exception as e:
            logger.error("Unexpected error fetching %s: %s", url, e, exc_info=True)
            return None
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay)
    return None


class FreeGameSource:
    """Base class for a free-game source."""

    name: str = "unknown"

    async def fetch(self, session: aiohttp.ClientSession) -> list[FreeGame]:
        """Return the current free games from this source."""
        raise NotImplementedError


class BlueskySource(FreeGameSource):
    """FreeGameFindings mirror on Bluesky."""

    name = "bluesky"

    async def fetch(self, session: aiohttp.ClientSession) -> list[FreeGame]:
        """Fetch and parse the FreeGameFindings Bluesky feed."""
        data = await _fetch_json(session, BLUESKY_FEED_URL)
        if not isinstance(data, dict):
            return []
        games = []
        for post_item in data.get("feed", []):
            game = self._parse_post(post_item)
            if game is not None:
                games.append(game)
        return games

    @staticmethod
    def _parse_post(post_item: dict) -> FreeGame | None:  # noqa: C901
        """Parse a single Bluesky feed item, skipping replies and link-less posts."""
        post = post_item.get("post", {})
        record = post.get("record", {})
        uri = post.get("uri")
        if not uri or record.get("reply"):
            return None

        full_text = record.get("text", "")
        if not full_text:
            return None

        # Platform label is usually the leading "[Steam]" / "[Epic Games]" tag.
        label_match = re.search(r"\[(.*?)\]", full_text)
        platforms = _normalize_platforms([label_match.group(1)]) if label_match else set()

        title = full_text.split("\n", 1)[0].strip()
        title_match = re.search(r"\[.*?\]\s*(.*?)is free", full_text, re.IGNORECASE)
        if title_match and title_match.group(1).strip():
            title = title_match.group(1).strip()
        elif label_match:
            title = full_text.replace(f"[{label_match.group(1)}]", "").strip()
            title = title.split("\n", 1)[0].strip()
        # Drop the leading type marker, e.g. "(Game) Blair Witch" -> "Blair Witch".
        title = re.sub(r"^\([^)]*\)\s*", "", title).strip()

        url = None
        for facet in record.get("facets", []):
            for feature in facet.get("features", []):
                if feature.get("$type") == "app.bsky.richtext.facet#link":
                    url = feature.get("uri")
                    break
            if url:
                break
        if not url:
            url_match = re.search(r"(https?://[^\s]+)", full_text)
            if url_match:
                url = url_match.group(1)
        if not url:
            return None

        # Strip query params so tracking params don't defeat dedupe.
        url = url.split("?", 1)[0]

        return FreeGame(
            source=BlueskySource.name,
            source_id=uri,
            title=title,
            url=url,
            platforms=platforms,
            text=full_text,
        )


class GamerPowerSource(FreeGameSource):
    """GamerPower giveaway API (https://www.gamerpower.com/)."""

    name = "gamerpower"

    async def fetch(self, session: aiohttp.ClientSession) -> list[FreeGame]:
        """Fetch active game giveaways from GamerPower."""
        data = await _fetch_json(session, GAMERPOWER_GIVEAWAYS_URL)
        if not isinstance(data, list):
            return []

        games = []
        for giveaway in data:
            if not isinstance(giveaway, dict):
                continue
            if str(giveaway.get("status", "")).lower() != "active":
                continue
            if str(giveaway.get("type", "")).lower() != "game":
                continue
            url = giveaway.get("open_giveaway_url") or giveaway.get("open_giveaway")
            title = giveaway.get("title")
            if not url or not title:
                continue
            platforms = _normalize_platforms(
                str(giveaway.get("platforms", "")).split(",")
            )
            games.append(
                FreeGame(
                    source=GamerPowerSource.name,
                    source_id=str(giveaway.get("id")),
                    title=title,
                    url=url,
                    platforms=platforms,
                    text=(
                        f"{title}\n{giveaway.get('description', '')}\n"
                        f"{giveaway.get('instructions', '')}"
                    ),
                    expires_at=giveaway.get("end_date"),
                )
            )
        return games


class EpicStoreSource(FreeGameSource):
    """Epic Games Store free-game promotions feed."""

    name = "epic"

    async def fetch(self, session: aiohttp.ClientSession) -> list[FreeGame]:
        """Fetch currently-free Epic Games Store promotions."""
        data = await _fetch_json(session, EPIC_FREE_GAMES_URL)
        if not isinstance(data, dict):
            return []
        elements = (
            data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
        )
        now = datetime.now(UTC)

        games = []
        for element in elements:
            offer = self._active_free_offer(element, now)
            if offer is None:
                continue
            slug = self._slug(element)
            title = element.get("title")
            if not slug or not title:
                continue
            games.append(
                FreeGame(
                    source=EpicStoreSource.name,
                    source_id=str(element.get("id") or slug),
                    title=title,
                    url=f"https://store.epicgames.com/en-US/p/{slug}",
                    platforms={PLATFORM_EPIC},
                    text=f"{title}\n{element.get('description', '')}",
                    expires_at=offer.get("endDate"),
                )
            )
        return games

    @staticmethod
    def _active_free_offer(element: dict, now: datetime) -> dict | None:
        """Return the active 100%-off promotion for an Epic catalog element, if any."""
        groups = (element.get("promotions") or {}).get("promotionalOffers") or []
        for group in groups:
            for offer in group.get("promotionalOffers", []):
                if offer.get("discountSetting", {}).get("discountPercentage") != 0:
                    continue
                start = _parse_iso(offer.get("startDate"))
                end = _parse_iso(offer.get("endDate"))
                if start and end and start <= now <= end:
                    return offer
        return None

    @staticmethod
    def _slug(element: dict) -> str | None:
        """Extract the store page slug used to build the public URL."""
        for mapping in element.get("offerMappings") or []:
            page = mapping.get("page") or {}
            slug = page.get("slug") or mapping.get("pageSlug")
            if slug:
                return slug
        slug = element.get("productSlug") or element.get("urlSlug")
        if slug:
            return slug.removesuffix("/home")
        return None


def build_default_sources() -> list[FreeGameSource]:
    """Return the ordered list of sources the plugin should poll.

    Order matters: earlier sources win the cross-source title dedupe, so the
    authoritative (Epic) and direct-link (GamerPower) sources are listed before
    the Bluesky aggregator, whose links point at Reddit threads.
    """
    return [EpicStoreSource(), GamerPowerSource(), BlueskySource()]


def extract_steam_id(url: str) -> str | None:
    """Extract the Steam App ID from a store URL, if present."""
    match = re.search(r"store\.steampowered\.com/app/(\d+)", url)
    if match:
        return match.group(1)
    return None


def url_domain(url: str) -> str:
    """Return the lowercased hostname of ``url`` (empty string on failure)."""
    return urlparse(url).netloc.lower()
