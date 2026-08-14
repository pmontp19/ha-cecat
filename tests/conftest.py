"""Shared pytest fixtures for cecat tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from custom_components.cecat.const import DOMAIN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture(autouse=True)
def _mock_platforms() -> Generator[None]:
    """Avoid real platform forwarding during tests."""
    with patch(
        "custom_components.cecat.async_setup_entry",
        wraps=lambda hass, entry: hass.config_entries.async_forward_entry_setups(
            entry, ()
        ),
    ):
        yield


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add a cecat MockConfigEntry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Plans de Protecció Civil",
        data={},
    )
    entry.add_to_hass(hass)
    return entry
