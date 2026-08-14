"""Config flow and options flow for the cecat integration.

Single-step setup: the only user-tunable is the polling interval. Before
creating the entry, the flow makes one test request to the endpoint
(rule: ``test_before_configure``). An empty list ``[]`` is a success, not an
error: it is the steady state of the feed on most days
(docs/03-feature-spec.md §2.1). ``single_config_entry`` plus a fixed
``unique_id`` means a second instance is aborted.

The options flow reconfigures the same field; saving rebinds the coordinator
poll interval via the update listener in ``__init__.py`` without reloading the
entry (docs/04-architecture.md §7).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .api import CecatConnectionError, CecatFormatError, fetch
from .const import (
    CONF_SCAN_INTERVAL_MIN,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    MAX_SCAN_INTERVAL_MIN,
    MIN_SCAN_INTERVAL_MIN,
)

__all__ = ["CONF_SCAN_INTERVAL_MIN"]

TITLE = "Plans de Protecció Civil"


def _scan_interval_schema(default: int) -> vol.Schema:
    """Schema for the poll-interval slider, bounded 1..60 (docs/03 §2.1)."""
    number_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=MIN_SCAN_INTERVAL_MIN,
            max=MAX_SCAN_INTERVAL_MIN,
            step=1,
            mode=selector.NumberSelectorMode.SLIDER,
        )
    )
    return vol.Schema(
        {vol.Required(CONF_SCAN_INTERVAL_MIN, default=default): number_selector}
    )


class CecatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for cecat.

    ``single_config_entry: true`` is declared in the manifest and enforced by
    Home Assistant before ``async_step_user`` runs; the flow additionally sets
    a fixed ``unique_id`` so a duplicate is aborted even if that flag is
    bypassed (docs/03-feature-spec.md §2.1, docs/04-architecture.md §7).
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pick the poll interval and verify the endpoint.

        One test request to ``api.fetch`` decides between creating the entry
        (any list body, including ``[]``) and reporting ``cannot_connect``
        (timeout, network, non-2xx, or a body that is not a list).
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await fetch(self.hass, last_modified=None)
            except (CecatConnectionError, CecatFormatError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=TITLE,
                    data={},
                    options={
                        CONF_SCAN_INTERVAL_MIN: user_input[CONF_SCAN_INTERVAL_MIN]
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_scan_interval_schema(DEFAULT_SCAN_INTERVAL_MIN),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> CecatOptionsFlowHandler:
        """Return the options flow handler for the given entry."""
        return CecatOptionsFlowHandler(config_entry)


class CecatOptionsFlowHandler(OptionsFlow):
    """Reconfigure the polling interval.

    Saving updates ``config_entry.options``; the update listener registered in
    ``async_setup_entry`` rebinds ``coordinator.update_interval`` without a
    reload. The entry is passed explicitly from ``async_get_options_flow``
    rather than read from the deprecated instance attribute.
    """

    def __init__(self, config_entry: Any) -> None:
        """Store the config entry passed by the flow factory."""
        super().__init__()
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the poll interval."""
        current = self._config_entry.options.get(
            CONF_SCAN_INTERVAL_MIN, DEFAULT_SCAN_INTERVAL_MIN
        )
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={CONF_SCAN_INTERVAL_MIN: user_input[CONF_SCAN_INTERVAL_MIN]},
            )
        return self.async_show_form(
            step_id="init",
            data_schema=_scan_interval_schema(current),
        )
