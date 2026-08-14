"""Tests for the cecat bus events (docs/05-implementation-plan.md T8).

Every acceptance criterion of T8 (lines 215-236) has an assertion here, plus
the two worked examples of docs/04-architecture.md §5. No network:
``aioresponses`` intercepts the fetches and the ``FakeClock`` makes
``duration_minutes`` deterministic.

The anchors, in one place: ``phase_started`` fires for every added key and
``phase_ended`` for every removed key, always and without suppression;
``phase_changed`` is additive behind three conditions (one add, one remove,
both phases in ``PHASE_ORDER``); a failed cycle fires nothing; a cycle where
only ``comunicatpdf`` changed fires nothing; and no payload ever asserts an
origin for a key that appeared, because continuity across an acronym is not
derivable from this source (docs/03-feature-spec.md §4.1).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from aioresponses import aioresponses
from custom_components.cecat import coordinator as coordinator_module
from custom_components.cecat.const import (
    BASE_URL,
    DOMAIN,
    EVENT_PHASE_CHANGED,
    EVENT_PHASE_ENDED,
    EVENT_PHASE_STARTED,
    EVENT_SERVICE_DEGRADED,
    PARAMS,
)
from custom_components.cecat.coordinator import CecatCoordinator
from custom_components.cecat.models import PHASE_ORDER, Phase
from homeassistant.core import Event, HomeAssistant, callback
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

# The exact payloads of docs/03-feature-spec.md §4.1, §4.2 and §4.3. Every
# firing is compared against these sets: an extra field (say a stray
# ``previous_phase`` on ``started``, or a ``phase`` on ``ended``) fails here.
STARTED_FIELDS = {
    "acronym",
    "name",
    "phase",
    "phase_raw",
    "activated",
    "started_at",
    "description",
    "communique_url",
}
ENDED_FIELDS = {
    "acronym",
    "name",
    "previous_phase",
    "previous_phase_raw",
    "duration_minutes",
}
CHANGED_FIELDS = {
    "acronym",
    "name",
    "previous_phase",
    "previous_phase_raw",
    "phase",
    "phase_raw",
    "escalation",
    "activated",
    "started_at",
}

# With the frozen clock at 2026-08-06 11:49 UTC (the capture instant of the
# alerta fixture), the row's 13:18 Madrid start is 11:18 UTC the day before:
# 24 h 31 m = 1471 minutes. The helper row's 10:00 Madrid start is 08:00 UTC
# the same day: 3 h 49 m = 229 minutes.
ALERTA_FIXTURE_MINUTES = 1471
HELPER_ROW_MINUTES = 229


class EventLog:
    """Every cecat bus event fired during a test, captured in fire order."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.entries: list[tuple[str, dict[str, Any]]] = []
        for name in EVENT_NAMES:
            hass.bus.async_listen(name, self._capture(name))

    def _capture(self, name: str) -> Any:
        # ``@callback`` is not decoration for decoration's sake: a plain sync
        # function is scheduled on the executor, so the capture would lag the
        # fire and scramble the order. A callback listener runs inline, inside
        # ``async_fire``, in exact fire order.
        @callback
        def _on(event: Event) -> None:
            self.entries.append((name, dict(event.data)))

        return _on

    def of(self, event_type: str) -> list[dict[str, Any]]:
        """The data payloads of every firing of ``event_type``, in order."""
        return [data for name, data in self.entries if name == event_type]

    @property
    def types(self) -> list[str]:
        """Every fired event type, in fire order."""
        return [name for name, _ in self.entries]

    @property
    def phase_types(self) -> list[str]:
        """Every fired type except the degraded diagnostics one."""
        return [name for name in self.types if name != EVENT_SERVICE_DEGRADED]


