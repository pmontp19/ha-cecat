"""Resilience tests for cecat: the §8 table of docs/04-architecture.md.

One test per row of the resilience table, row by row, plus the trap-7 URL
passthrough of docs/01-data-sources.md §12 that T10 pins as an acceptance
criterion. Every test runs the full stack (``aioresponses`` feeds the
fetch, the real ``async_setup_entry`` wires coordinator, platforms and
entities), because §8 is a table of observable behaviour, not of internal
calls: "entities keep the value" and "available = False on all entities"
are claims about entity objects and states, not about the coordinator
alone.

Row map: every test is named ``test_rowN_...`` after its §8 row, in table
order. Row 1 timeout/network/5xx, row 2 4xx, row 3 invalid or non-list
JSON, row 4 non-dict element inside the list, row 5 missing or null field,
row 6 unknown ``plafase``, row 7 unknown ``plaacronim``, row 8 tolerated
``plaactivat`` spelling, row 9 absent/empty/unrecognizable ``plaactivat``,
row 10 same acronym in two phases, row 11 three consecutive failures, row
12 data older than max(6 x interval, 1 h), row 13 HTTP 304. The last test
pins the trap-7 URL passthrough that T10 lists as an acceptance criterion.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from aioresponses import aioresponses
from custom_components.cecat.const import (
    BASE_URL,
    DOMAIN,
    EVENT_PHASE_CHANGED,
    EVENT_PHASE_ENDED,
    EVENT_PHASE_STARTED,
    EVENT_SERVICE_DEGRADED,
    PARAMS,
)
from custom_components.cecat.models import Phase
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import async_get_platforms
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

from tests.conftest import FakeClock, load_fixture

CECAT_URL = URL(BASE_URL).with_query(PARAMS)
LAST_MODIFIED = "Thu, 06 Aug 2026 09:20:17 GMT"

EVENT_NAMES = (
    EVENT_PHASE_STARTED,
    EVENT_PHASE_CHANGED,
    EVENT_PHASE_ENDED,
    EVENT_SERVICE_DEGRADED,
)


def _row(acronym: str, phase: str, **overrides: Any) -> dict[str, Any]:
    """A synthetic feed row; overrides replace fields or add new ones."""
    row: dict[str, Any] = {
        "plaacronim": acronym,
        "plafase": phase,
        "plaactivat": "SI",
        "fasedatahora": "06/08/2026 10:00",
        "comunicatpdf": {"url": f"https://example.invalid/{acronym}_{phase}.pdf"},
        "descripcio": f"Test row {acronym} {phase}",
    }
    row.update(overrides)
    return row


async def _setup(
    hass: HomeAssistant,
    mock_http: aioresponses,
    payload: Any,
    caplog: pytest.LogCaptureFixture | None = None,
) -> MockConfigEntry:
    """Set up a full cecat entry served ``payload`` and return the entry.

    The whole wiring runs for real (coordinator, first refresh, platform
    forward, entity registration): the §8 rows make claims about entities
    and events, so the entities and the listeners have to exist.
    """
    mock_http.get(CECAT_URL, payload=payload, headers={"Last-Modified": LAST_MODIFIED})
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _listen(hass: HomeAssistant) -> list[tuple[str, dict[str, Any]]]:
    """Capture every cecat bus event fired after this call, in fire order.

    The listeners are ``@callback`` so they run inline inside
    ``async_fire``, preserving fire order (same lesson as ``test_events``).
    """
    seen: list[tuple[str, dict[str, Any]]] = []
    for name in EVENT_NAMES:

        @callback
        def _on(event: Event, _name: str = name) -> None:
            seen.append((_name, dict(event.data)))

        hass.bus.async_listen(name, _on)
    return seen


def _sensor_state(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    """The current state of one of the three sensors, by description key."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state


