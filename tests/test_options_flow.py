"""Tests for the cecat options flow and the coordinator poll rebind.

Saving the options flow updates ``config_entry.options[scan_interval_min]``;
the update listener registered in ``async_setup_entry`` rebinds
``coordinator.update_interval`` without reloading the entry
(docs/04-architecture.md §7, docs/05 T9 acceptance). Because the coordinator
itself lands in T5, the rebind is exercised against a mock coordinator placed
in ``hass.data[DOMAIN][entry.entry_id]`` (docs/05 T9 decision lore).
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from custom_components.cecat import (
    _async_update_listener,
    async_unload_entry,
)
from custom_components.cecat import (
    async_setup_entry as real_setup,
)
from custom_components.cecat.config_flow import CONF_SCAN_INTERVAL_MIN, CecatConfigFlow
from custom_components.cecat.const import DEFAULT_SCAN_INTERVAL_MIN, DOMAIN
from homeassistant.config_entries import OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _entry_with_options(options: dict[str, int]) -> MockConfigEntry:
    """A cecat MockConfigEntry carrying the given options."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={},
        options=options,
        title="Plans de Protecció Civil",
    )


@pytest.fixture
def _coordinator() -> MagicMock:
    """A stand-in coordinator exposing the writable ``update_interval``."""
    coord = MagicMock()
    coord.update_interval = timedelta(minutes=DEFAULT_SCAN_INTERVAL_MIN)
    return coord


# ---------------------------------------------------------------------------
# Options UI: form and save
# ---------------------------------------------------------------------------


async def test_options_form_shows_current_value(hass: HomeAssistant) -> None:
    """The options form is pre-filled with the entry's current interval."""
    entry = _entry_with_options({CONF_SCAN_INTERVAL_MIN: 12})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    schema = result["data_schema"].schema
    marker = next(
        s for s in schema if getattr(s, "schema", None) == CONF_SCAN_INTERVAL_MIN
    )
    assert marker.default() == 12


async def test_options_save_updates_entry(hass: HomeAssistant) -> None:
    """Saving writes the new interval into ``entry.options``."""
    entry = _entry_with_options({CONF_SCAN_INTERVAL_MIN: 5})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_SCAN_INTERVAL_MIN: 15}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated.options[CONF_SCAN_INTERVAL_MIN] == 15


# ---------------------------------------------------------------------------
# Coordinator poll rebind
# ---------------------------------------------------------------------------


async def test_options_change_rebinds_coordinator(
    hass: HomeAssistant, _coordinator: MagicMock
) -> None:
    """Saving a new interval rebinds ``coordinator.update_interval`` (T9)."""
    entry = _entry_with_options({CONF_SCAN_INTERVAL_MIN: 5})
    entry.add_to_hass(hass)
    # Register the real update listener; bypass the conftest platform patch.
    await real_setup(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = _coordinator
    assert _coordinator.update_interval == timedelta(minutes=5)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_SCAN_INTERVAL_MIN: 15}
    )
    await hass.async_block_till_done()

    assert _coordinator.update_interval == timedelta(minutes=15)


async def test_update_listener_rebinds_coordinator_directly(
    hass: HomeAssistant, _coordinator: MagicMock
) -> None:
    """The listener sets ``update_interval`` from the entry's options."""
    entry = _entry_with_options({CONF_SCAN_INTERVAL_MIN: 7})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = _coordinator

    await _async_update_listener(hass, entry)

    assert _coordinator.update_interval == timedelta(minutes=7)


async def test_update_listener_noop_without_coordinator(hass: HomeAssistant) -> None:
    """No coordinator stored yet (T5 not landed) is a safe no-op."""
    entry = _entry_with_options({CONF_SCAN_INTERVAL_MIN: 5})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})
    # Must not raise.
    await _async_update_listener(hass, entry)


async def test_update_listener_falls_back_to_default(
    hass: HomeAssistant, _coordinator: MagicMock
) -> None:
    """Missing option defaults to DEFAULT_SCAN_INTERVAL_MIN."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = _coordinator

    await _async_update_listener(hass, entry)

    assert _coordinator.update_interval == timedelta(minutes=DEFAULT_SCAN_INTERVAL_MIN)


# ---------------------------------------------------------------------------
# Setup/unload wiring
# ---------------------------------------------------------------------------


async def test_setup_registers_update_listener(hass: HomeAssistant) -> None:
    """``async_setup_entry`` registers exactly one update listener."""
    entry = _entry_with_options({CONF_SCAN_INTERVAL_MIN: 5})
    entry.add_to_hass(hass)
    assert not entry.update_listeners
    await real_setup(hass, entry)
    assert len(entry.update_listeners) == 1


async def test_unload_drops_runtime_data(
    hass: HomeAssistant, _coordinator: MagicMock
) -> None:
    """``async_unload_entry`` removes the coordinator from runtime data."""
    entry = _entry_with_options({CONF_SCAN_INTERVAL_MIN: 5})
    entry.add_to_hass(hass)
    await real_setup(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = _coordinator

    ok = await async_unload_entry(hass, entry)
    assert ok
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


def test_options_handler_is_options_flow() -> None:
    """The handler built by ``async_get_options_flow`` is an OptionsFlow."""
    entry = _entry_with_options({CONF_SCAN_INTERVAL_MIN: 5})
    assert real_setup.__module__ == "custom_components.cecat"  # sanity
    flow = CecatConfigFlow.async_get_options_flow(entry)
    assert isinstance(flow, OptionsFlow)
    assert flow._config_entry is entry
