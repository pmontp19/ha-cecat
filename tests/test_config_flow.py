"""Tests for the cecat config_flow stub.

The full flow lands in T9; these only exercise the stub created in T1 so the
``--cov-fail-under=95`` gate has covered code to measure against.
"""

from __future__ import annotations

from custom_components.cecat.const import DOMAIN
from homeassistant.data_entry_flow import FlowResultType


async def test_user_step_shows_form_when_no_input(hass) -> None:
    """First call without input returns the form."""
    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_creates_entry_when_input_provided(hass) -> None:
    """Submitting the form creates the entry."""
    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": "user"}, user_input={})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Plans de Protecció Civil"
    assert result["data"] == {}


async def test_second_instance_is_aborted(hass, config_entry) -> None:
    """A configured instance aborts a new one (single_config_entry)."""
    flow = hass.config_entries.flow
    result = await flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
