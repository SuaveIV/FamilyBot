"""Golden tests for ``family_utils.format_message``.

The expected output in ``data/format_message_golden.json`` was captured from the original
sequential implementation, then verified byte-identical after it was rewritten to fetch app
details and ITAD prices concurrently. Each scenario pins behaviour that is easy to break:
the per-failure "Unknown Game" suffixes, wishlist ordering, duplicate app ids, the
pre-populated cache path, and the >1900-character short retry.

Regenerate deliberately (and review the diff) with:

    UPDATE_GOLDEN=1 python -m pytest tests/test_format_message.py
"""

import asyncio
import json
import os
from pathlib import Path

import aiohttp
import pytest

from familybot.lib import family_utils

GOLDEN_PATH = Path(__file__).parent / "fixtures" / "format_message_golden.json"

STEAM_USER_A = "76561198000000001"
STEAM_USER_B = "76561198000000002"

APP_OK = "1001"
APP_SALE = "1002"
APP_NO_SUCCESS = "1003"
APP_BAD_JSON = "1004"
APP_TRANSPORT = "1005"
APP_NO_PRICE = "1006"
APP_MISSING_NAME = "1007"

PAYLOADS = {
    APP_OK: {
        "name": "Half-Life 3",
        "price_overview": {
            "discount_percent": 0,
            "final_formatted": "$59.99",
            "final": 5999,
        },
    },
    APP_SALE: {
        "name": "Portal 3",
        "price_overview": {
            "discount_percent": 75,
            "final_formatted": "$4.99",
            "final": 499,
        },
    },
    APP_NO_PRICE: {"name": "Free Game", "categories": []},
    APP_MISSING_NAME: {"categories": []},
}


class StubResponse:
    """Stand in for an aiohttp response, keyed by the app id in the URL."""

    def __init__(self, app_id: str) -> None:
        self._app_id = app_id

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self) -> None:
        if self._app_id == APP_TRANSPORT:
            msg = "simulated transport failure"
            raise aiohttp.ClientError(msg)

    async def text(self) -> str:
        if self._app_id == APP_BAD_JSON:
            return "{not valid json"
        if self._app_id == APP_NO_SUCCESS:
            return json.dumps({self._app_id: {"success": False}})
        payload = {"success": True, "data": PAYLOADS[self._app_id]}
        return json.dumps({self._app_id: payload})


