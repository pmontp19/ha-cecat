"""Tests for the cecat config flow.

Every acceptance criterion of ``docs/05-implementation-plan.md`` T9 (lines
249-256) that belongs to the setup flow has an assertion here. The flow makes
one test request via ``api.fetch`` before creating the entry: an empty list
``[]`` is a success (docs/03-feature-spec.md §2.1), while a timeout, non-2xx
or non-list body report ``cannot_connect``. ``single_config_entry`` aborts a
second instance before ``async_step_user`` even runs.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from custom_components.cecat.api import (
    CecatConnectionError,
    CecatFormatError,
    FetchResult,
)
from custom_components.cecat.config_flow import CONF_SCAN_INTERVAL_MIN, CecatConfigFlow
from custom_components.cecat.const import (
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    MAX_SCAN_INTERVAL_MIN,
    MIN_SCAN_INTERVAL_MIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _ok_result(rows: list[dict[str, Any]] | None = None) -> FetchResult:
    """A successful fetch result (a list body, possibly empty)."""
    return FetchResult(
        rows=rows if rows is not None else [], last_modified=None, not_modified=False
    )


@pytest.fixture
def _mock_fetch() -> AsyncMock:
    """Patch ``api.fetch`` in the config_flow module with an async mock."""
    with patch(
        "custom_components.cecat.config_flow.fetch", new_callable=AsyncMock
    ) as mocked:
        yield mocked


# ---------------------------------------------------------------------------
# Step 1: the user form
# ---------------------------------------------------------------------------


async def test_user_step_shows_form_with_default_interval(
    hass: HomeAssistant, _mock_fetch: AsyncMock
) -> None:
    """First call returns the user form pre-filled with the default interval."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    schema = result["data_schema"].schema
    marker = next(
        s for s in schema if getattr(s, "schema", None) == CONF_SCAN_INTERVAL_MIN
    )
    selector_config = schema[marker].config
    assert selector_config["min"] == MIN_SCAN_INTERVAL_MIN
    assert selector_config["max"] == MAX_SCAN_INTERVAL_MIN
    assert selector_config["mode"] == "slider"
    assert marker.default() == DEFAULT_SCAN_INTERVAL_MIN


# ---------------------------------------------------------------------------
# Step 2: a successful test request creates the entry
# ---------------------------------------------------------------------------


async def test_empty_list_creates_entry(
    hass: HomeAssistant, _mock_fetch: AsyncMock
) -> None:
    """A test response of ``[]`` creates the entry (docs/03 §2.1)."""
    _mock_fetch.return_value = _ok_result([])
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={CONF_SCAN_INTERVAL_MIN: DEFAULT_SCAN_INTERVAL_MIN},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Plans de Protecció Civil"
    assert result["data"] == {}
    assert result["options"] == {CONF_SCAN_INTERVAL_MIN: DEFAULT_SCAN_INTERVAL_MIN}
    _mock_fetch.assert_awaited_once()


async def test_rows_create_entry_too(
    hass: HomeAssistant, _mock_fetch: AsyncMock
) -> None:
    """A populated list also creates the entry."""
    _mock_fetch.return_value = _ok_result(
        [{"plaacronim": "INUNCAT", "plafase": "ALERTA"}]
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={CONF_SCAN_INTERVAL_MIN: 10},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_SCAN_INTERVAL_MIN: 10}


async def test_entry_has_fixed_unique_id(
    hass: HomeAssistant, _mock_fetch: AsyncMock
) -> None:
    """The created entry carries the fixed unique_id ``cecat``."""
    _mock_fetch.return_value = _ok_result()
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={CONF_SCAN_INTERVAL_MIN: DEFAULT_SCAN_INTERVAL_MIN},
    )
    entry = hass.config_entries.async_get_entry(result["result"].entry_id)
    assert entry.unique_id == DOMAIN


# ---------------------------------------------------------------------------
# Step 3: a failing test request reports cannot_connect
# ---------------------------------------------------------------------------


async def test_connection_error_reports_cannot_connect(
    hass: HomeAssistant, _mock_fetch: AsyncMock
) -> None:
    """A timeout/network/5xx maps to ``cannot_connect`` and reshow the form."""
    _mock_fetch.side_effect = CecatConnectionError("boom")
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={CONF_SCAN_INTERVAL_MIN: DEFAULT_SCAN_INTERVAL_MIN},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_format_error_reports_cannot_connect(
    hass: HomeAssistant, _mock_fetch: AsyncMock
) -> None:
    """A body that is not a list maps to ``cannot_connect`` too."""
    _mock_fetch.side_effect = CecatFormatError("not a list")
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={CONF_SCAN_INTERVAL_MIN: DEFAULT_SCAN_INTERVAL_MIN},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


# ---------------------------------------------------------------------------
# Step 4: single_config_entry aborts a second instance
# ---------------------------------------------------------------------------


async def test_second_instance_is_aborted(hass: HomeAssistant) -> None:
    """A configured instance aborts a new flow (single_config_entry)."""
    existing = MockConfigEntry(domain=DOMAIN, data={}, title="Plans de Protecció Civil")
    existing.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


def test_async_get_options_flow_returns_handler() -> None:
    """``async_get_options_flow`` builds the options handler from the entry."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    handler = CecatConfigFlow.async_get_options_flow(entry)
    assert handler._config_entry is entry
