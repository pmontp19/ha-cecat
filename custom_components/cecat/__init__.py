"""The Protecció Civil Catalunya (cecat) integration.

Exposes the activation state of Catalonia's civil-protection plans
(INUNCAT, VENTCAT, NEUCAT, PROCICAT, SISMICAT, ...) sourced from the
CECAT feed on the Catalan open-data portal.

This is the scaffold: `async_setup_entry` and `async_unload_entry` are
placeholders that let Home Assistant load the integration. The coordinator,
entity platforms and config flow land in later tasks.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

__all__ = ["DOMAIN"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up cecat from a config entry.

    Placeholder: the coordinator, first refresh and platform forwarding are
    wired in later tasks. Returning ``True`` lets the integration load so the
    config flow and validation tooling can be exercised.
    """
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a cecat config entry.

    Placeholder: once platforms are forwarded in ``async_setup_entry``, this
    will call ``async_unload_platforms`` and shut down the coordinator.
    """
    return True