@pytest.fixture
def evlog(hass: HomeAssistant) -> EventLog:
    """Capture every cecat event fired while the test runs."""
    return EventLog(hass)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Freeze the coordinator clock so durations are deterministic."""
    clock = FakeClock(datetime(2026, 8, 6, 11, 49, tzinfo=UTC))
    monkeypatch.setattr("custom_components.cecat.coordinator.utcnow", clock)
    return clock


def _make_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Build and register a cecat MockConfigEntry."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    return entry


def _row(acronym: str, phase: str, **overrides: Any) -> dict[str, Any]:
    """A synthetic feed row; overrides replace fields or add new ones.

    The default ``fasedatahora`` (06/08/2026 10:00 Madrid = 08:00 UTC) sits
    229 whole minutes before the frozen clock, so any ``duration_minutes``
    derived from it is exactly ``HELPER_ROW_MINUTES``.
    """
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


# ---------------------------------------------------------------------------
# Names: the family speaks of phases, never of activation (criterion line 215)
# ---------------------------------------------------------------------------


def test_event_names_are_the_phase_family() -> None:
    """No event is named activated/deactivated: that word is the binary's."""
    for name in EVENT_NAMES:
        assert "activated" not in name
        assert "deactivated" not in name
    assert EVENT_NAMES == (
        "cecat_plan_phase_started",
        "cecat_plan_phase_changed",
        "cecat_plan_phase_ended",
        "cecat_service_degraded",
    )


async def test_first_cycle_emits_no_events(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """The seeding cycle stays silent: no spurious started on restart."""
    mock_http.get(CECAT_URL, payload=load_fixture("alerta_2026_08_06"))
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()

    assert evlog.types == []


# ---------------------------------------------------------------------------
# Appearance from empty: one started, exactly eight fields (criterion 216)
# ---------------------------------------------------------------------------


async def test_started_from_empty_has_exactly_eight_fields(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """``{}`` -> ``{(INUNCAT, alerta)}`` fires one started, nothing else."""
    mock_http.get(CECAT_URL, payload=[])
    mock_http.get(CECAT_URL, payload=load_fixture("alerta_2026_08_06"))
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()  # seeds empty
    await coord.async_refresh()  # INUNCAT appears

    started = evlog.of(EVENT_PHASE_STARTED)
    assert len(started) == 1
    data = started[0]
    assert set(data) == STARTED_FIELDS
    # No origin field: continuity across an acronym is not derivable (§4.1).
    assert "previous_phase" not in data
    assert "previous_phase_raw" not in data
    assert data["acronym"] == "INUNCAT"
    assert data["name"] == "Inundacions"
    assert data["phase"] == Phase.ALERTA
    assert data["phase_raw"] == "ALERTA"
    assert data["activated"] is True
    assert data["started_at"] == datetime(2026, 8, 5, 11, 18, tzinfo=UTC)
    assert data["description"] == "Avís intensitat pluja fins al 04/08  -"
    assert (
        data["communique_url"]
        == "https://documents.dadesobertes.gencat.cat/cecat/docs/I-125912_ACTUALITZACIO--ACTIVAT_INUNCAT_202608061114.pdf"
    )
    assert evlog.of(EVENT_PHASE_ENDED) == []
    assert evlog.of(EVENT_PHASE_CHANGED) == []


# ---------------------------------------------------------------------------
# prealerta -> alerta: three events, none suppressing another (criterion 217)
# ---------------------------------------------------------------------------


async def test_prealerta_to_alerta_fires_three_events(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """Ended + started + changed with escalation true, in that order."""
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "PREALERTA", plaactivat="NO")])
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "ALERTA")])
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()

    assert evlog.types == [EVENT_PHASE_ENDED, EVENT_PHASE_STARTED, EVENT_PHASE_CHANGED]

    ended = evlog.of(EVENT_PHASE_ENDED)[0]
    assert set(ended) == ENDED_FIELDS
    assert "phase" not in ended
    assert "phase_raw" not in ended
    assert ended["acronym"] == "INUNCAT"
    assert ended["previous_phase"] == Phase.PREALERTA
    assert ended["previous_phase_raw"] == "PREALERTA"
    # duration_minutes is there for the intermediate phase too (criterion 232).
    assert ended["duration_minutes"] == HELPER_ROW_MINUTES

    started = evlog.of(EVENT_PHASE_STARTED)[0]
    assert set(started) == STARTED_FIELDS
    assert started["phase"] == Phase.ALERTA
    assert started["phase_raw"] == "ALERTA"

    changed = evlog.of(EVENT_PHASE_CHANGED)[0]
    assert set(changed) == CHANGED_FIELDS
    # Raw literals present even when both phases were recognised (criterion 227).
    assert changed["phase_raw"] == "ALERTA"
    assert changed["previous_phase_raw"] == "PREALERTA"
    assert changed["previous_phase"] == Phase.PREALERTA
    assert changed["phase"] == Phase.ALERTA
    assert changed["escalation"] is True


