"""HTTP client and conditional cache for the CECAT civil-protection feed.

A single GET against the Socrata open-data endpoint, with conditional caching
via ``If-Modified-Since`` (docs/04-architecture.md §3). This module is the only
contact with the outside world: it fetches, validates the body is a list, and
returns the raw rows. Turning rows into ``PlanActivation`` objects is
``models.py``'s job; reconciling cycles is the coordinator's (T5).

Conditional caching uses ``If-Modified-Since`` exclusively. The source's
``ETag`` arrives broken (a duplicated ``--gzip`` suffix) and is not honoured
(docs/captures/http-headers-2026-08-06.txt): ``If-None-Match`` is never sent.
``last_modified`` is passed in and echoed back, never stored here, so this
function stays stateless and the coordinator owns that piece of state.

An empty body ``[]`` is the expected steady state (docs/01-data-sources.md
§12 trap 1): it returns an empty list, never raises. A non-dict element inside
the list is discarded at ``debug`` and the rest are processed, so one malformed
row never drops a real plan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import BASE_URL, PARAMS

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "CecatConnectionError",
    "CecatFormatError",
    "FetchResult",
    "fetch",
]

_REQUEST_TIMEOUT_SECONDS = 15


class CecatConnectionError(HomeAssistantError):
    """Network or HTTP failure reaching the CECAT endpoint.

    Covers timeouts, connection errors, and any non-304 HTTP status (4xx and
    5xx). There is no authentication on this endpoint, so a 4xx is a contract
    change, not a credentials problem (docs/04-architecture.md §3). The
    coordinator maps this to ``UpdateFailed`` and preserves the last good state.
    """


class CecatFormatError(HomeAssistantError):
    """The response body is not the expected JSON list.

    The source is expected to return ``[row, ...]``; an object, a bare string,
    or undecodable bytes are all schema changes worth flagging. The coordinator
    maps this to ``UpdateFailed`` and preserves the last good state.
    """


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Outcome of one ``fetch`` call.

    ``rows`` is the decoded list of dict rows on a 200, or ``None`` on a 304.
    ``last_modified`` is the ``Last-Modified`` header to feed back into the next
    call as ``If-Modified-Since``: on a 304 it is the value that was passed in,
    untouched. ``not_modified`` is True only on a 304.
    """

    rows: list[dict[str, Any]] | None
    last_modified: str | None
    not_modified: bool


async def fetch(hass: HomeAssistant, last_modified: str | None) -> FetchResult:
    """Fetch the CECAT feed with conditional caching.

    Sends ``If-Modified-Since`` when ``last_modified`` is not ``None``. Returns
    the decoded rows and the new ``Last-Modified`` on a 200, or signals
    ``not_modified`` on a 304. Raises ``CecatConnectionError`` on any network or
    HTTP failure, and ``CecatFormatError`` when the body is not a JSON list.
    """
    session = async_get_clientsession(hass)
    headers: dict[str, str] = {}
    if last_modified is not None:
        headers["If-Modified-Since"] = last_modified

    try:
        async with session.get(
            BASE_URL,
            params=PARAMS,
            headers=headers,
            timeout=ClientTimeout(total=_REQUEST_TIMEOUT_SECONDS),
        ) as response:
            if response.status == HTTPStatus.NOT_MODIFIED:
                return FetchResult(
                    rows=None,
                    last_modified=last_modified,
                    not_modified=True,
                )
            response.raise_for_status()
            new_last_modified = response.headers.get("Last-Modified")
            body = await response.json(content_type=None)
    except (ClientError, TimeoutError) as err:
        raise CecatConnectionError(
            f"Could not reach the CECAT endpoint: {err}"
        ) from err
    except ValueError as err:
        raise CecatFormatError(f"The CECAT response was not valid JSON: {err}") from err

    if not isinstance(body, list):
        raise CecatFormatError(
            f"The CECAT response is not a list but {type(body).__name__}: {body!r}"
        )

    rows: list[dict[str, Any]] = []
    for row in body:
        if isinstance(row, dict):
            rows.append(row)
        else:
            _LOGGER.debug("Discarding non-dict element from CECAT response: %r", row)

    return FetchResult(
        rows=rows,
        last_modified=new_last_modified,
        not_modified=False,
    )