def _plan_items(hass: HomeAssistant, entry: MockConfigEntry) -> list[dict[str, Any]]:
    """The per-plan objects of the ``plans`` sensor attribute."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_plans"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    return state.attributes["plans"]


def _live_entities(hass: HomeAssistant) -> list[Any]:
    """Every live cecat entity object (3 sensors + the binary sensor)."""
    entities: list[Any] = []
    for platform in async_get_platforms(hass, DOMAIN):
        entities.extend(platform.entities.values())
    assert len(entities) == 4
    return entities


def _sent_if_modified_since(mocked: aioresponses) -> list[str | None]:
    """The ``If-Modified-Since`` header of every GET, in call order."""
    sent: list[str | None] = []
    for (method, _url), calls in mocked.requests.items():
        if method != "GET":
            continue
        for call in calls:
            sent.append(dict(call.kwargs.get("headers") or {}).get("If-Modified-Since"))
    return sent


# ---------------------------------------------------------------------------
# §8 row 1: Timeout / xarxa / 5xx
# ---------------------------------------------------------------------------


async def test_row1_timeout_network_5xx_keep_entities_and_count(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A timeout and a 5xx each count one failure; entities keep the value.

    ``UpdateFailed`` keeps the last good ``self.data`` (§5 step 3) and the
    stale window keeps the entities presenting it: right after the failures
    the states are still ``alerta`` / ``1`` / ``on``, never ``unavailable``.
    """
    entry = await _setup(hass, mock_http, load_fixture("alerta_2026_08_06"))
    coordinator = entry.runtime_data
    good_state = coordinator.data
    assert _sensor_state(hass, entry, "max_phase") == "alerta"

    mock_http.get(CECAT_URL, exception=TimeoutError("upstream timeout"))
    await coordinator.async_refresh()
    mock_http.get(CECAT_URL, status=500)
    await coordinator.async_refresh()

    assert coordinator.consecutive_failures == 2
    assert coordinator.data is good_state
    assert coordinator.last_update_success is False
    assert _sensor_state(hass, entry, "max_phase") == "alerta"
    assert _sensor_state(hass, entry, "plans") == "1"


# ---------------------------------------------------------------------------
# §8 row 2: 4xx
# ---------------------------------------------------------------------------


