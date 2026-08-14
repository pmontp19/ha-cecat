"""The Protecció Civil Catalunya (cecat) integration.

Exposes the activation state of Catalonia's civil-protection plans
(INUNCAT, VENTCAT, NEUCAT, PROCICAT, SISMICAT, ...) sourced from the
CECAT feed on the Catalan open-data portal.

``async_setup_entry`` stores per-entry runtime data under ``hass.data[DOMAIN]``
and registers an update listener that rebinds the coordinator poll interval
when ``scan_interval_min`` changes in the options flow, without reloading the
entry (docs/04-architecture.md §7). The coordinator itself and platform
forwarding land in T5.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_SCAN_INTERVAL_MIN, DEFAULT_SCAN_INTERVAL_MIN, DOMAIN

__all__ = ["DOMAIN"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up cecat from a config entry.

    Registers the options-update listener so that changing
    ``scan_interval_min`` rebinds the coordinator's ``update_interval``
    without a reload. The coordinator, first refresh and platform forwarding
    are wired in by T5.
    """
    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a cecat config entry.

    Drops the per-entry runtime data. Platform unloading is wired in by T5.
    """
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rebind the coordinator poll interval when ``scan_interval_min`` changes.

    Reads the coordinator from ``hass.data[DOMAIN][entry.entry_id]``; until T5
    stores it there this is a safe no-op, so the options flow is testable in
    isolation by mocking the coordinator (docs/05 T9 decision lore).
    """
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        return
    interval = entry.options.get(CONF_SCAN_INTERVAL_MIN, DEFAULT_SCAN_INTERVAL_MIN)
    coordinator.update_interval = timedelta(minutes=interval)
