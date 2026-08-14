"""Config flow for the cecat integration.

This is a scaffold stub. The full config flow (single_config_entry, options) lands in T9.
hassfest requires this file to exist when manifest declares ``config_flow: true``.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


class CecatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for cecat. Replaced fully in T9."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Single-step stub: creates the entry immediately.

        T9 replaces this with the proper single_config_entry flow (no user options
        at setup time; ``single_config_entry`` means one entry per instance).
        """
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Plans de Protecció Civil", data={})
        return self.async_show_form(step_id="user")