async def test_row2_http_4xx_behaves_like_a_network_failure(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A 404 is a contract change, not credentials: same handling as 5xx.

    There is no auth on this endpoint, so nothing about a 4xx is
    recoverable by the integration: it counts, it keeps the state, it
    surfaces the status in ``last_error``.
    """
    entry = await _setup(hass, mock_http, load_fixture("alerta_2026_08_06"))
    coordinator = entry.runtime_data
    good_state = coordinator.data

    mock_http.get(CECAT_URL, status=404)
    await coordinator.async_refresh()

    assert coordinator.consecutive_failures == 1
    assert coordinator.data is good_state
    assert coordinator.last_error is not None
    assert "404" in coordinator.last_error
    assert _sensor_state(hass, entry, "max_phase") == "alerta"


# ---------------------------------------------------------------------------
# §8 row 3: JSON no vàlid o no-llista
# ---------------------------------------------------------------------------


async def test_row3_invalid_or_non_list_body_preserves_state(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """Undecodable bytes and a JSON object are both ``CecatFormatError``.

    Two shape changes, two failed cycles, one preserved state: the
    entities never see the malformed body at all.
    """
    entry = await _setup(hass, mock_http, load_fixture("alerta_2026_08_06"))
    coordinator = entry.runtime_data
    good_state = coordinator.data

    mock_http.get(CECAT_URL, body="<html>not json</html>", content_type="text/html")
    await coordinator.async_refresh()
    mock_http.get(CECAT_URL, payload={"error": True})
    await coordinator.async_refresh()

    assert coordinator.consecutive_failures == 2
    assert coordinator.data is good_state
    assert _sensor_state(hass, entry, "max_phase") == "alerta"


# ---------------------------------------------------------------------------
# §8 row 4: element no-dict dins la llista
# ---------------------------------------------------------------------------


async def test_row4_non_dict_element_is_discarded_and_rest_processed(
    hass: HomeAssistant,
    mock_http: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A stray string and a stray int are dropped at debug; dicts survive.

    One malformed element never drops a real plan: the ALERTA row in the
    same body still lands as the one and only entry.
    """
    alerta = load_fixture("alerta_2026_08_06")
    mixed: list[Any] = [alerta[0], "not a dict", 42]
    caplog.set_level(logging.DEBUG, logger="custom_components.cecat.api")
    entry = await _setup(hass, mock_http, mixed)

    assert _sensor_state(hass, entry, "plans") == "1"
    assert _sensor_state(hass, entry, "max_phase") == "alerta"
    assert any("non-dict" in record.message.lower() for record in caplog.records)


# ---------------------------------------------------------------------------
# §8 row 5: camp que falta o és null
# ---------------------------------------------------------------------------


async def test_row5_missing_or_null_fields_never_raise_in_any_layer(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """Absent fields and explicit nulls both read as defaults, never raise.

    ``camps_absents_SYNTHETIC`` (optional fields absent wholesale) plus an
    inline row with the same fields explicitly ``null`` travel the whole
    stack: fetch, parse, coordinator, entities. No ``KeyError`` anywhere,
    both rows ingested with ``None`` where the field was not there.
    """
    nulls_row = _row(
        "AEROCAT",
        "PREALERTA",
        plaactivat="NO",
        fasedatahora=None,
        descripcio=None,
        comunicatpdf=None,
        plaicona=None,
    )
    payload = [*load_fixture("camps_absents_SYNTHETIC"), nulls_row]
    entry = await _setup(hass, mock_http, payload)

    assert _sensor_state(hass, entry, "plans") == "2"
    items = {item["acronym"]: item for item in _plan_items(hass, entry)}
    for acronym in ("TRANSCAT", "AEROCAT"):
        assert items[acronym]["description"] is None
        assert items[acronym]["communique_url"] is None


# ---------------------------------------------------------------------------
# §8 row 6: plafase desconeguda
# ---------------------------------------------------------------------------


async def test_row6_unknown_plafase_transitions_without_phase_changed(
    hass: HomeAssistant,
    mock_http: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """To and from ``UNRECOGNIZED``: ended + started with raw literals, no
    ``phase_changed``, one warning per literal, no exception.

    Cycle 2 walks PROCICAT ALERTA -> MÀXIMA and cycle 3 walks back: both
    directions must carry the raw literal (``MÀXIMA``) in
    ``phase_raw``/``previous_phase_raw``, and neither may assert a change
    event, because one side of the pair has no severity position (AD-8).
    """
    caplog.set_level("WARNING", logger="custom_components.cecat.coordinator")
    entry = await _setup(hass, mock_http, [_row("PROCICAT", "ALERTA")])
    coordinator = entry.runtime_data
    seen = _listen(hass)

    mock_http.get(
        CECAT_URL,
        payload=load_fixture("fase_desconeguda_SYNTHETIC"),
        headers={"Last-Modified": LAST_MODIFIED},
    )
    await coordinator.async_refresh()

    types = [name for name, _ in seen]
    assert types == [EVENT_PHASE_ENDED, EVENT_PHASE_STARTED]
    ended, started = seen[0][1], seen[1][1]
    assert ended["previous_phase_raw"] == "ALERTA"
    assert started["phase_raw"] == "MÀXIMA"
    assert started["phase"] == Phase.UNRECOGNIZED.value

    mock_http.get(
        CECAT_URL,
        payload=[_row("PROCICAT", "ALERTA")],
        headers={"Last-Modified": LAST_MODIFIED},
    )
    await coordinator.async_refresh()

    types = [name for name, _ in seen]
    assert types.count(EVENT_PHASE_CHANGED) == 0
    assert types.count(EVENT_PHASE_ENDED) == 2
    assert types.count(EVENT_PHASE_STARTED) == 2
    assert seen[2][1]["previous_phase_raw"] == "MÀXIMA"
    assert seen[3][1]["phase_raw"] == "ALERTA"
    phase_warnings = [
        r for r in caplog.records if "Fase de pla no reconeguda" in r.message
    ]
    assert len(phase_warnings) == 1  # one per literal across both cycles


# ---------------------------------------------------------------------------
# §8 row 7: plaacronim desconegut
# ---------------------------------------------------------------------------


async def test_row7_unknown_plaacronim_is_ingested_with_name_fallback(
    hass: HomeAssistant,
    mock_http: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``NOPLA`` is not a plan, and the row is ingested anyway.

    The name falls back to the acronym verbatim (never ``planom``, trap 4)
    and the warning fires once, not once per cycle.
    """
    caplog.set_level("WARNING", logger="custom_components.cecat.coordinator")
    body = [_row("NOPLA", "ALERTA")]
    for _ in range(2):
        mock_http.get(CECAT_URL, payload=body, headers={"Last-Modified": LAST_MODIFIED})
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await entry.runtime_data.async_refresh()  # second cycle with NOPLA

    assert _sensor_state(hass, entry, "plans") == "1"
    assert _sensor_state(hass, entry, "max_phase") == "alerta"
    item = _plan_items(hass, entry)[0]
    assert item["acronym"] == "NOPLA"
    assert item["name"] == "NOPLA"
    acronym_warnings = [r for r in caplog.records if "Pla desconegut" in r.message]
    assert len(acronym_warnings) == 1


# ---------------------------------------------------------------------------
# §8 row 8: plaactivat amb una grafia tolerada
# ---------------------------------------------------------------------------


async def test_row8_tolerated_plaactivat_spellings_win_without_warning(
    hass: HomeAssistant,
    mock_http: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``SI``/``si``/`` SI ``/``Si``/``NO``/``no`` are used as-is.

    Two rows prove the literal wins over the phase, which is the whole
    point of "no derivation": ``ALERTA`` with ``NO`` reads not activated,
    and ``PREALERTA`` with ``SI`` reads activated. No warning, nothing in
    ``unknown_activated``: tolerating the spelling is the normal case.
    """
    caplog.set_level("WARNING", logger="custom_components.cecat.coordinator")
    expectations = [
        ("INUNCAT", "ALERTA", "SI", True),
        ("INFOCAT", "ALERTA", "si", True),
        ("NEUCAT", "ALERTA", " SI ", True),
        ("VENTCAT", "ALERTA", "Si", True),
        ("AEROCAT", "ALERTA", "NO", False),  # literal beats activating phase
        ("TRANSCAT", "ALERTA", "no", False),
        ("PLASEQTA", "PREALERTA", "SI", True),  # literal beats non-activating
        ("CAMCAT", "PREALERTA", "no", False),
    ]
    body = [
        _row(acronym, phase, plaactivat=literal)
        for acronym, phase, literal, _ in expectations
    ]
    for _ in range(2):
        mock_http.get(CECAT_URL, payload=body, headers={"Last-Modified": LAST_MODIFIED})
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await entry.runtime_data.async_refresh()  # second cycle, still silent

    activated = {
        item["acronym"]: item["activated"] for item in _plan_items(hass, entry)
    }
    for acronym, _phase, _literal, expected in expectations:
        assert activated[acronym] is expected
    assert entry.runtime_data.unknown_activated == set()
    assert not [r for r in caplog.records if "plaactivat no reconegut" in r.message]


# ---------------------------------------------------------------------------
# §8 row 9: plaactivat absent, buit o irreconeixible
# ---------------------------------------------------------------------------


async def test_row9_unrecognizable_plaactivat_derives_from_phase(
    hass: HomeAssistant,
    mock_http: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Absent, empty and weird literals all derive from ``plafase``.

    The three ``EMERGÈNCIA`` rows of the fixture (``Si``, `` SI ``, absent)
    all read activated: an absent field never reads as "not activated".
    The empty literal on a ``PREALERTA`` derives ``False`` (the fallback is
    the phase, not unconditional ``True``), and ``Activat`` on an ``ALERTA``
    derives ``True``. Each literal warns exactly once.
    """
    caplog.set_level("WARNING", logger="custom_components.cecat.coordinator")
    body = [
        *load_fixture("emergencia_plaactivat_rar_SYNTHETIC"),
        _row("RADCAT", "PREALERTA", plaactivat=""),
        _row("SISMICAT", "ALERTA", plaactivat="Activat"),
    ]
    for _ in range(2):
        mock_http.get(CECAT_URL, payload=body, headers={"Last-Modified": LAST_MODIFIED})
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await entry.runtime_data.async_refresh()  # second cycle for once-ness

    activated = {
        item["acronym"]: item["activated"] for item in _plan_items(hass, entry)
    }
    assert activated["INUNCAT"] is True  # Si
    assert activated["INFOCAT"] is True  # " SI "
    assert activated["NEUCAT"] is True  # absent: derived from EMERGÈNCIA
    assert activated["RADCAT"] is False  # empty on PREALERTA: the phase wins
    assert activated["SISMICAT"] is True  # weird literal on ALERTA

    coordinator = entry.runtime_data
    assert coordinator.unknown_activated == {"<absent>", "", "Activat"}
    activated_warnings = [
        r for r in caplog.records if "plaactivat no reconegut" in r.message
    ]
    assert len(activated_warnings) == 3  # once per literal, across two cycles


# ---------------------------------------------------------------------------
# §8 row 10: dues files amb el mateix plaacronim en fases diferents
# ---------------------------------------------------------------------------


async def test_row10_same_acronym_two_phases_two_entries_two_started(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The key is ``(acronym, phase)``: one plan, two episodes.

    Seeded on ``[]`` so both PROCICAT rows arrive as additions: two
    ``phase_started``, two entries in the state, and the count sensor reads
    2, never 1.
    """
    entry = await _setup(hass, mock_http, load_fixture("buit_2026_06_16"))
    coordinator = entry.runtime_data
    seen = _listen(hass)

    mock_http.get(
        CECAT_URL,
        payload=load_fixture("dos_procicat_SYNTHETIC"),
        headers={"Last-Modified": LAST_MODIFIED},
    )
    await coordinator.async_refresh()

    started = [data for name, data in seen if name == EVENT_PHASE_STARTED]
    assert [data["acronym"] for data in started] == ["PROCICAT", "PROCICAT"]
    assert {data["phase"] for data in started} == {"alerta", "prealerta"}
    assert _sensor_state(hass, entry, "plans") == "2"
    assert len(_plan_items(hass, entry)) == 2


# ---------------------------------------------------------------------------
# §8 row 11: 3 cicles fallits consecutius
# ---------------------------------------------------------------------------


async def test_row11_three_consecutive_failures_degrade_then_recover(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The degraded event fires once per streak, recovered on the next 200.

    Three failures fire ``cecat_service_degraded`` with the streak count;
    a fourth failure stays silent (once per streak, not per failure); the
    next success fires the recovery event with ``recovered: true``.
    """
    entry = await _setup(hass, mock_http, load_fixture("alerta_2026_08_06"))
    coordinator = entry.runtime_data
    seen = _listen(hass)

    for _ in range(4):
        mock_http.get(CECAT_URL, status=500)
    for _ in range(4):
        await coordinator.async_refresh()

    degraded = [data for name, data in seen if name == EVENT_SERVICE_DEGRADED]
    assert len(degraded) == 1
    assert degraded[0]["consecutive_failures"] == 3
    assert degraded[0]["recovered"] is False

    mock_http.get(
        CECAT_URL,
        payload=load_fixture("alerta_2026_08_06"),
        headers={"Last-Modified": LAST_MODIFIED},
    )
    await coordinator.async_refresh()

    degraded = [data for name, data in seen if name == EVENT_SERVICE_DEGRADED]
    assert len(degraded) == 2
    assert degraded[1]["consecutive_failures"] == 0
    assert degraded[1]["recovered"] is True


# ---------------------------------------------------------------------------
# §8 row 12: dades més velles que max(6 x interval, 1 h)
# ---------------------------------------------------------------------------


async def test_row12_stale_data_takes_every_entity_unavailable(
    hass: HomeAssistant,
    mock_http: aioresponses,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh failure keeps values; past the window every entity is stale.

    Right after a failed cycle the four entities still present the last
    good values (the stale window is the whole point). One hour and one
    minute past the last successful fetch, ``available`` is ``False`` on
    all four, while the state machine keeps showing what it last wrote:
    ``unavailable`` on the next push, never a silent value change.
    """
    monkeypatch.setattr("custom_components.cecat.coordinator.utcnow", clock)
    entry = await _setup(hass, mock_http, load_fixture("alerta_2026_08_06"))
    coordinator = entry.runtime_data
    coordinator.last_update_success_time = clock.now  # align to the fake clock

    mock_http.get(CECAT_URL, status=500)
    await coordinator.async_refresh()
    assert all(entity.available for entity in _live_entities(hass))
    assert _sensor_state(hass, entry, "max_phase") == "alerta"

    clock.advance(hours=1, minutes=1)  # past max(6 x 5 min, 1 h)
    assert coordinator.available is False
    assert not any(entity.available for entity in _live_entities(hass))
    # The last written states stay visible until the next push.
    assert _sensor_state(hass, entry, "max_phase") == "alerta"


# ---------------------------------------------------------------------------
# §8 row 13: HTTP 304
# ---------------------------------------------------------------------------


async def test_row13_http_304_leaves_state_events_availability_intact(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """A 304 recomputes nothing, fires nothing, keeps availability."""
    entry = await _setup(hass, mock_http, load_fixture("alerta_2026_08_06"))
    coordinator = entry.runtime_data
    before = coordinator.data
    seen = _listen(hass)

    mock_http.get(CECAT_URL, status=304)
    await coordinator.async_refresh()

    assert seen == []
    assert coordinator.data is before
    assert coordinator.last_modified == LAST_MODIFIED
    assert coordinator.available is True
    assert _sensor_state(hass, entry, "max_phase") == "alerta"
    assert _sent_if_modified_since(mock_http)[-1] == LAST_MODIFIED


# ---------------------------------------------------------------------------
# T10 acceptance criterion 4 (docs/01 §12 trap 7): URL with accents
# ---------------------------------------------------------------------------


async def test_pdf_url_accents_reach_the_attribute_verbatim(
    hass: HomeAssistant, mock_http: aioresponses
) -> None:
    """The communiqué URL is an opaque string: never recoded, never checked.

    ``pdf_url_accents_2026_07_03`` carries ``ó``, ``à`` and an apostrophe
    unencoded in the path: the attribute must be the same string as the
    fixture, no percent-encoding, no normalisation, no validation.
    """
    rows = load_fixture("pdf_url_accents_2026_07_03")
    entry = await _setup(hass, mock_http, rows)

    item = _plan_items(hass, entry)[0]
    assert item["communique_url"] == rows[0]["comunicatpdf"]["url"]
    assert "ó" in item["communique_url"]
    assert "'" in item["communique_url"]
