"""Tests for the cecat coordinator (docs/05-implementation-plan.md T5).

Every acceptance criterion of T5 (lines 154-162) and the brief's cycle criteria
have an assertion here. No network: ``aioresponses`` intercepts the HA client
session the coordinator fetches through, and the ``FakeClock`` drives the
stale-data window without real time.

The reconciliation key ``(acronym, phase)`` is the criterion that fails if the
state were indexed by acronym alone: ``dos_procicat_SYNTHETIC`` must surface as
two entries. A failed cycle must never drop a plan, and a 304 must never
recompute. Those three invariants anchor the rest.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aioresponses import aioresponses
from custom_components.cecat.const import BASE_URL, DOMAIN, PARAMS
from custom_components.cecat.coordinator import CecatCoordinator
from custom_components.cecat.models import Phase
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

from tests.conftest import FakeClock, load_fixture

CECAT_URL = URL(BASE_URL).with_query(PARAMS)
LAST_MODIFIED = "Thu, 06 Aug 2026 09:20:17 GMT"
LAST_MODIFIED_2 = "Fri, 07 Aug 2026 10:00:00 GMT"


def _sent_if_modified_since(mocked: aioresponses) -> list[str | None]:
    """Collect the ``If-Modified-Since`` header from every GET, in call order."""
    sent: list[str | None] = []
    for (method, _url), calls in mocked.requests.items():
        if method != "GET":
            continue
        for call in calls:
            sent.append(dict(call.kwargs.get("headers") or {}).get("If-Modified-Since"))
    return sent


def _make_entry(
    hass: HomeAssistant, *, options: dict[str, Any] | None = None
) -> MockConfigEntry:
    """Build and register a cecat MockConfigEntry, optionally with options."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {})
    entry.add_to_hass(hass)
    return entry


# ---------------------------------------------------------------------------
# Cycle 1 (200): state populated, last_modified stored
# ---------------------------------------------------------------------------


