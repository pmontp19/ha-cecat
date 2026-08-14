"""Tests for the cecat sensor entities (docs/05-implementation-plan.md T6).

Every acceptance criterion of T6 (lines 174-185) has an assertion here. No
network: ``aioresponses`` intercepts the fetch the first refresh makes, and
the entry is set up through the real ``async_setup_entry`` so the entities
land on the state machine exactly as a user's instance would build them.

The reconciliation key ``(acronym, phase)`` is the criterion that fails if
the state were indexed by acronym alone: ``dos_procicat_SYNTHETIC`` must
count two and carry both rows in the ``plans`` attribute. The reserved
string ``unknown`` must never appear on ``max_phase``, not even for the
unrecognised-phase fixture (docs/03 §3.1 criterion 6a).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import custom_components.cecat as cecat_module
import pytest
from aioresponses import aioresponses
from custom_components.cecat import PLATFORMS
from custom_components.cecat.const import BASE_URL, DOMAIN, PARAMS
from custom_components.cecat.coordinator import CecatCoordinator
from custom_components.cecat.models import CecatState
from custom_components.cecat.sensor import (
    LastUpdatedSensor,
    MaxPhaseSensor,
    PlansSensor,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import async_get_platforms
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

from tests.conftest import load_fixture

CECAT_URL = URL(BASE_URL).with_query(PARAMS)
LAST_MODIFIED = "Thu, 06 Aug 2026 09:20:17 GMT"

# Captured before conftest's autouse patch replaces the module attribute, so
# the sensor tests can restore the real setup and exercise the platform
# forward for real.
_REAL_ASYNC_SETUP_ENTRY = cecat_module.async_setup_entry

# The nine fields of the ``plans`` attribute schema (docs/03 §3.2).
PLAN_ITEM_FIELDS = {
    "acronym",
    "name",
    "phase",
    "phase_raw",
    "activated",
    "started_at",
    "started_at_source",
    "description",
    "communique_url",
}

# Every fixture with its expected aggregated ``max_phase``: feeds criterion
# 12 ("never the reserved unknown, in any fixture") with the whole corpus.
ALL_FIXTURES: list[tuple[str, str]] = [
    ("buit_2026_06_16", "none"),
    ("prealerta_2024_12_02", "prealerta"),
    ("alerta_2026_08_06", "alerta"),
    ("camps_sistema_2026_08_06", "alerta"),
    ("pdf_url_accents_2026_07_03", "alerta"),
    ("dos_plans_2026_01_19", "alerta"),
    ("dos_procicat_SYNTHETIC", "alerta"),
    ("emergencia_SYNTHETIC", "emergencia"),
    ("emergencia_plaactivat_rar_SYNTHETIC", "emergencia"),
    ("fase_desconeguda_SYNTHETIC", "unrecognized"),
    ("camps_absents_SYNTHETIC", "alerta"),
]


async def _setup_entry(
    hass: HomeAssistant,
    mock_http: aioresponses,
    rows: list[dict[str, Any]],
    headers: dict[str, str] | None = None,
) -> MockConfigEntry:
    """Mock one fetch and set up a cecat entry through the real path."""
    mock_http.get(CECAT_URL, payload=rows, headers=headers or {})
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    """Resolve a sensor's entity_id from its unique id."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id is not None
    return entity_id


def _entities(hass: HomeAssistant) -> dict[str, Any]:
    """The live cecat sensor entity objects, by entity_id."""
    platforms = async_get_platforms(hass, DOMAIN)
    for platform in platforms:
        if platform.domain == "sensor":
            return dict(platform.entities)
    raise AssertionError("cecat sensor platform not found")


# ---------------------------------------------------------------------------
# Criterion 1: the count entity is `plans`, never `active_plans`, and counts
# every phase, prealerta included
# ---------------------------------------------------------------------------


