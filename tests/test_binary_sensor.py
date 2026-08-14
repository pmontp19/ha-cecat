"""Tests for the cecat binary sensor (docs/05-implementation-plan.md T7).

Every acceptance criterion of T7 (lines 195-205) has an assertion here. No
network: ``aioresponses`` feeds the coordinator's first refresh and the real
``async_setup_entry`` runs the whole wiring (coordinator, forward, entity
registration), the same direct-call pattern as ``test_init.py``.

Three anchors, one per trap the entity exists to defuse:

- ``prealerta_2024_12_02`` must read ``off`` **while the maximum phase is
  ``prealerta``: the prealerta is a first-class state, not "not activated"''
  (docs/03-feature-spec.md §3.3).
- Each row of ``emergencia_plaactivat_rar_SYNTHETIC`` loaded alone must read
  ``on``: ``Si``, ``" SI "`` and an absent ``plaactivat`` all resolve through
  ``resolve_activated``, never a literal ``== "SI"`` (AD-6, trap 14).
- The attribute is ``acronyms`` (sorted strings), never ``plans``: that name
  belongs to the object list of ``sensor...._plans`` alone
  (docs/04-architecture.md §6).
"""

from __future__ import annotations

from typing import Any

import pytest
from aioresponses import aioresponses
from custom_components.cecat import async_setup_entry
from custom_components.cecat.binary_sensor import (
    PLAN_ACTIVATED_DESCRIPTION,
    CecatPlanActivatedBinarySensor,
)
from custom_components.cecat.const import BASE_URL, DOMAIN, PARAMS
from custom_components.cecat.models import Phase, max_phase
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

from tests.conftest import load_fixture

CECAT_URL = URL(BASE_URL).with_query(PARAMS)
LAST_MODIFIED = "Thu, 06 Aug 2026 09:20:17 GMT"

RARE_ROWS: list[dict[str, Any]] = load_fixture("emergencia_plaactivat_rar_SYNTHETIC")


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    """Build and register a cecat MockConfigEntry."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    return entry


async def _setup(
    hass: HomeAssistant, mock_http: aioresponses, payload: Any
) -> tuple[MockConfigEntry, str]:
    """Set up a full entry served ``payload`` and return ``(entry, entity_id)``.

    Calls the real ``async_setup_entry`` (the autouse ``_mock_platforms``
    patch only swaps the module attribute, so the imported reference here is
    the original) under the entry's ``setup_lock``, the same guarantee
    ``hass.config_entries.async_setup`` gives in production, so the
    coordinator's first refresh and the platform forward run for real.
    """
    mock_http.get(CECAT_URL, payload=payload, headers={"Last-Modified": LAST_MODIFIED})
    entry = _entry(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    async with entry.setup_lock:
        assert await async_setup_entry(hass, entry) is True

    entity_ids = hass.states.async_entity_ids("binary_sensor")
    assert len(entity_ids) == 1
    return entry, entity_ids[0]


# ---------------------------------------------------------------------------
# Criterion 1: alerta → on, acronyms = ["INUNCAT"], never "plans"
# ---------------------------------------------------------------------------


async def test_alerta_is_on_with_inuncat_acronyms(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A live ALERTA capture reads ``on`` with ``acronyms = ["INUNCAT"]``."""
    _, entity_id = await _setup(hass, mock_http, load_fixture("alerta_2026_08_06"))

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["acronyms"] == ["INUNCAT"]
    # The name "plans" is exclusive to the sensor's object list (§3.3, §3.2).
    assert "plans" not in state.attributes


# ---------------------------------------------------------------------------
# Criterion 2: prealerta → off while max_phase is prealerta
# ---------------------------------------------------------------------------