async def test_transition_to_emergencia_still_fires_started(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """A listener of started with phase == emergencia triggers (criterion 218).

    This is the regression the old suppression caused: replacing the pair
    with a changed event left the most important transition silent.
    """
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "ALERTA")])
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "EMERGÈNCIA")])
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()

    started = evlog.of(EVENT_PHASE_STARTED)
    assert len(started) == 1
    assert started[0]["phase"] == Phase.EMERGENCIA
    assert started[0]["phase_raw"] == "EMERGÈNCIA"
    changed = evlog.of(EVENT_PHASE_CHANGED)
    assert len(changed) == 1
    assert changed[0]["escalation"] is True
    assert evlog.of(EVENT_PHASE_ENDED)


async def test_alerta_to_prealerta_fires_three_events_desescalation(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """A downgrade is still three events, with escalation false (criterion 219)."""
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "ALERTA")])
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "PREALERTA", plaactivat="NO")])
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()

    assert len(evlog.of(EVENT_PHASE_ENDED)) == 1
    started = evlog.of(EVENT_PHASE_STARTED)
    assert len(started) == 1
    assert started[0]["phase"] == Phase.PREALERTA
    changed = evlog.of(EVENT_PHASE_CHANGED)
    assert len(changed) == 1
    assert changed[0]["escalation"] is False


async def test_emergencia_to_alerta_changed_has_escalation_false(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """The improving transition: started without origin, ended with
    previous_phase = emergencia, additive changed with escalation false
    (criterion 230)."""
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "EMERGÈNCIA")])
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "ALERTA")])
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()

    started = evlog.of(EVENT_PHASE_STARTED)[0]
    assert set(started) == STARTED_FIELDS
    assert started["phase"] == Phase.ALERTA
    ended = evlog.of(EVENT_PHASE_ENDED)[0]
    assert set(ended) == ENDED_FIELDS
    assert ended["previous_phase"] == Phase.EMERGENCIA
    assert ended["previous_phase_raw"] == "EMERGÈNCIA"
    changed = evlog.of(EVENT_PHASE_CHANGED)[0]
    assert changed["escalation"] is False


# ---------------------------------------------------------------------------
# Two keys of one acronym: two started, nothing collapsed (criterion 220)
# ---------------------------------------------------------------------------


