"""Shared pytest fixtures and helpers for cecat tests."""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from custom_components.cecat.const import DOMAIN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytest_plugins = "pytest_homeassistant_custom_component"


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> list[dict] | dict:
    """Load a JSON fixture from ``tests/fixtures``.

    ``name`` may be given with or without the ``.json`` extension. Real
    fixtures are literal copies of ``docs/captures/`` (observed evidence);
    synthetic ones carry the ``_SYNTHETIC`` suffix and a ``_comment`` key on
    each row declaring so (``AGENTS.md`` evidence discipline).
    """
    if not name.endswith(".json"):
        name = f"{name}.json"
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FakeClock:
    """A controllable stand-in for ``homeassistant.util.dt.utcnow``.

    Time-dependent logic in this integration (stale-data windows, escalation
    windows, "recently ended" detection) is a pure function of the wall clock.
    Tests advance this clock explicitly instead of sleeping for real time or
    fighting ``freezegun`` across many refresh cycles
    (``docs/04-architecture.md`` §12).

    Patch it over the ``utcnow`` reference of the module under test, e.g.::

        monkeypatch.setattr("custom_components.cecat.coordinator.utcnow", clock)
    """

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock() -> FakeClock:
    """A ``FakeClock`` starting at a fixed, memorable instant.

    2026-08-06 11:49 UTC is the capture instant of ``alerta_2026_08_06.json``,
    so a test using that fixture starts in the same moment the evidence was
    observed.
    """
    return FakeClock(datetime(2026, 8, 6, 11, 49, tzinfo=UTC))


@pytest.fixture(autouse=True)
def _mock_platforms() -> Generator[None]:
    """Avoid real platform forwarding during tests.

    The coordinator and platforms land in T5; until then setup is replaced by
    a no-op forward of an empty platform tuple. The wrapper is an async
    function so Home Assistant's setup machinery awaits it cleanly instead of
    leaking an unawaited coroutine.
    """

    async def _setup(hass: HomeAssistant, entry: object) -> None:
        await hass.config_entries.async_forward_entry_setups(entry, ())  # type: ignore[arg-type]

    with patch("custom_components.cecat.async_setup_entry", wraps=_setup):
        yield


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let the HA flow manager load the cecat custom component."""


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
