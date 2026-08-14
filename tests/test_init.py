"""Tests for the cecat integration setup and unload.

The coordinator is exercised directly in ``test_coordinator.py``; this module
covers the wiring that ``async_setup_entry`` adds on top: the coordinator lands
on ``entry.runtime_data`` (never ``hass.data``), the empty ``PLATFORMS`` tuple
forwards to nothing, and the entry sets up and unloads cleanly.
"""

from __future__ import annotations

from importlib.util import find_spec

from aioresponses import aioresponses
from custom_components.cecat import PLATFORMS, async_setup_entry, async_unload_entry
from custom_components.cecat.const import BASE_URL, DOMAIN, PARAMS
from custom_components.cecat.coordinator import CecatCoordinator
from homeassistant.config_entries import ConfigEntryState, Platform
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

CECAT_URL = URL(BASE_URL).with_query(PARAMS)


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    """Build and register a cecat MockConfigEntry."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    return entry


def test_every_forwarded_platform_has_its_module() -> None:
    """``PLATFORMS`` only names platforms whose module exists.

    Forwarding to a platform with no module raises and would make the
    integration unloadable, so this invariant is what lets the tuple grow
    one platform at a time (T6 adds SENSOR on top of BINARY_SENSOR).
    """
    for platform in PLATFORMS:
        assert find_spec(f"custom_components.cecat.{platform.value}") is not None


def test_binary_sensor_is_forwarded() -> None:
    """T7 registers the binary_sensor platform (docs/05 T7)."""
    assert Platform.BINARY_SENSOR in PLATFORMS


async def test_setup_puts_coordinator_on_runtime_data(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """Setup arms the coordinator on ``runtime_data`` and returns True.

    The call runs under the entry's ``setup_lock``, the guarantee
    ``hass.config_entries.async_setup`` gives in production, because since T7
    the setup forwards to ``BINARY_SENSOR`` and forwarding demands the lock.
    """
    mock_http.get(CECAT_URL, payload=[])
    entry = _entry(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    async with entry.setup_lock:
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
    async with entry.setup_lock:
        await async_setup_entry(hass, entry)
    # Direct-call path: pretend HA finished the state transition so the
    # unload really reaches ``async_unload_entry``.
    entry.mock_state(hass, ConfigEntryState.LOADED)

    assert await async_unload_entry(hass, entry) is True