async def test_empty_to_dos_procicat_fires_two_started(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """``{}`` -> two PROCICAT phases: one started per key, none lost."""
    mock_http.get(CECAT_URL, payload=[])
    mock_http.get(CECAT_URL, payload=load_fixture("dos_procicat_SYNTHETIC"))
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()

    started = evlog.of(EVENT_PHASE_STARTED)
    assert len(started) == 2
    assert {data["phase"] for data in started} == {Phase.PREALERTA, Phase.ALERTA}
    assert all(data["acronym"] == "PROCICAT" for data in started)
    for data in started:
        assert set(data) == STARTED_FIELDS
    assert evlog.of(EVENT_PHASE_ENDED) == []
    assert evlog.of(EVENT_PHASE_CHANGED) == []


# ---------------------------------------------------------------------------
# Ambiguous cardinality: no changed, no pairing heuristic (criterion 221)
# ---------------------------------------------------------------------------


async def test_ambiguous_two_removed_one_added_no_changed(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """``{(P, p), (P, a)}`` -> ``{(P, e)}``: two ended, one started, no changed.

    The ambiguous case against a matching heuristic: nothing is paired when
    there is more than one add or one remove per acronym.
    """
    mock_http.get(CECAT_URL, payload=load_fixture("dos_procicat_SYNTHETIC"))
    mock_http.get(CECAT_URL, payload=[_row("PROCICAT", "EMERGÈNCIA")])
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()

    ended = evlog.of(EVENT_PHASE_ENDED)
    assert len(ended) == 2
    assert {data["previous_phase"] for data in ended} == {
        Phase.PREALERTA,
        Phase.ALERTA,
    }
    started = evlog.of(EVENT_PHASE_STARTED)
    assert len(started) == 1
    assert started[0]["phase"] == Phase.EMERGENCIA
    assert evlog.of(EVENT_PHASE_CHANGED) == []


async def test_inverse_cardinality_one_removed_two_added_no_changed(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """``{(P, p)}`` -> ``{(P, a), (P, e)}``: one ended, two started, no changed.

    Neither started asserts an origin: that is exactly the case where an
    origin inference would be false for at least one of the two (criterion
    222, feature-spec 11e).
    """
    mock_http.get(CECAT_URL, payload=[_row("PROCICAT", "PREALERTA", plaactivat="NO")])
    mock_http.get(
        CECAT_URL,
        payload=[_row("PROCICAT", "ALERTA"), _row("PROCICAT", "EMERGÈNCIA")],
    )
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()

    ended = evlog.of(EVENT_PHASE_ENDED)
    assert len(ended) == 1
    assert ended[0]["previous_phase"] == Phase.PREALERTA
    started = evlog.of(EVENT_PHASE_STARTED)
    assert len(started) == 2
    assert {data["phase"] for data in started} == {Phase.ALERTA, Phase.EMERGENCIA}
    for data in started:
        assert set(data) == STARTED_FIELDS
    assert evlog.of(EVENT_PHASE_CHANGED) == []


# ---------------------------------------------------------------------------
# Unrecognized side: the pair fires, changed never (criteria 223, 224, 229)
# ---------------------------------------------------------------------------


async def test_alerta_to_unrecognized_fires_pair_without_changed(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """The §4.1 asymmetry, asserted on both events of the same cycle.

    started (phase = unrecognized) carries the raw literal and no origin;
    ended carries previous_phase = alerta with its own raw literal and a
    duration. No changed: one side is not in PHASE_ORDER. No exception
    aborts the cycle (feature-spec 6b).
    """
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "ALERTA")])
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "MÀXIMA")])
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()

    started = evlog.of(EVENT_PHASE_STARTED)
    assert len(started) == 1
    assert set(started[0]) == STARTED_FIELDS
    assert started[0]["phase"] == Phase.UNRECOGNIZED
    assert started[0]["phase_raw"] == "MÀXIMA"
    assert "previous_phase" not in started[0]

    ended = evlog.of(EVENT_PHASE_ENDED)
    assert len(ended) == 1
    assert set(ended[0]) == ENDED_FIELDS
    assert ended[0]["previous_phase"] == Phase.ALERTA
    assert ended[0]["previous_phase_raw"] == "ALERTA"
    assert ended[0]["duration_minutes"] == HELPER_ROW_MINUTES

    assert evlog.of(EVENT_PHASE_CHANGED) == []


async def test_worked_example_unrecognized_to_emergencia(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """ALERTA -> MÀXIMA -> EMERGÈNCIA over two cycles (feature-spec 6c).

    The second hop fires ended(previous_phase = unrecognized, previous_phase_raw
    with the literal) + started(phase = emergencia) and no changed: the
    escalation still reaches a phase_started listener, which is the path the
    blueprint listens to.
    """
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "ALERTA")])
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "MÀXIMA")])
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "EMERGÈNCIA")])
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()  # -> unrecognized
    assert evlog.phase_types == [EVENT_PHASE_ENDED, EVENT_PHASE_STARTED]
    assert evlog.of(EVENT_PHASE_CHANGED) == []

    await coord.async_refresh()  # -> emergencia
    assert evlog.phase_types == [
        EVENT_PHASE_ENDED,
        EVENT_PHASE_STARTED,
        EVENT_PHASE_ENDED,
        EVENT_PHASE_STARTED,
    ]
    second_ended = evlog.of(EVENT_PHASE_ENDED)[1]
    assert second_ended["previous_phase"] == Phase.UNRECOGNIZED
    assert second_ended["previous_phase_raw"] == "MÀXIMA"
    second_started = evlog.of(EVENT_PHASE_STARTED)[1]
    assert second_started["phase"] == Phase.EMERGENCIA
    assert evlog.of(EVENT_PHASE_CHANGED) == []