async def test_prealerta_is_off_while_max_phase_is_prealerta(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The real 2024-12-02 prealerta reads ``off``, its phase is not lost.

    The prealerta is a first-class state: the same snapshot leaves this
    entity ``off`` (the source says a prealerta does not activate the plan)
    and leaves the maximum phase at ``prealerta``. Both assertions read the
    same coordinator state so the pairing cannot drift.
    """
    entry, entity_id = await _setup(
        hass, mock_http, load_fixture("prealerta_2024_12_02")
    )

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "off"
    assert state.attributes["acronyms"] == []

    phases = [activation.phase for activation in entry.runtime_data.data.activations]
    assert max_phase(phases) is Phase.PREALERTA


# ---------------------------------------------------------------------------
# Criterion 3: buit → off
# ---------------------------------------------------------------------------


async def test_empty_feed_is_off(hass: HomeAssistant, mock_http: aioresponses) -> None:
    """``[]`` is a valid state: ``off``, not ``unknown`` or ``unavailable``."""
    _, entity_id = await _setup(hass, mock_http, [])

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "off"
    assert state.attributes["acronyms"] == []


# ---------------------------------------------------------------------------
# Criterion 4: emergencia_SYNTHETIC → on
# ---------------------------------------------------------------------------


async def test_emergencia_synthetic_is_on(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """An EMERGÈNCIA row (never observed live) reads ``on``."""
    _, entity_id = await _setup(hass, mock_http, load_fixture("emergencia_SYNTHETIC"))

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["acronyms"] == ["INUNCAT"]


# ---------------------------------------------------------------------------
# Criterion 5: the three rare plaactivat variants together still read on
# ---------------------------------------------------------------------------


async def test_rare_plaactivat_variants_aggregate_is_on(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The full three-variant fixture reads ``on`` and sorts ``acronyms``.

    This is the aggregation check only (criterion 5b of docs/03 §3.3): the
    per-variant coverage lives in the parametrized test below. It also pins
    the sorted, deduplicated attribute across three distinct acronyms.
    """
    _, entity_id = await _setup(hass, mock_http, RARE_ROWS)

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["acronyms"] == ["INFOCAT", "INUNCAT", "NEUCAT"]


# ---------------------------------------------------------------------------
# Criterion 6: each rare variant alone reads on (Si / " SI " / absent)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "variant_row",
    RARE_ROWS,
    ids=["Si_INUNCAT", "spaced_SI_INFOCAT", "absent_NEUCAT"],
)
async def test_each_rare_plaactivat_variant_alone_is_on(
    hass: HomeAssistant, mock_http: aioresponses, variant_row: dict[str, Any]
) -> None:
    """One rare-variant row at a time: ``Si``, ``" SI "`` and absent → on.

    A literal ``plaactivat == "SI"`` comparison would fail all three: the
    casing, the padding and the missing field each break it. Each variant is
    loaded as its own single-row feed so no variant hides behind another.
    """
    _, entity_id = await _setup(hass, mock_http, [variant_row])

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "on"


# ---------------------------------------------------------------------------
# Entity contract: device_class, translation_key, device, unique_id
# ---------------------------------------------------------------------------


async def test_entity_contract_is_safety_and_translated(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """``device_class = SAFETY``, ``translation_key = "plan_activated"``.

    Instantiated against a live coordinator (the same one ``async_setup_entry``
    arms) so ``unique_id`` and ``device_info`` are read as production would.
    """
    entry, _ = await _setup(hass, mock_http, [])

    entity = CecatPlanActivatedBinarySensor(
        entry.runtime_data, PLAN_ACTIVATED_DESCRIPTION
    )
    assert entity.device_class == BinarySensorDeviceClass.SAFETY
    assert entity.translation_key == "plan_activated"
    assert entity.unique_id == f"{entry.entry_id}_plan_activated"
    assert entity.available is True

    device_info = entity.device_info
    assert device_info is not None
    assert device_info["entry_type"] is DeviceEntryType.SERVICE
    assert device_info["identifiers"] == {(DOMAIN, entry.entry_id)}


# ---------------------------------------------------------------------------
# Deduplication: two rows of one acronym, one activated
# ---------------------------------------------------------------------------


async def test_acronyms_deduplicates_one_acronym_in_two_phases(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """Two PROCICAT rows collapse to one entry of ``acronyms``.

    The question is "which plans are activated", not "how many rows say so".
    """
    _, entity_id = await _setup(hass, mock_http, load_fixture("dos_procicat_SYNTHETIC"))

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["acronyms"] == ["PROCICAT"]
