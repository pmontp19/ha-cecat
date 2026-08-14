"""The data coordinator for the cecat integration.

One ``DataUpdateCoordinator`` per config entry owns the cycle-to-cycle state of
the CECAT feed (docs/04-architecture.md §5): the previous snapshot keyed by
``(acronym, phase)``, the ``Last-Modified`` value for conditional caching, the
sets of unknown literals that have already earned their single warning, and
the resilience counters behind ``cecat_service_degraded``.

``_emit_events`` reconciles ``_previous`` against each new snapshot and fires
the bus events of docs/03-feature-spec.md §4: ``phase_started`` for every key
that appears and ``phase_ended`` for every key that disappears, always and
without suppression, plus an additive ``phase_changed`` behind three
conditions. The payloads are written out in full at each call site so they
read field by field against the spec. A frozen state never loses a plan, a
304 never recomputes anything, and a failed cycle never announces a phase
ended.

State lives on ``entry.runtime_data`` (docs/04-architecture.md §9), never on
``hass.data``: this is a single-config-entry service integration, and
``runtime_data`` is the typed handle every platform reads.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util.dt import utcnow

from .api import CecatConnectionError, CecatFormatError, fetch
from .const import (
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    EVENT_PHASE_CHANGED,
    EVENT_PHASE_ENDED,
    EVENT_PHASE_STARTED,
    EVENT_SERVICE_DEGRADED,
    MAX_SCAN_INTERVAL_MIN,
    MIN_SCAN_INTERVAL_MIN,
)
from .models import (
    PHASE_ORDER,
    PLAN_NAMES,
    CecatState,
    Phase,
    PlanActivation,
    _severity,
)

_LOGGER = logging.getLogger(__name__)

# docs/04-architecture.md §8: three consecutive failures are a degraded source.
# Crossing the threshold fires ``cecat_service_degraded`` once per streak.
_DEGRADED_FAILURE_THRESHOLD = 3

# Stale-data window (docs/04-architecture.md §8): entities go ``available =
# False`` once the last successful fetch is older than ``max(6 x interval, 1h)``.
# With the default 5 min interval that floor is 1 h, the only signal that
# separates a frozen-but-empty source from a healthy empty one.
_STALE_FLOOR = timedelta(hours=1)

# The options key that sets the poll interval (docs/04-architecture.md §7). The
# constant for it lands in ``const.py`` with the full options flow in T9; the
# coordinator reads it by name now so T9 only has to add the constant.
CONF_SCAN_INTERVAL = "scan_interval"


class CecatCoordinator(TimestampDataUpdateCoordinator[CecatState]):
    """Holds the CECAT snapshot between cycles and prepares the reconcile state.

    ``always_update=False`` plus ``CecatState``'s value equality means entities
    wake only when the activation picture actually changed: a re-ordered but
    identical payload, or a 304, does not fire ``async_update_listeners``.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Arm the coordinator with the entry's poll interval (default 5 min)."""
        minutes = _scan_interval_minutes(entry.options)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
            config_entry=entry,
            always_update=False,
        )
        # Reconciliation baseline (docs/04-architecture.md §5). Keyed by
        # ``(acronym, phase)`` (AD-5): two PROCICAT plans in different phases
        # are two entries, never collapsed into one.
        self._previous: dict[tuple[str, Phase], PlanActivation] = {}
        # ``If-Modified-Since`` for the next fetch; set on every 200, untouched
        # on a 304.
        self._last_modified: str | None = None
        # One warning per literal, across cycles (§5 "Literals desconeguts").
        # Three independent sets so the three traps never mask each other.
        self._unknown_phases: set[str] = set()
        self._unknown_acronyms: set[str] = set()
        self._unknown_activated: set[str] = set()
        # Resilience bookkeeping (§8). The event firing is T8.
        self._consecutive_failures = 0
        self._degraded = False
        # First cycle seeds ``_previous`` silently (§5 Cicle step 5); without
        # this guard every restart would replay each active plan as ``started``.
        self.is_first_refresh = True
        # Surface of the last failure for diagnostics; the state itself stays.
        self.last_error: str | None = None

    # ------------------------------------------------------------------
    # Cycle (docs/04-architecture.md §5 "Cicle")
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> CecatState:
        """Fetch one cycle and fold it into a fresh state.

        A 304 returns ``self.data`` untouched (step 2). A failure preserves
        ``_previous`` and raises ``UpdateFailed`` so HA keeps the last good
        ``self.data`` (step 3): no event fires on a failed cycle, because a
        network glitch must never announce that an emergency is over. A 200
        builds the new state, warns once per unknown literal, diffs against
        ``_previous`` to fire the phase events, and makes the new picture the
        reconciliation baseline (steps 4-7).
        """
        try:
            result = await fetch(self.hass, self._last_modified)
        except (CecatConnectionError, CecatFormatError) as err:
            # A failed cycle must never drop a plan or fire phase_ended (§5
            # step 3): only a valid ``[]`` is a deactivation. ``_previous`` is
            # left untouched and HA keeps ``self.data`` on ``UpdateFailed``.
            self._record_failure(err)
            raise UpdateFailed(str(err)) from err

        if result.not_modified:
            # 304: the source says nothing changed. Return ``self.data``
            # untouched, no recompute, no warnings, no events (§5 step 2). A
            # 304 only happens after a 200 set ``_last_modified``, so
            # ``self.data`` is populated; the fallback guards an impossible
            # 304-before-any-data.
            return self.data if self.data is not None else CecatState()

        # A 200 ends any standing failure streak (§5 step 6). If the streak
        # had crossed the threshold, fire the one-shot recovery event before
        # the counters reset.
        if self._degraded:
            self._degraded = False
            self._fire(
                EVENT_SERVICE_DEGRADED,
                consecutive_failures=0,
                last_error=self.last_error,
                recovered=True,
            )
        self._consecutive_failures = 0

        current = CecatState.from_rows(
            result.rows or [], last_modified=result.last_modified
        )
        self._warn_unknown_literals(current.by_key)

        # Seed on the first cycle so a restart never replays every active plan
        # as ``started``; from the second on, diff ``_previous`` against the
        # new snapshot and fire the phase events (§5 step 5). Either way the
        # new picture becomes the baseline for the next cycle.
        if self.is_first_refresh:
            self.is_first_refresh = False
        else:
            self._emit_events(self._previous, current.by_key)
        self._previous = dict(current.by_key)
        self._last_modified = result.last_modified
        return current

    # ------------------------------------------------------------------
    # Availability (docs/04-architecture.md §8)
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Whether the source's data is fresh enough to present (§8).

        Entities read this instead of ``last_update_success`` so a transient
        network glitch keeps the last value visible: only a genuinely stale
        source (older than ``max(6 x interval, 1h)``) takes them to
        ``unavailable``. With ``[]`` as the normal state, that staleness is the
        only signal that separates a frozen source from a healthy empty one.
        """
        if self.last_update_success_time is None:
            return False
        return utcnow() - self.last_update_success_time <= self._stale_after

    @property
    def _stale_after(self) -> timedelta:
        """``max(6 x interval, 1h)``: how long the last good data stays trusted."""
        interval = self.update_interval or timedelta(minutes=DEFAULT_SCAN_INTERVAL_MIN)
        return max(interval * 6, _STALE_FLOOR)

    # ------------------------------------------------------------------
    # Resilience bookkeeping (event firing is T8)
    # ------------------------------------------------------------------

    def _record_failure(self, err: Exception) -> None:
        """Count the failure, stamp ``last_error``, fire degraded at threshold.

        ``cecat_service_degraded`` fires exactly once per streak: the
        ``_degraded`` flag keeps cycles 4, 5, ... silent until a success
        resets it. The repair issue that completes this diagnostics story is
        T10.
        """
        self.last_error = str(err) or type(err).__name__
        self._consecutive_failures += 1
        if (
            self._consecutive_failures >= _DEGRADED_FAILURE_THRESHOLD
            and not self._degraded
        ):
            self._degraded = True
            self._fire(
                EVENT_SERVICE_DEGRADED,
                consecutive_failures=self._consecutive_failures,
                last_error=self.last_error,
                recovered=False,
            )

    # ------------------------------------------------------------------
    # Event emission (docs/04-architecture.md §5 "_emit_events")
    # ------------------------------------------------------------------

    def _emit_events(
        self,
        previous: Mapping[tuple[str, Phase], PlanActivation],
        current: Mapping[tuple[str, Phase], PlanActivation],
    ) -> None:
        """Diff two snapshots by ``(acronym, phase)`` key and fire the events.

        ``phase_ended`` for every removed key and ``phase_started`` for every
        added key, always, in that order and without exceptions; then an
        additive ``phase_changed`` per acronym whose add/remove diff is
        exactly 1-to-1 with both phases in ``PHASE_ORDER``. No event ever
        suppresses another, and no pairing heuristic exists beyond that rule:
        with more than one add or one remove per acronym there is no honest
        way to say which plan "changed phase", so none is asserted.

        Only ever called from the second cycle on: the first cycle seeds
        ``_previous`` silently so a restart does not replay every active plan
        as ``started``.
        """
        added = current.keys() - previous.keys()
        removed = previous.keys() - current.keys()

        # 1. Always, without exceptions or suppression. Sorted for a
        # deterministic order: the feed guarantees no row order (§6).
        for key in sorted(removed):
            old = previous[key]
            self._fire(
                EVENT_PHASE_ENDED,
                acronym=old.acronym,
                name=old.name,
                previous_phase=old.phase,
                previous_phase_raw=old.phase_raw,
                duration_minutes=_duration_minutes(old),
            )
        for key in sorted(added):
            new = current[key]
            # A row never carries Phase.NONE (it only exists as the aggregate
            # of an empty feed), but the guard costs nothing and keeps the
            # started payload honest if that ever changes.
            if new.phase is Phase.NONE:
                continue
            self._fire(
                EVENT_PHASE_STARTED,
                acronym=new.acronym,
                name=new.name,
                phase=new.phase,
                phase_raw=new.phase_raw,
                activated=new.activated,
                started_at=new.started_at,
                description=new.description,
                communique_url=new.communique_url,
            )

        # 2. Additionally, when the three conditions hold, one change event
        # per acronym: exactly one add, exactly one remove, and both phases
        # in PHASE_ORDER (no UNRECOGNIZED side, AD-8).
        for acronym in sorted({acronym for acronym, _ in added | removed}):
            adds = [key for key in added if key[0] == acronym]
            removes = [key for key in removed if key[0] == acronym]
            pairs = (
                len(adds) == 1
                and len(removes) == 1
                and adds[0][1] in PHASE_ORDER
                and removes[0][1] in PHASE_ORDER
            )
            if pairs:
                new = current[adds[0]]
                old = previous[removes[0]]
                self._fire(
                    EVENT_PHASE_CHANGED,
                    acronym=new.acronym,
                    name=new.name,
                    previous_phase=old.phase,
                    previous_phase_raw=old.phase_raw,
                    phase=new.phase,
                    phase_raw=new.phase_raw,
                    escalation=_severity(new.phase) > _severity(old.phase),
                    activated=new.activated,
                    started_at=new.started_at,
                )

    def _fire(self, event_type: str, **data: Any) -> None:
        """Fire a bus event whose payload is exactly the given kwargs.

        ``_fire`` adds and completes nothing from the ``PlanActivation``: each
        payload is written out in full at its call site (§5), so the three
        payloads read directly from the three calls and compare field by
        field with docs/03-feature-spec.md §4.1, §4.2 and §4.3. In particular
        ``phase_ended`` carries no ``phase`` nor ``phase_raw`` on purpose: the
        phase of the key that vanished already travels as ``previous_phase``,
        and carrying it twice under two names invites reading it as the
        plan's current phase.
        """
        self.hass.bus.async_fire(event_type, data)

    # ------------------------------------------------------------------
    # Unknown-literal warnings (one per literal, not per cycle)
    # ------------------------------------------------------------------

    def _warn_unknown_literals(
        self, by_key: Mapping[tuple[str, Phase], PlanActivation]
    ) -> None:
        """Emit one ``warning`` per unknown literal, ever (§5).

        Without the per-literal guard a 5 min poll would write 288 lines a day
        per literal. The three sets are separate by design: a ``plafase`` the
        source invented, a ``plaacronim`` never seen, and a ``plaactivat`` that
        had to be derived from the phase are independent traps.
        """
        for activation in by_key.values():
            acronym = activation.acronym
            if (
                acronym
                and acronym.upper() not in PLAN_NAMES
                and acronym not in self._unknown_acronyms
            ):
                self._unknown_acronyms.add(acronym)
                _LOGGER.warning(
                    "Pla desconegut: l'acrònim %r no és al registre de plans",
                    acronym,
                )
            if (
                activation.phase is Phase.UNRECOGNIZED
                and activation.phase_raw
                and activation.phase_raw not in self._unknown_phases
            ):
                self._unknown_phases.add(activation.phase_raw)
                _LOGGER.warning(
                    "Fase de pla no reconeguda: %r (pla %s)",
                    activation.phase_raw,
                    acronym,
                )
            if (
                activation.activated_raw is not None
                and activation.activated_raw not in self._unknown_activated
            ):
                self._unknown_activated.add(activation.activated_raw)
                _LOGGER.warning(
                    "Valor de plaactivat no reconegut: %r (pla %s). "
                    "S'ha derivat de la fase %s",
                    activation.activated_raw,
                    acronym,
                    activation.phase,
                )

    # ------------------------------------------------------------------
    # Read-only surface for T8 events and the diagnostics export
    # ------------------------------------------------------------------

    @property
    def previous(self) -> dict[tuple[str, Phase], PlanActivation]:
        """The last successful snapshot, keyed by ``(acronym, phase)``."""
        return self._previous

    @property
    def last_modified(self) -> str | None:
        """The ``Last-Modified`` to echo back as ``If-Modified-Since``."""
        return self._last_modified

    @property
    def consecutive_failures(self) -> int:
        """How many fetches in a row have failed (docs/04-architecture.md §8)."""
        return self._consecutive_failures

    @property
    def degraded(self) -> bool:
        """Whether the degraded threshold has been crossed this streak."""
        return self._degraded

    @property
    def unknown_phases(self) -> set[str]:
        """Literals seen at ``plafase`` that did not map to a known phase."""
        return self._unknown_phases

    @property
    def unknown_acronyms(self) -> set[str]:
        """Acronyms seen at ``plaacronim`` that are not in the plan registry."""
        return self._unknown_acronyms

    @property
    def unknown_activated(self) -> set[str]:
        """Literals seen at ``plaactivat`` that had to be derived from the phase."""
        return self._unknown_activated


def _duration_minutes(activation: PlanActivation) -> int | None:
    """Whole minutes the phase lasted, or ``None`` when ``started_at`` was.

    Measured from ``started_at`` to now (the poll resolution, docs/03 §4.3:
    the CECAT publishes almost no closing communiques, so the instant of an
    end is only as precise as the polling interval). ``None``, not 0, when
    the row carried no usable start: a row with no timestamp is still a valid
    activation, and 0 would assert a duration we never observed.
    """
    if activation.started_at is None:
        return None
    seconds = (utcnow() - activation.started_at).total_seconds()
    return int(seconds // 60)


def _scan_interval_minutes(options: Mapping[str, object]) -> int:
    """Read the poll interval from options, falling back to the 5 min default.

    Clamped to the documented bounds so a stale or hand-edited option never
    presses the source below the 1 min floor or stretches it past 1 h.
    """
    raw = options.get(CONF_SCAN_INTERVAL)
    try:
        minutes = int(raw) if raw is not None else DEFAULT_SCAN_INTERVAL_MIN
    except (TypeError, ValueError):
        return DEFAULT_SCAN_INTERVAL_MIN
    return max(MIN_SCAN_INTERVAL_MIN, min(MAX_SCAN_INTERVAL_MIN, minutes))