async def test_count_entity_is_plans_not_active_plans(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The count entity has translation_key `plans` and a prealerta counts."""
    entry = await _setup_entry(hass, mock_http, load_fixture("prealerta_2024_12_02"))

    assert PLATFORMS  # the sensor platform was forwarded
    entity_id = _entity_id(hass, entry, "plans")
    assert entity_id == "sensor.proteccio_civil_catalunya_plans"
    assert "active" not in entity_id
    entity = _entities(hass)[entity_id]
    assert entity.translation_key == "plans"
    # A prealerta row is counted: any phase, not only activated plans.
    assert hass.states.get(entity_id).state == "1"


# ---------------------------------------------------------------------------
# Criterion 2: `buit` gives none / 0, and no entity is unavailable
# ---------------------------------------------------------------------------


async def test_empty_feed_is_none_zero_and_available(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """`[]` is a valid state: `none`, `0`, and nothing on `unavailable`."""
    entry = await _setup_entry(
        hass,
        mock_http,
        load_fixture("buit_2026_06_16"),
        {"Last-Modified": LAST_MODIFIED},
    )

    states = [
        hass.states.get(_entity_id(hass, entry, key))
        for key in ("max_phase", "plans", "last_updated")
    ]
    assert [state.state for state in states] == [
        "none",
        "0",
        "2026-08-06T09:20:17+00:00",
    ]
    assert all(state.state != "unavailable" for state in states)


# ---------------------------------------------------------------------------
# Criterion 3: prealerta gives max_phase=prealerta, plans=1, activated=0
# ---------------------------------------------------------------------------


async def test_prealerta_counts_as_phase_not_as_activated(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A PREALERTA row with plaactivat=NO counts 1 plan, 0 activated."""
    entry = await _setup_entry(hass, mock_http, load_fixture("prealerta_2024_12_02"))

    assert hass.states.get(_entity_id(hass, entry, "max_phase")).state == "prealerta"
    plans = hass.states.get(_entity_id(hass, entry, "plans"))
    assert plans.state == "1"
    assert plans.attributes["activated"] == 0
    assert plans.attributes["prealerta"] == 1


# ---------------------------------------------------------------------------
# Criterion 4: the plans element carries the nine fields of §3.2
# ---------------------------------------------------------------------------


async def test_plans_element_has_the_nine_schema_fields(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The per-row object has exactly the §3.2 fields, with real values."""
    entry = await _setup_entry(hass, mock_http, load_fixture("alerta_2026_08_06"))

    plans = hass.states.get(_entity_id(hass, entry, "plans"))
    [item] = plans.attributes["plans"]
    assert set(item) == PLAN_ITEM_FIELDS
    assert item["acronym"] == "INUNCAT"
    assert item["name"] == "Inundacions"
    assert item["phase"] == "alerta"
    assert item["phase_raw"] == "ALERTA"
    assert item["activated"] is True
    # Bare projection: started_at comes from fasedatahora (05/08 13:18 CEST).
    assert item["started_at"] == "2026-08-05T11:18:00+00:00"
    assert item["started_at_source"] == "fasedatahora"
    assert item["description"] == "Avís intensitat pluja fins al 04/08  -"
    assert item["communique_url"].endswith(
        "I-125912_ACTUALITZACIO--ACTIVAT_INUNCAT_202608061114.pdf"
    )


# ---------------------------------------------------------------------------
# Criterion 5: dos_plans counts 2, attribute ordered INUNCAT before NEUCAT
# ---------------------------------------------------------------------------


async def test_dos_plans_sorted_by_acronym_and_phase(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """Two plans in ALERTA: count 2, attribute order INUNCAT then NEUCAT."""
    entry = await _setup_entry(hass, mock_http, load_fixture("dos_plans_2026_01_19"))

    plans = hass.states.get(_entity_id(hass, entry, "plans"))
    assert plans.state == "2"
    assert [(p["acronym"], p["phase"]) for p in plans.attributes["plans"]] == [
        ("INUNCAT", "alerta"),
        ("NEUCAT", "alerta"),
    ]


# ---------------------------------------------------------------------------
# Criterion 6: two rows of the same acronym are two entries, both visible
# ---------------------------------------------------------------------------


async def test_dos_procicat_keeps_both_rows_in_deterministic_order(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """Same acronym, different phases: count 2, both rows, stable order.

    This is the criterion that fails if the state is indexed by acronym
    alone: one of the two PROCICAT rows would be lost.
    """
    entry = await _setup_entry(hass, mock_http, load_fixture("dos_procicat_SYNTHETIC"))

    plans = hass.states.get(_entity_id(hass, entry, "plans"))
    assert plans.state == "2"
    items = plans.attributes["plans"]
    assert [(p["acronym"], p["phase"]) for p in items] == [
        ("PROCICAT", "prealerta"),
        ("PROCICAT", "alerta"),
    ]
    assert plans.attributes["activated"] == 1  # only the ALERTA row
    assert plans.attributes["prealerta"] == 1


# ---------------------------------------------------------------------------
# Criterion 7: EMERGÈNCIA (never observed live) aggregates to emergencia
# ---------------------------------------------------------------------------


async def test_emergencia_synthetic_aggregates_to_emergencia(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The documented-but-never-observed phase parses and aggregates."""
    entry = await _setup_entry(hass, mock_http, load_fixture("emergencia_SYNTHETIC"))

    max_phase = hass.states.get(_entity_id(hass, entry, "max_phase"))
    assert max_phase.state == "emergencia"
    assert max_phase.attributes["acronyms"] == ["INUNCAT"]
    assert max_phase.attributes["total_plans"] == 1


# ---------------------------------------------------------------------------
# Criterion 8: an unrecognised phase surfaces as unrecognized + phase_raw
# ---------------------------------------------------------------------------


async def test_unrecognised_phase_shows_phase_raw_in_plans(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """`plafase: MÀXIMA` gives max_phase=unrecognized with the literal visible."""
    rows = load_fixture("fase_desconeguda_SYNTHETIC")
    entry = await _setup_entry(hass, mock_http, rows)

    assert hass.states.get(_entity_id(hass, entry, "max_phase")).state == "unrecognized"
    plans = hass.states.get(_entity_id(hass, entry, "plans"))
    [item] = plans.attributes["plans"]
    assert item["phase"] == "unrecognized"
    assert item["phase_raw"] == "MÀXIMA"


# ---------------------------------------------------------------------------
# Criterion 9: an unrecognised row never beats a known phase, no exception
# ---------------------------------------------------------------------------


async def test_unrecognised_row_does_not_beat_alerta(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A feed with MÀXIMA and ALERTA gives `alerta`, and setup survives.

    The aggregation filters to PHASE_ORDER before ordering (docs/04 §4), so
    `max()` never receives the orderless value: no ValueError, no lost cycle.
    """
    rows = [
        *load_fixture("fase_desconeguda_SYNTHETIC"),
        *load_fixture("alerta_2026_08_06"),
    ]
    entry = await _setup_entry(hass, mock_http, rows)

    assert hass.states.get(_entity_id(hass, entry, "max_phase")).state == "alerta"
    plans = hass.states.get(_entity_id(hass, entry, "plans"))
    assert plans.state == "2"
    assert {p["phase"] for p in plans.attributes["plans"]} == {"unrecognized", "alerta"}


# ---------------------------------------------------------------------------
# Criterion 10: last_updated parses Last-Modified; None when absent
# ---------------------------------------------------------------------------


async def test_last_updated_parses_header_with_timezone(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A Last-Modified header becomes a tz-aware datetime state."""
    entry = await _setup_entry(
        hass,
        mock_http,
        load_fixture("alerta_2026_08_06"),
        {"Last-Modified": LAST_MODIFIED},
    )

    entity_id = _entity_id(hass, entry, "last_updated")
    assert hass.states.get(entity_id).state == "2026-08-06T09:20:17+00:00"
    native = _entities(hass)[entity_id].native_value
    assert native == datetime(2026, 8, 6, 9, 20, 17, tzinfo=UTC)


async def test_last_updated_is_none_without_header(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """No Last-Modified header: the diagnostic reads `None` (state unknown)."""
    entry = await _setup_entry(hass, mock_http, load_fixture("alerta_2026_08_06"))

    entity_id = _entity_id(hass, entry, "last_updated")
    assert _entities(hass)[entity_id].native_value is None
    assert hass.states.get(entity_id).state == "unknown"


# ---------------------------------------------------------------------------
# Criterion 11: ENUM options include unrecognized; last_updated is DIAGNOSTIC
# ---------------------------------------------------------------------------


async def test_enum_options_and_diagnostic_category(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The ENUM lists all five states; last_updated is a diagnostic entity."""
    entry = await _setup_entry(hass, mock_http, load_fixture("buit_2026_06_16"))

    entities = _entities(hass)
    max_phase = entities[_entity_id(hass, entry, "max_phase")]
    assert max_phase.options == [
        "none",
        "prealerta",
        "alerta",
        "emergencia",
        "unrecognized",
    ]
    last_updated = entities[_entity_id(hass, entry, "last_updated")]
    assert last_updated.entity_category is EntityCategory.DIAGNOSTIC


# ---------------------------------------------------------------------------
# Criterion 12: max_phase is never the reserved `unknown`, in any fixture
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("fixture_name", "expected"), ALL_FIXTURES)
async def test_max_phase_never_unknown_nor_unavailable(
    hass: HomeAssistant,
    mock_http: aioresponses,
    fixture_name: str,
    expected: str,
) -> None:
    """Across the whole corpus the state machine never holds `unknown`."""
    entry = await _setup_entry(hass, mock_http, load_fixture(fixture_name))

    state = hass.states.get(_entity_id(hass, entry, "max_phase"))
    assert state.state not in ("unknown", "unavailable")
    assert state.state == expected


# ---------------------------------------------------------------------------
# Defensive branches: no data yet, unreadable or tz-less Last-Modified
# ---------------------------------------------------------------------------


def _bare_entry(hass: HomeAssistant) -> MockConfigEntry:
    """A registered cecat entry whose coordinator is never refreshed."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    return entry


async def test_no_data_yet_degrades_to_none_zero(hass: HomeAssistant) -> None:
    """Before any successful fetch the states are none/0/None, not raises."""
    coord = CecatCoordinator(hass, _bare_entry(hass))
    coord.data = None
    try:
        assert MaxPhaseSensor(coord).native_value == "none"
        assert MaxPhaseSensor(coord).extra_state_attributes == {
            "acronyms": [],
            "total_plans": 0,
        }
        assert PlansSensor(coord).native_value == 0
        assert PlansSensor(coord).extra_state_attributes == {
            "plans": [],
            "activated": 0,
            "prealerta": 0,
        }
        assert LastUpdatedSensor(coord).native_value is None
    finally:
        await coord.async_shutdown()


async def test_last_updated_unreadable_header_degrades_to_none(
    hass: HomeAssistant,
) -> None:
    """A Last-Modified that is not RFC 822 reads as None, never raises."""
    coord = CecatCoordinator(hass, _bare_entry(hass))
    coord.data = CecatState(activations=(), last_modified="not-an-rfc822-date")
    try:
        assert LastUpdatedSensor(coord).native_value is None
    finally:
        await coord.async_shutdown()


async def test_last_updated_tz_less_header_gets_utc(hass: HomeAssistant) -> None:
    """A naive Last-Modified is still a timestamp: UTC is assumed."""
    coord = CecatCoordinator(hass, _bare_entry(hass))
    coord.data = CecatState(activations=(), last_modified="Thu, 06 Aug 2026 09:20:17")
    try:
        assert LastUpdatedSensor(coord).native_value == datetime(
            2026, 8, 6, 9, 20, 17, tzinfo=UTC
        )
    finally:
        await coord.async_shutdown()


# ---------------------------------------------------------------------------
# Device and attribution (docs/03 §3.5)
# ---------------------------------------------------------------------------


async def test_service_device_and_attribution(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """All entities share one SERVICE device and the licence attribution."""
    entry = await _setup_entry(hass, mock_http, load_fixture("alerta_2026_08_06"))

    device = dr.async_get(hass).async_get_device({(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.entry_type is dr.DeviceEntryType.SERVICE

    for key in ("max_phase", "plans", "last_updated"):
        state = hass.states.get(_entity_id(hass, entry, key))
        assert state.attributes["attribution"].startswith("Generalitat de Catalunya")