async def test_severity_never_receives_a_phase_outside_phase_order(
    hass: HomeAssistant,
    mock_http: aioresponses,
    evlog: EventLog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pairing branch never hands ``_severity`` an unordered phase.

    A double wraps ``_severity`` in the coordinator namespace: through the
    unrecognized cycle (where no changed may fire) it must not be called at
    all, and on the ordered hop it only ever sees PHASE_ORDER members
    (criterion 226).
    """
    seen: list[Phase] = []
    real = coordinator_module._severity

    def spy(phase: Phase) -> int:
        assert phase in PHASE_ORDER, f"unordered phase reached _severity: {phase!r}"
        seen.append(phase)
        return real(phase)

    monkeypatch.setattr(coordinator_module, "_severity", spy)

    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "ALERTA")])
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "MÀXIMA")])
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "EMERGÈNCIA")])
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "ALERTA")])
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()  # -> unrecognized: pairing branch not taken
    await coord.async_refresh()  # -> emergencia: pairing branch not taken
    assert seen == []

    await coord.async_refresh()  # -> alerta: ordered pair, changed fires
    # ``escalation`` evaluates the new phase first: ALERTA then EMERGENCIA.
    assert seen == [Phase.ALERTA, Phase.EMERGENCIA]
    assert len(evlog.of(EVENT_PHASE_CHANGED)) == 1


# ---------------------------------------------------------------------------
# Disappearance in a valid cycle: ended with duration (criteria 231, 232)
# ---------------------------------------------------------------------------


async def test_valid_empty_cycle_fires_ended_with_duration(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """``{(INUNCAT, alerta)}`` -> ``{}`` in a valid cycle: one ended.

    The alerta fixture's start (2026-08-05 11:18 UTC) against the frozen
    clock (2026-08-06 11:49 UTC) is exactly 1471 whole minutes.
    """
    mock_http.get(CECAT_URL, payload=load_fixture("alerta_2026_08_06"))
    mock_http.get(CECAT_URL, payload=[])
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()

    ended = evlog.of(EVENT_PHASE_ENDED)
    assert len(ended) == 1
    assert set(ended[0]) == ENDED_FIELDS
    assert ended[0]["acronym"] == "INUNCAT"
    assert ended[0]["previous_phase"] == Phase.ALERTA
    assert ended[0]["previous_phase_raw"] == "ALERTA"
    assert ended[0]["duration_minutes"] == ALERTA_FIXTURE_MINUTES
    assert evlog.of(EVENT_PHASE_STARTED) == []
    assert evlog.of(EVENT_PHASE_CHANGED) == []


# ---------------------------------------------------------------------------
# Silence: failed cycle and pdf-only change fire nothing (criteria 233, 234)
# ---------------------------------------------------------------------------


async def test_failed_cycle_fires_no_events(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """A fetch failure must never announce a phase ended (criterion 233)."""
    mock_http.get(CECAT_URL, payload=load_fixture("alerta_2026_08_06"))
    mock_http.get(CECAT_URL, status=500)
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()  # fails

    assert evlog.types == []


async def test_comunicatpdf_change_only_fires_no_events(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """Same (acronym, phase), new pdf url: an attribute change, not an event."""
    rows = load_fixture("alerta_2026_08_06")
    new_pdf = dict(rows[0])
    new_pdf["comunicatpdf"] = {
        "url": "https://documents.dadesobertes.gencat.cat/cecat/docs/I-125912_NEW.pdf"
    }
    mock_http.get(CECAT_URL, payload=rows)
    mock_http.get(CECAT_URL, payload=[new_pdf])
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()

    assert evlog.types == []


async def test_304_fires_no_events(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """A 304 means nothing changed: state intact, no event (§5 step 2)."""
    mock_http.get(
        CECAT_URL,
        payload=load_fixture("alerta_2026_08_06"),
        headers={"Last-Modified": LAST_MODIFIED},
    )
    mock_http.get(CECAT_URL, status=304)
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()

    assert evlog.types == []


# ---------------------------------------------------------------------------
# duration_minutes None when started_at was None (criterion 236)
# ---------------------------------------------------------------------------


async def test_duration_minutes_none_when_started_at_was_none(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """A row without any usable start still starts and ends; the duration
    is None, not 0."""
    mock_http.get(CECAT_URL, payload=[])
    mock_http.get(
        CECAT_URL,
        payload=[_row("INUNCAT", "ALERTA", fasedatahora=None, **{":created_at": None})],
    )
    mock_http.get(CECAT_URL, payload=[])
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()  # appears, no usable timestamp

    started = evlog.of(EVENT_PHASE_STARTED)
    assert len(started) == 1
    assert started[0]["started_at"] is None

    await coord.async_refresh()  # disappears

    ended = evlog.of(EVENT_PHASE_ENDED)
    assert len(ended) == 1
    assert ended[0]["duration_minutes"] is None


# ---------------------------------------------------------------------------
# cecat_service_degraded: threshold and recovery (criterion 235)
# ---------------------------------------------------------------------------


async def test_three_failures_degraded_then_recovery_event(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """Three consecutive failures fire one recovered: false; the next good
    cycle fires one recovered: true. Further failures stay silent until the
    streak is crossed again."""
    for _ in range(4):
        mock_http.get(CECAT_URL, status=500)
    mock_http.get(CECAT_URL, payload=[])
    coord = CecatCoordinator(hass, _make_entry(hass))
    for _ in range(3):
        await coord.async_refresh()

    degraded = evlog.of(EVENT_SERVICE_DEGRADED)
    assert len(degraded) == 1
    assert set(degraded[0]) == {"consecutive_failures", "last_error", "recovered"}
    assert degraded[0]["recovered"] is False
    assert degraded[0]["consecutive_failures"] == 3
    assert degraded[0]["last_error"]

    await coord.async_refresh()  # fourth failure: still silent

    assert len(evlog.of(EVENT_SERVICE_DEGRADED)) == 1

    await coord.async_refresh()  # recovery

    degraded = evlog.of(EVENT_SERVICE_DEGRADED)
    assert len(degraded) == 2
    assert degraded[1]["recovered"] is True
    # No phase event fired at any point: failures carry no phase signal.
    assert evlog.phase_types == []


# ---------------------------------------------------------------------------
# Cross-acronym independence: one acronym's pairing does not leak
# ---------------------------------------------------------------------------


async def test_two_acronyms_transition_independently(
    hass: HomeAssistant, mock_http: aioresponses, evlog: EventLog
) -> None:
    """INUNCAT transitions while NEUCAT appears: the changed pairs only the
    acronym that actually has one add and one remove."""
    mock_http.get(CECAT_URL, payload=[_row("INUNCAT", "PREALERTA", plaactivat="NO")])
    mock_http.get(
        CECAT_URL,
        payload=[_row("INUNCAT", "ALERTA"), _row("NEUCAT", "ALERTA")],
    )
    coord = CecatCoordinator(hass, _make_entry(hass))
    await coord.async_refresh()
    await coord.async_refresh()

    assert len(evlog.of(EVENT_PHASE_ENDED)) == 1
    started = evlog.of(EVENT_PHASE_STARTED)
    assert {data["acronym"] for data in started} == {"INUNCAT", "NEUCAT"}
    changed = evlog.of(EVENT_PHASE_CHANGED)
    assert len(changed) == 1
    assert changed[0]["acronym"] == "INUNCAT"
    assert changed[0]["escalation"] is True
