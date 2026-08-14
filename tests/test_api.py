"""Tests for the CECAT HTTP client and conditional cache.

Every acceptance criterion of ``docs/05-implementation-plan.md`` T4 (lines
118-126) has an assertion here. No network: ``aioresponses`` intercepts every
request the HA client session makes, so the test exercises the real
``async_get_clientsession`` path. The live evidence that ``If-Modified-Since``
returns 304 lives in ``docs/captures/http-headers-2026-08-06.txt`` and is
re-verified once at the end of the PR description.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from aiohttp import ClientError
from aioresponses import aioresponses
from custom_components.cecat.api import (
    CecatConnectionError,
    CecatFormatError,
    FetchResult,
    fetch,
)
from custom_components.cecat.const import BASE_URL, PARAMS
from homeassistant.core import HomeAssistant
from yarl import URL

CECAT_URL = URL(BASE_URL).with_query(PARAMS)
LAST_MODIFIED = "Thu, 06 Aug 2026 09:20:17 GMT"

ONE_ROW: list[dict[str, Any]] = [
    {"plaacronim": "INUNCAT", "plafase": "ALERTA", "plaactivat": "SI"}
]


@pytest.fixture
def mock_http() -> aioresponses:
    """An ``aioresponses`` context covering every request made in a test."""
    with aioresponses() as mocked:
        yield mocked


def _request_headers(mocked: aioresponses) -> list[dict[str, str]]:
    """Collect the request headers from every GET to the CECAT endpoint."""
    headers_list: list[dict[str, str]] = []
    for (method, _url), calls in mocked.requests.items():
        if method != "GET":
            continue
        for call in calls:
            headers_list.append(dict(call.kwargs.get("headers") or {}))
    return headers_list


# ---------------------------------------------------------------------------
# 200: rows returned and Last-Modified stored
# ---------------------------------------------------------------------------


async def test_200_returns_rows_and_last_modified(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A 200 decodes the body and reads the ``Last-Modified`` header."""
    mock_http.get(
        CECAT_URL,
        payload=ONE_ROW,
        headers={"Last-Modified": LAST_MODIFIED},
    )
    result = await fetch(hass, None)

    assert isinstance(result, FetchResult)
    assert result.not_modified is False
    assert result.rows == ONE_ROW
    assert result.last_modified == LAST_MODIFIED


# ---------------------------------------------------------------------------
# Second call sends If-Modified-Since with the stored value
# ---------------------------------------------------------------------------


async def test_second_call_sends_if_modified_since(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """``last_modified`` passed in becomes the ``If-Modified-Since`` header."""
    mock_http.get(
        CECAT_URL,
        payload=ONE_ROW,
        headers={"Last-Modified": LAST_MODIFIED},
    )
    await fetch(hass, LAST_MODIFIED)

    sent = _request_headers(mock_http)
    assert len(sent) == 1
    assert sent[0]["If-Modified-Since"] == LAST_MODIFIED


async def test_first_call_without_last_modified_sends_no_conditional_header(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """``last_modified=None`` means no ``If-Modified-Since`` on the wire."""
    mock_http.get(CECAT_URL, payload=[])
    await fetch(hass, None)

    sent = _request_headers(mock_http)
    assert len(sent) == 1
    assert "If-Modified-Since" not in sent[0]


# ---------------------------------------------------------------------------
# 304: not_modified=True, rows=None, Last-Modified untouched
# ---------------------------------------------------------------------------


async def test_304_returns_not_modified_without_touching_last_modified(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A 304 echoes back the ``last_modified`` that was passed in, unchanged."""
    mock_http.get(CECAT_URL, status=304)
    result = await fetch(hass, LAST_MODIFIED)

    assert result.not_modified is True
    assert result.rows is None
    assert result.last_modified == LAST_MODIFIED


# ---------------------------------------------------------------------------
# Timeout, 500, 404 -> CecatConnectionError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [500, 404])
async def test_http_errors_raise_connection_error(
    hass: HomeAssistant, mock_http: aioresponses, status: int
) -> None:
    """Non-304 error statuses surface as ``CecatConnectionError``."""
    mock_http.get(CECAT_URL, status=status)
    with pytest.raises(CecatConnectionError):
        await fetch(hass, None)


async def test_timeout_raises_connection_error(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A request timeout surfaces as ``CecatConnectionError``."""
    mock_http.get(CECAT_URL, timeout=True)
    with pytest.raises(CecatConnectionError):
        await fetch(hass, None)


async def test_connection_error_raises_cecat_connection_error(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A network-level failure (DNS, refused) surfaces as ``CecatConnectionError``."""
    mock_http.get(CECAT_URL, exception=ClientError("connection refused"))
    with pytest.raises(CecatConnectionError):
        await fetch(hass, None)


# ---------------------------------------------------------------------------
# Body is not a list -> CecatFormatError
# ---------------------------------------------------------------------------


async def test_object_body_raises_format_error(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A JSON object instead of a list is a schema change -> ``CecatFormatError``."""
    mock_http.get(CECAT_URL, payload={"error": True})
    with pytest.raises(CecatFormatError):
        await fetch(hass, None)


async def test_non_json_body_raises_format_error(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A body that does not decode as JSON is a ``CecatFormatError``."""
    mock_http.get(
        CECAT_URL,
        body="<html>not json</html>",
        content_type="text/html",
    )
    with pytest.raises(CecatFormatError):
        await fetch(hass, None)


# ---------------------------------------------------------------------------
# Empty list [] is valid, no exception
# ---------------------------------------------------------------------------


async def test_empty_list_returns_empty_rows(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """``[]`` is the most likely steady state and must never raise."""
    mock_http.get(CECAT_URL, payload=[])
    result = await fetch(hass, None)

    assert result.not_modified is False
    assert result.rows == []


# ---------------------------------------------------------------------------
# Non-dict element discarded with debug; rest processed
# ---------------------------------------------------------------------------


async def test_non_dict_element_discarded_with_debug(
    hass: HomeAssistant,
    mock_http: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A stray non-dict inside the list is dropped at debug; dicts survive."""
    mixed: list[Any] = [
        ONE_ROW[0],
        "not a dict",
        42,
        {"plaacronim": "PROCICAT", "plafase": "PREALERTA"},
    ]
    mock_http.get(CECAT_URL, payload=mixed)
    caplog.set_level(logging.DEBUG, logger="custom_components.cecat.api")
    result = await fetch(hass, None)

    assert result.rows == [ONE_ROW[0], mixed[3]]
    assert any("non-dict" in record.message.lower() for record in caplog.records)


# ---------------------------------------------------------------------------
# If-None-Match is never sent
# ---------------------------------------------------------------------------


async def test_if_none_match_never_sent(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The broken ETag is never used: ``If-None-Match`` is absent on every call."""
    mock_http.get(
        CECAT_URL,
        payload=ONE_ROW,
        headers={
            "Last-Modified": LAST_MODIFIED,
            "ETag": '"broken--gzip--gzip"',
        },
    )
    await fetch(hass, None)
    mock_http.get(CECAT_URL, status=304)
    await fetch(hass, LAST_MODIFIED)

    for headers in _request_headers(mock_http):
        assert "If-None-Match" not in headers