class StubSession:
    """Minimal aiohttp.ClientSession replacement; never touches the network."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, url: str, **_kwargs) -> StubResponse:
        return StubResponse(url.split("appids=")[1].split("&")[0])


def _stub_lowest_price(app_id: int) -> str:
    return {1001: "$9.99", 1002: "$2.49"}.get(app_id, "N/A")


def _wishlist(*app_ids: str) -> list:
    return [(app_id, [STEAM_USER_A, STEAM_USER_B]) for app_id in app_ids]


SCENARIOS = {
    "empty": lambda: ([], False, None),
    "single_ok": lambda: (_wishlist(APP_OK), False, None),
    "single_ok_short": lambda: (_wishlist(APP_OK), True, None),
    "sale": lambda: (_wishlist(APP_SALE), False, None),
    "sale_short": lambda: (_wishlist(APP_SALE), True, None),
    "no_price_overview": lambda: (_wishlist(APP_NO_PRICE), False, None),
    "missing_name": lambda: (_wishlist(APP_MISSING_NAME), False, None),
    "failure_success_false": lambda: (_wishlist(APP_NO_SUCCESS), False, None),
    "failure_bad_json": lambda: (_wishlist(APP_BAD_JSON), False, None),
    "failure_transport": lambda: (_wishlist(APP_TRANSPORT), False, None),
    "mixed": lambda: (
        _wishlist(APP_OK, APP_SALE, APP_NO_SUCCESS, APP_BAD_JSON, APP_TRANSPORT),
        False,
        None,
    ),
    "duplicates": lambda: (_wishlist(APP_OK, APP_OK, APP_SALE), False, None),
    "unknown_user": lambda: ([(APP_OK, ["76561198999999999"])], False, None),
    "pre_cached": lambda: (_wishlist(APP_OK), False, {APP_OK: PAYLOADS[APP_OK]}),
    "many_triggers_recursion": lambda: (_wishlist(*([APP_OK] * 40)), False, None),
}


@pytest.fixture
def patched(monkeypatch):
    """Return family_utils with the network and config-dependent bits replaced."""
    monkeypatch.setattr(aiohttp, "ClientSession", StubSession)
    monkeypatch.setattr(family_utils, "get_lowest_price", _stub_lowest_price)
    # An empty mapping renders every member as "Unknown User(<id>)", so golden output does
    # not depend on whichever config.yml happens to be present.
    monkeypatch.setattr(family_utils, "FAMILY_USER_DICT", {})
    return family_utils


def _read_golden() -> dict:
    if not GOLDEN_PATH.exists():
        return {}
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _write_golden(name: str, message: str) -> None:
    golden = _read_golden()
    golden[name] = message
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(
        json.dumps(golden, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _render(module, items, short, cached) -> str:
    return asyncio.run(module.format_message(items, short=short, cached_data=cached))


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_matches_golden(patched, name):
    items, short, cached = SCENARIOS[name]()
    actual = _render(patched, items, short, cached)

    if os.environ.get("UPDATE_GOLDEN"):
        _write_golden(name, actual)
        return

    golden = _read_golden()
    assert name in golden, (
        f"{GOLDEN_PATH.name} has no entry for {name!r}; regenerate with UPDATE_GOLDEN=1"
    )
    assert actual == golden[name], f"output drifted for scenario {name!r}"


@pytest.mark.parametrize(
    ("scenario", "suffix"),
    [
        ("failure_success_false", "(Details Unavailable)"),
        ("failure_bad_json", "(Data Error)"),
        ("failure_transport", "(API Error)"),
    ],
)
def test_failure_kind_maps_to_its_suffix(patched, scenario, suffix):
    items, short, cached = SCENARIOS[scenario]()
    assert suffix in _render(patched, items, short, cached)


def test_empty_wishlist_returns_placeholder(patched):
    expected = "# 📝 Family Wishlist \nNo common wishlist items found to display."
    assert _render(patched, [], False, None) == expected


def test_short_mode_omits_price_breakdown(patched):
    items, _, cached = SCENARIOS["sale"]()
    message = _render(patched, items, True, cached)

    assert "The game is on sale at $4.99 (-75%)" in message
    assert "per person" not in message
    assert "The lowest price ever was" not in message


def test_long_mode_renders_per_person_and_lowest(patched):
    items, _, cached = SCENARIOS["sale"]()
    message = _render(patched, items, False, cached)

    assert "which is 2.5$ per person" in message
    assert "The lowest price ever was $2.49$" in message


def test_duplicate_app_ids_render_one_block_each(patched):
    items, _, cached = SCENARIOS["duplicates"]()
    message = _render(patched, items, False, cached)

    assert message.count("Half-Life 3") == 2
    assert message.count("Portal 3") == 1


def test_warm_cache_skips_the_network(patched, monkeypatch):
    def explode(*_args, **_kwargs):
        msg = "format_message must not fetch when the cache is warm"
        raise AssertionError(msg)

    # _prefetch_details still runs, but with an empty list; _fetch_app_details is what
    # actually performs a request, so it must never be reached.
    monkeypatch.setattr(patched, "_fetch_app_details", explode)
    items, _, cached = SCENARIOS["pre_cached"]()

    assert "Half-Life 3" in _render(patched, items, True, cached)


def test_mapped_members_render_their_friendly_name(patched, monkeypatch):
    monkeypatch.setattr(
        patched, "FAMILY_USER_DICT", {STEAM_USER_A: "Alice", STEAM_USER_B: "Bob"}
    )
    items, _, cached = SCENARIOS["single_ok"]()

    assert "Alice, Bob want" in _render(patched, items, True, cached)

