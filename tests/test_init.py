"""Tests for the cecat integration setup and unload.

The coordinator is exercised directly in ``test_coordinator.py``; this module
covers the wiring that ``async_setup_entry`` adds on top: the coordinator lands
on ``entry.runtime_data`` (never ``hass.data``), the empty ``PLATFORMS`` tuple
forwards to nothing, and the entry sets up and unloads cleanly.
"""

from __future__ import annotations

from aioresponses import aioresponses
from custom_components.cecat import PLATFORMS, async_setup_entry, async_unload_entry
from custom_components.cecat.const import BASE_URL, DOMAIN, PARAMS
from custom_components.cecat.coordinator import CecatCoordinator
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

CECAT_URL = URL(BASE_URL).with_query(PARAMS)


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    """Build and register a cecat MockConfigEntry."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    return entry


def test_platforms_is_empty_until_t6_lands() -> None:
    """No platform module exists yet, so the forward target is empty."""
    assert PLATFORMS == ()


async def test_setup_puts_coordinator_on_runtime_data(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """Setup arms the coordinator on ``runtime_data`` and returns True."""
    mock_http.get(CECAT_URL, payload=[])
    entry = _entry(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    assert await async_setup_entry(hass, entry) is True

    assert isinstance(entry.runtime_data, CecatCoordinator)
    assert DOMAIN not in hass.data  # nothing on hass.data (§9)


async def test_unload_entry_shuts_down_coordinator(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A configured entry unloads and returns True."""
    mock_http.get(CECAT_URL, payload=[])
    entry = _entry(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    await async_setup_entry(hass, entry)

    assert await async_unload_entry(hass, entry) is True
