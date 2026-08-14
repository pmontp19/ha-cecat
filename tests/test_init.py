"""Tests for the cecat ``__init__`` setup/unload wiring.

These cover the update-listener registration that rebinds the coordinator poll
interval on options change (docs/05 T9); the coordinator itself and platform
forwarding land in T5.
"""

from __future__ import annotations

from custom_components.cecat import async_setup_entry, async_unload_entry
from custom_components.cecat.const import DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, data={}, title="Plans de Protecció Civil")


async def test_async_setup_entry_returns_true(hass: HomeAssistant) -> None:
    """Setup succeeds and stores per-entry runtime data."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await async_setup_entry(hass, entry) is True
    assert DOMAIN in hass.data


async def test_async_setup_entry_registers_update_listener(
    hass: HomeAssistant,
) -> None:
    """Setup registers exactly one update listener."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert not entry.update_listeners
    await async_setup_entry(hass, entry)
    assert len(entry.update_listeners) == 1


async def test_async_unload_entry_returns_true(hass: HomeAssistant) -> None:
    """Unload succeeds and clears per-entry runtime data."""
    entry = _entry()
    entry.add_to_hass(hass)
    await async_setup_entry(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = object()
    assert await async_unload_entry(hass, entry) is True
    assert entry.entry_id not in hass.data[DOMAIN]


async def test_async_setup_entry_type_checked(hass: HomeAssistant) -> None:
    """Setup accepts a real ConfigEntry-typed entry (mypy parity)."""
    entry: ConfigEntry = _entry()  # type: ignore[assignment]
    entry.add_to_hass(hass)
    assert await async_setup_entry(hass, entry) is True