async def test_first_cycle_populates_state_and_last_modified(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A 200 builds ``CecatState`` and stores ``Last-Modified`` for the next call."""
    mock_http.get(
        CECAT_URL,
        payload=load_fixture("alerta_2026_08_06"),
        headers={"Last-Modified": LAST_MODIFIED},
    )
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()

    assert len(coord.data.activations) == 1
    assert coord.data.activations[0].acronym == "INUNCAT"
    assert coord.data.last_modified == LAST_MODIFIED
    assert coord.last_modified == LAST_MODIFIED
    # First cycle seeds the reconciliation baseline, keyed by (acronym, phase).
    assert ("INUNCAT", Phase.ALERTA) in coord.previous
    assert coord.is_first_refresh is False


# ---------------------------------------------------------------------------
# Cycle 2 (304): state preserved, last_modified untouched, If-Modified-Since sent
# ---------------------------------------------------------------------------


async def test_304_preserves_state_and_does_not_touch_last_modified(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A 304 returns ``self.data`` intact and leaves ``_last_modified`` as-is."""
    mock_http.get(
        CECAT_URL,
        payload=load_fixture("alerta_2026_08_06"),
        headers={"Last-Modified": LAST_MODIFIED},
    )
    mock_http.get(CECAT_URL, status=304)
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()  # cycle 1: 200
    before = coord.data
    await coord.async_refresh()  # cycle 2: 304

    assert coord.data is before  # the exact same object, not a recompute
    assert coord.data.last_modified == LAST_MODIFIED
    assert coord.last_modified == LAST_MODIFIED
    assert _sent_if_modified_since(mock_http)[1] == LAST_MODIFIED


# ---------------------------------------------------------------------------
# Failed fetch: last_error populated, previous state preserved
# ---------------------------------------------------------------------------


async def test_failed_fetch_populates_last_error_and_preserves_state(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A failed cycle sets ``last_error``, keeps ``self.data`` and ``_previous``."""
    mock_http.get(
        CECAT_URL,
        payload=load_fixture("alerta_2026_08_06"),
        headers={"Last-Modified": LAST_MODIFIED},
    )
    mock_http.get(CECAT_URL, status=500)
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()  # success
    good_state = coord.data
    await coord.async_refresh()  # failure

    assert coord.data is good_state  # HA keeps self.data on UpdateFailed
    assert coord.last_error is not None
    assert coord.consecutive_failures == 1


async def test_failed_cycle_preserves_previous_intact(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A failure never touches ``_previous``: no plan can be lost to a glitch."""
    mock_http.get(
        CECAT_URL,
        payload=load_fixture("dos_procicat_SYNTHETIC"),
        headers={"Last-Modified": LAST_MODIFIED},
    )
    mock_http.get(CECAT_URL, exception=TimeoutError("network gone"))
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()  # two PROCICAT rows
    await coord.async_refresh()  # failure

    assert set(coord.previous) == {
        ("PROCICAT", Phase.PREALERTA),
        ("PROCICAT", Phase.ALERTA),
    }


# ---------------------------------------------------------------------------
# always_update=False: unchanged state stays silent, changed state fires
# ---------------------------------------------------------------------------


async def test_unchanged_state_does_not_notify_listeners(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A 200 with byte-identical content + Last-Modified wakes no listener."""
    body = load_fixture("alerta_2026_08_06")
    mock_http.get(CECAT_URL, payload=body, headers={"Last-Modified": LAST_MODIFIED})
    mock_http.get(CECAT_URL, payload=body, headers={"Last-Modified": LAST_MODIFIED})
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()  # cycle 1

    calls: list[int] = []
    coord.async_add_listener(lambda: calls.append(1))
    try:
        await coord.async_refresh()  # cycle 2: identical content
    finally:
        await coord.async_shutdown()

    assert calls == []  # always_update=False + equal CecatState


async def test_304_does_not_notify_listeners(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A 304 returns ``self.data`` and so never wakes a listener."""
    mock_http.get(
        CECAT_URL,
        payload=load_fixture("alerta_2026_08_06"),
        headers={"Last-Modified": LAST_MODIFIED},
    )
    mock_http.get(CECAT_URL, status=304)
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()

    calls: list[int] = []
    coord.async_add_listener(lambda: calls.append(1))
    try:
        await coord.async_refresh()  # 304
    finally:
        await coord.async_shutdown()

    assert calls == []


async def test_changed_state_notifies_listeners(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A 200 whose content differs fires ``async_update_listeners`` once."""
    mock_http.get(
        CECAT_URL,
        payload=load_fixture("alerta_2026_08_06"),
        headers={"Last-Modified": LAST_MODIFIED},
    )
    mock_http.get(
        CECAT_URL,
        payload=load_fixture("dos_procicat_SYNTHETIC"),
        headers={"Last-Modified": LAST_MODIFIED_2},
    )
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()

    calls: list[int] = []
    coord.async_add_listener(lambda: calls.append(1))
    try:
        await coord.async_refresh()
    finally:
        await coord.async_shutdown()

    assert len(calls) == 1


# ---------------------------------------------------------------------------
# (acronym, phase) key: two PROCICAT rows are two entries
# ---------------------------------------------------------------------------


async def test_dos_procicat_yields_two_entries_not_one(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The reconciliation key is the pair, so two PROCICAT rows survive (AD-5)."""
    mock_http.get(CECAT_URL, payload=load_fixture("dos_procicat_SYNTHETIC"))
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()

    assert len(coord.data.activations) == 2
    assert set(coord.data.by_key) == {
        ("PROCICAT", Phase.PREALERTA),
        ("PROCICAT", Phase.ALERTA),
    }


# ---------------------------------------------------------------------------
# Valid [] replaces _previous with an empty dict
# ---------------------------------------------------------------------------


async def test_empty_response_replaces_previous_with_empty_dict(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A valid ``[]`` is a deactivation: ``_previous`` becomes empty, not kept."""
    mock_http.get(
        CECAT_URL,
        payload=load_fixture("alerta_2026_08_06"),
        headers={"Last-Modified": LAST_MODIFIED},
    )
    mock_http.get(CECAT_URL, payload=[], headers={"Last-Modified": LAST_MODIFIED_2})
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()  # one plan
    assert coord.previous

    await coord.async_refresh()  # valid empty

    assert coord.previous == {}
    assert coord.data.is_empty


# ---------------------------------------------------------------------------
# Stale-data guard: available flips when the last good fetch is too old
# ---------------------------------------------------------------------------


async def test_fresh_data_is_available(
    hass: HomeAssistant, mock_http: aioresponses, clock: FakeClock, monkeypatch
) -> None:
    """Right after a successful fetch, ``available`` is True."""
    monkeypatch.setattr("custom_components.cecat.coordinator.utcnow", clock)
    mock_http.get(CECAT_URL, payload=load_fixture("alerta_2026_08_06"))
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    coord.last_update_success_time = clock.now  # align to the fake clock

    assert coord.available is True


async def test_stale_data_is_unavailable(
    hass: HomeAssistant, mock_http: aioresponses, clock: FakeClock, monkeypatch
) -> None:
    """Data older than ``max(6 x interval, 1h)`` flips ``available`` to False."""
    monkeypatch.setattr("custom_components.cecat.coordinator.utcnow", clock)
    mock_http.get(CECAT_URL, payload=load_fixture("alerta_2026_08_06"))
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    coord.last_update_success_time = clock.now

    clock.advance(minutes=30)  # default 5 min interval -> floor is 1 h
    assert coord.available is True
    clock.advance(hours=2)  # total 2 h30, well past the 1 h floor
    assert coord.available is False


async def test_stale_window_grows_with_the_interval(
    hass: HomeAssistant, clock: FakeClock, monkeypatch
) -> None:
    """A 15 min interval lifts the floor to 6 x 15 = 90 min (> 1 h)."""
    monkeypatch.setattr("custom_components.cecat.coordinator.utcnow", clock)
    coord = CecatCoordinator(hass, _make_entry(hass, options={"scan_interval": 15}))
    assert coord.update_interval == timedelta(minutes=15)
    coord.last_update_success_time = clock.now

    clock.advance(minutes=80)
    assert coord.available is True  # 80 < 90
    clock.advance(minutes=20)
    assert coord.available is False  # 100 > 90


async def test_available_false_before_any_successful_fetch(
    hass: HomeAssistant, monkeypatch
) -> None:
    """With no successful fetch yet, there is nothing fresh to present."""
    clock = FakeClock(datetime(2026, 8, 6, 11, 49, tzinfo=UTC))
    monkeypatch.setattr("custom_components.cecat.coordinator.utcnow", clock)
    coord = CecatCoordinator(hass, _make_entry(hass))
    assert coord.available is False


# ---------------------------------------------------------------------------
# Unknown literals: one warning per literal, three independent sets
# ---------------------------------------------------------------------------


async def test_unknown_phase_warns_once_across_cycles(
    hass: HomeAssistant,
    mock_http: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unrecognised ``plafase`` warns exactly once, not once per cycle."""
    body = load_fixture("fase_desconeguda_SYNTHETIC")
    for _ in range(2):
        mock_http.get(CECAT_URL, payload=body)
    coord = CecatCoordinator(hass, _make_entry(hass))
    caplog.set_level("WARNING", logger="custom_components.cecat.coordinator")
    await coord.async_refresh()
    await coord.async_refresh()

    phase_warnings = [
        r for r in caplog.records if "Fase de pla no reconeguda" in r.message
    ]
    assert len(phase_warnings) == 1
    assert "MÀXIMA" in phase_warnings[0].message
    assert coord.unknown_phases == {"MÀXIMA"}


async def test_unknown_acronym_warns_once(
    hass: HomeAssistant,
    mock_http: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An acronym outside the registry warns once; the row is still ingested."""
    row: list[dict[str, Any]] = [{"plaacronim": "NOPLA", "plafase": "ALERTA"}]
    for _ in range(2):
        mock_http.get(CECAT_URL, payload=row)
    coord = CecatCoordinator(hass, _make_entry(hass))
    caplog.set_level("WARNING", logger="custom_components.cecat.coordinator")
    await coord.async_refresh()
    await coord.async_refresh()

    acronym_warnings = [r for r in caplog.records if "Pla desconegut" in r.message]
    assert len(acronym_warnings) == 1
    assert "NOPLA" in acronym_warnings[0].message
    assert coord.unknown_acronyms == {"NOPLA"}
    # Unknown acronym is ingested, not dropped; name falls back to the acronym.
    assert coord.data.activations[0].name == "NOPLA"


async def test_unknown_activated_warns_once_per_literal(
    hass: HomeAssistant,
    mock_http: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A ``plaactivat`` that had to be derived warns once per literal.

    ``Si`` and ``" SI "`` are tolerated (no warning); the absent field is the
    only one that warns here, registered as the ``<absent>`` sentinel.
    """
    body = load_fixture("emergencia_plaactivat_rar_SYNTHETIC")
    for _ in range(2):
        mock_http.get(CECAT_URL, payload=body)
    coord = CecatCoordinator(hass, _make_entry(hass))
    caplog.set_level("WARNING", logger="custom_components.cecat.coordinator")
    await coord.async_refresh()
    await coord.async_refresh()

    activated_warnings = [
        r for r in caplog.records if "plaactivat no reconegut" in r.message
    ]
    assert len(activated_warnings) == 1
    assert "<absent>" in activated_warnings[0].message
    assert coord.unknown_activated == {"<absent>"}


async def test_three_unknown_sets_are_independent(
    hass: HomeAssistant,
    mock_http: aioresponses,
) -> None:
    """An unknown phase, acronym and activated value each land in their own set."""
    rows: list[dict[str, Any]] = [
        {"plaacronim": "NOPLA", "plafase": "MÀXIMA", "plaactivat": "true"}
    ]
    mock_http.get(CECAT_URL, payload=rows)
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()

    assert coord.unknown_acronyms == {"NOPLA"}
    assert coord.unknown_phases == {"MÀXIMA"}
    assert coord.unknown_activated == {"true"}


# ---------------------------------------------------------------------------
# Resilience bookkeeping (event firing is T8)
# ---------------------------------------------------------------------------


async def test_three_failures_flip_degraded_flag(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """Three consecutive failures cross the degraded threshold (§8)."""
    for _ in range(3):
        mock_http.get(CECAT_URL, status=500)
    coord = CecatCoordinator(hass, _make_entry(hass))
    for _ in range(3):
        await coord.async_refresh()

    assert coord.consecutive_failures == 3
    assert coord.degraded is True


async def test_success_clears_degraded_after_streak(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A successful fetch resets the streak and the degraded flag."""
    for _ in range(3):
        mock_http.get(CECAT_URL, status=500)
    mock_http.get(CECAT_URL, payload=load_fixture("alerta_2026_08_06"))
    coord = CecatCoordinator(hass, _make_entry(hass))
    for _ in range(3):
        await coord.async_refresh()
    assert coord.degraded is True

    await coord.async_refresh()  # recovery

    assert coord.consecutive_failures == 0
    assert coord.degraded is False


async def test_first_refresh_seeds_previous_silently(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The first cycle seeds ``_previous`` and clears ``is_first_refresh``."""
    mock_http.get(CECAT_URL, payload=load_fixture("alerta_2026_08_06"))
    coord = CecatCoordinator(hass, _make_entry(hass))
    assert coord.is_first_refresh is True

    await coord.async_refresh()

    assert coord.is_first_refresh is False
    assert coord.previous  # seeded, not empty


# ---------------------------------------------------------------------------
# Scan interval: read from options, clamped to bounds, invalid falls back
# ---------------------------------------------------------------------------


def test_scan_interval_defaults_to_five_minutes(hass: HomeAssistant) -> None:
    """No option set -> the documented 5 min default."""
    coord = CecatCoordinator(hass, _make_entry(hass))
    assert coord.update_interval == timedelta(minutes=5)
    assert coord._stale_after == timedelta(hours=1)  # max(6x5min, 1h) = 1h


def test_scan_interval_clamped_to_bounds(hass: HomeAssistant) -> None:
    """Below the floor clamps to 1 min; above the ceiling clamps to 1 h."""
    too_low = CecatCoordinator(hass, _make_entry(hass, options={"scan_interval": 0}))
    too_high = CecatCoordinator(hass, _make_entry(hass, options={"scan_interval": 999}))
    assert too_low.update_interval == timedelta(minutes=1)
    assert too_high.update_interval == timedelta(minutes=60)


def test_scan_interval_invalid_falls_back_to_default(hass: HomeAssistant) -> None:
    """A non-numeric option is ignored: the 5 min default applies."""
    coord = CecatCoordinator(hass, _make_entry(hass, options={"scan_interval": "soon"}))
    assert coord.update_interval == timedelta(minutes=5)
