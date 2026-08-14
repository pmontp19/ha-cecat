"""The Proteccio Civil Catalunya (cecat) integration.

Exposes the activation state of Catalonia's civil-protection plans
(INUNCAT, VENTCAT, NEUCAT, PROCICAT, SISMICAT, ...) sourced from the
CECAT feed on the Catalan open-data portal.

Each config entry owns one ``CecatCoordinator`` that lives on
``entry.runtime_data`` (docs/04-architecture.md §9): no ``hass.data`` dict,
because this is a single-config-entry service integration and ``runtime_data``
is the typed handle every platform reads.

An options-update listener rebinds the coordinator poll interval when
``scan_interval_min`` changes in the options flow, without reloading the
entry (docs/04-architecture.md §7).
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import coordinator
from .const import CONF_SCAN_INTERVAL_MIN, DEFAULT_SCAN_INTERVAL_MIN, DOMAIN

# Target set is BINARY_SENSOR + SENSOR (docs/04-architecture.md §6). Each
# platform joins this tuple only when its module exists: forwarding a config
# entry to a platform with no module raises and would make the integration
# unloadable, so SENSOR joins when T6 lands.
PLATFORMS: tuple[Platform, ...] = (Platform.BINARY_SENSOR,)

# The coordinator a config entry carries on its ``runtime_data``. Typing the
# entry this way gives every platform ``entry.runtime_data`` already typed as
# the coordinator, with no cast and no ``hass.data`` lookup.
CecatConfigEntry = ConfigEntry[coordinator.CecatCoordinator]

__all__ = ["DOMAIN", "PLATFORMS", "CecatConfigEntry"]


async def async_setup_entry(hass: HomeAssistant, entry: CecatConfigEntry) -> bool:
    """Set up cecat from a config entry.

    Arms the coordinator with a first refresh, registers the options-update
    listener, and forwards the entry to its platforms. ``runtime_data`` holds
    the coordinator; nothing is written to ``hass.data``. The forward is
    skipped while ``PLATFORMS`` is empty.
    """
    coord = coordinator.CecatCoordinator(hass, entry)
    entry.runtime_data = coord
    await coord.async_config_entry_first_refresh()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CecatConfigEntry) -> bool:
    """Unload a cecat config entry and stop its coordinator."""
    unload_ok = True
    if PLATFORMS:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.async_shutdown()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: CecatConfigEntry) -> None:
    """Rebind the coordinator poll interval when ``scan_interval_min`` changes.

    Reads the coordinator from ``entry.runtime_data``; the options flow
    triggers an entry update, so the listener always sees a live coordinator.
    """
    interval = entry.options.get(CONF_SCAN_INTERVAL_MIN, DEFAULT_SCAN_INTERVAL_MIN)
    entry.runtime_data.update_interval = timedelta(minutes=interval)
