"""Tests for the cecat diagnostics export (docs/05 T10, docs/03 §3.6).

The export contract of §3.6, field by field: the redacted config entry, the
raw response of the last successful cycle, the ``Last-Modified`` in force,
the three accumulated sets of unrecognised literals, and the consecutive
failure count. ``unknown_activated`` gets its own test because it is the
only channel that can show an unexpected ``plaactivat`` literal from the
field (docs/03 §7 criterion 5b): the sensor attributes deliberately drop
``activated_raw``.

No network: ``aioresponses`` feeds the fetches and the entry is set up
through the real ``async_setup_entry`` so ``entry.runtime_data`` is the live
coordinator, exactly what the diagnostics handler reads.
"""

from __future__ import annotations

import json
from typing import Any

from aioresponses import aioresponses
from custom_components.cecat.const import BASE_URL, DOMAIN, PARAMS
from custom_components.cecat.coordinator import CecatCoordinator
from custom_components.cecat.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

from tests.conftest import load_fixture

CECAT_URL = URL(BASE_URL).with_query(PARAMS)
LAST_MODIFIED = "Thu, 06 Aug 2026 09:20:17 GMT"

# The exact §3.6 contract: the download must carry these keys and no others,
# so a stray field (or a renamed one) fails the shape check.
EXPORT_FIELDS = {
    "entry",
    "last_raw_response",
    "last_modified",
    "unknown_phases",
    "unknown_acronyms",
    "unknown_activated",
    "consecutive_failures",
}

# One row tripping all three unknown-literal valves at once, the same
# construction as test_coordinator.test_three_unknown_sets_are_independent.
ALL_UNKNOWN_ROW: list[dict[str, Any]] = [
    {"plaacronim": "NOPLA", "plafase": "MÀXIMA", "plaactivat": "true"}
]


async def _setup(
    hass: HomeAssistant,
    mock_http: aioresponses,
    payload: Any,
    *,
    options: dict[str, Any] | None = None,
) -> MockConfigEntry:
    """Set up a full cecat entry served ``payload`` and return the entry."""
    mock_http.get(CECAT_URL, payload=payload, headers={"Last-Modified": LAST_MODIFIED})
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _export(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, Any]:
    """Run the diagnostics handler against the entry's live coordinator."""
    return dict(await async_get_config_entry_diagnostics(hass, entry))


# ---------------------------------------------------------------------------
# Criterion 1: the export carries the full §3.6 contract
# ---------------------------------------------------------------------------


async def test_export_carries_the_full_contract(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """All three unknown sets, the raw rows, Last-Modified and the count."""
    entry = await _setup(hass, mock_http, ALL_UNKNOWN_ROW)
    export = await _export(hass, entry)

    assert set(export) == EXPORT_FIELDS
    assert export["last_raw_response"] == ALL_UNKNOWN_ROW
    assert export["last_modified"] == LAST_MODIFIED
    assert export["unknown_phases"] == ["MÀXIMA"]
    assert export["unknown_acronyms"] == ["NOPLA"]
    assert export["unknown_activated"] == ["true"]
    assert export["consecutive_failures"] == 0


async def test_raw_response_is_verbatim(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The raw rows keep every field the parser never reads, byte for byte.

    ``camps_sistema_2026_08_06`` is the fixture with the Socrata system
    columns (``:id``, ``:created_at``, ...): the export must carry them
    exactly as decoded, because "raw, dirty text" is the whole point of the
    field (§3.6).
    """
    rows = load_fixture("camps_sistema_2026_08_06")
    entry = await _setup(hass, mock_http, rows)
    export = await _export(hass, entry)

    assert export["last_raw_response"] == rows


async def test_config_entry_has_nothing_to_redact(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """Verified: no coordinates, no secrets; data is empty, options in clear.

    ``data={}`` by construction (``config_flow.py``) and the only option is
    ``scan_interval_min``, so the redaction set is empty and the entry
    passes through unchanged.
    """
    entry = await _setup(
        hass,
        mock_http,
        load_fixture("buit_2026_06_16"),
        options={"scan_interval_min": 15},
    )
    export = await _export(hass, entry)

    assert not TO_REDACT
    assert export["entry"]["data"] == {}
    assert export["entry"]["options"] == {"scan_interval_min": 15}


async def test_export_is_json_serializable(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The download path JSON-encodes the export; it must never raise.

    The three unknown sets are converted to sorted lists for exactly this
    reason: a bare ``set`` would sink ``json.dumps``.
    """
    entry = await _setup(hass, mock_http, ALL_UNKNOWN_ROW)
    export = await _export(hass, entry)

    assert json.loads(json.dumps(export)) == export


# ---------------------------------------------------------------------------
# Criterion 2: a row with plaactivat absent leaves "<absent>" in the export
# ---------------------------------------------------------------------------


async def test_absent_plaactivat_registers_as_absent(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The absent field is the sentinel ``<absent>``; ``Si``/`` SI `` are not.

    ``emergencia_plaactivat_rar_SYNTHETIC`` carries the three variants with
    distinct acronyms so all three resolve: only the absent one registers.
    """
    entry = await _setup(
        hass, mock_http, load_fixture("emergencia_plaactivat_rar_SYNTHETIC")
    )
    export = await _export(hass, entry)

    assert export["unknown_activated"] == ["<absent>"]


# ---------------------------------------------------------------------------
# Failure streak and 304: what the export shows while things go wrong
# ---------------------------------------------------------------------------


async def test_export_reflects_failure_streak_and_keeps_last_good_cycle(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """Failures count; the raw rows and Last-Modified stay at the last 200."""
    entry = await _setup(hass, mock_http, ALL_UNKNOWN_ROW)
    mock_http.get(CECAT_URL, status=500)
    mock_http.get(CECAT_URL, status=503)
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    export = await _export(hass, entry)

    assert export["consecutive_failures"] == 2
    assert export["last_raw_response"] == ALL_UNKNOWN_ROW
    assert export["last_modified"] == LAST_MODIFIED


async def test_304_keeps_the_last_raw_response(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A 304 changes nothing: the export still shows the last 200's rows."""
    rows = load_fixture("alerta_2026_08_06")
    entry = await _setup(hass, mock_http, rows)
    mock_http.get(CECAT_URL, status=304)
    await entry.runtime_data.async_refresh()
    export = await _export(hass, entry)

    assert export["last_raw_response"] == rows
    assert export["last_modified"] == LAST_MODIFIED


async def test_export_before_any_successful_cycle(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """Before a first success the raw fields are ``None``, the count is 1.

    The coordinator is wired by hand because a first refresh that fails
    leaves the entry in setup retry: the handler must still produce an
    honest export, not raise.
    """
    mock_http.get(CECAT_URL, status=500)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = CecatCoordinator(hass, entry)
    entry.runtime_data = coordinator
    await coordinator.async_refresh()
    export = await _export(hass, entry)

    assert export["last_raw_response"] is None
    assert export["last_modified"] is None
    assert export["consecutive_failures"] == 1
    assert export["unknown_phases"] == []
    assert export["unknown_acronyms"] == []
    assert export["unknown_activated"] == []
