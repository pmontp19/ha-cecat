"""Tests for the cecat config_flow stub.

Direct instantiation bypasses HA's flow manager (which needs the integration
registered); the full e2e flow tests land in T9 with proper conftest setup.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from custom_components.cecat.config_flow import CecatConfigFlow


def _make_flow(existing_entries: list[Any] | None = None) -> CecatConfigFlow:
    """Build a CecatConfigFlow with a fake handler context."""
    flow = CecatConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config_entries.flow.async_progress = MagicMock(return_value=[])
    flow._async_current_entries = MagicMock(  # type: ignore[assignment]
        return_value=existing_entries or []
    )
    return flow


async def test_user_step_returns_form_when_no_input() -> None:
    """First call without input returns the form."""
    flow = _make_flow()
    result = await flow.async_step_user()
    assert result["type"] == "form"
    assert result["step_id"] == "user"


async def test_user_step_creates_entry_when_input_provided() -> None:
    """Submitting the form creates the entry."""
    flow = _make_flow()
    result = await flow.async_step_user(user_input={})
    assert result["type"] == "create_entry"
    assert result["title"] == "Plans de Protecció Civil"
    assert result["data"] == {}


async def test_second_instance_is_aborted() -> None:
    """A configured instance aborts a new one (single_config_entry)."""
    flow = _make_flow(existing_entries=[{"id": "existing"}])
    result = await flow.async_step_user()
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"
