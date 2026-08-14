"""The data coordinator for the cecat integration.

One ``DataUpdateCoordinator`` per config entry owns the cycle-to-cycle state of
the CECAT feed (docs/04-architecture.md §5): the previous snapshot keyed by
``(acronym, phase)``, the ``Last-Modified`` value for conditional caching, the
sets of unknown literals that have already earned their single warning, and the
resilience counters that T8 turns into the ``cecat_service_degraded`` event.

This module deliberately does **not** fire bus events. Reconciling ``_previous``
against the new snapshot and emitting ``phase_started`` / ``phase_changed`` /
``phase_ended`` is the job of T8 (``_emit_events``); the degraded event is T8
too. Here we only maintain the state those events need, so a frozen state never
loses a plan and a 304 never recomputes anything.

State lives on ``entry.runtime_data`` (docs/04-architecture.md §9), never on
``hass.data``: this is a single-config-entry service integration, and
``runtime_data`` is the typed handle every platform reads.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import timedelta

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
    MAX_SCAN_INTERVAL_MIN,
    MIN_SCAN_INTERVAL_MIN,
)
from .models import PLAN_NAMES, CecatState, Phase, PlanActivation

_LOGGER = logging.getLogger(__name__)

# docs/04-architecture.md §8: three consecutive failures are a degraded source.
# The count is maintained here; firing ``cecat_service_degraded`` is T8.
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
        ``self.data`` (step 3). A 200 builds the new state, warns once per
        unknown literal, and makes the new picture the reconciliation baseline
        (steps 4-7). Event emission is deferred to T8.
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

        # A 200 ends any standing failure streak (§5 step 6). The recovery
        # event is T8.
        self._consecutive_failures = 0
        if self._degraded:
            self._degraded = False

        current = CecatState.from_rows(
            result.rows or [], last_modified=result.last_modified
        )
        self._warn_unknown_literals(current.by_key)

        # Seed on the first cycle; from the second on, T8 diffs ``_previous``
        # against ``current`` here. Either way the new picture becomes the
        # baseline for the next cycle (§5 step 5).
        self._previous = dict(current.by_key)
        self.is_first_refresh = False
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
        """Count the failure, stamp ``last_error``, flag degraded at threshold.

        The ``cecat_service_degraded`` event and repair issue fire in T8; here
        we only keep the streak and the one-shot flag so the threshold and the
        recovery are detectable.
        """
        self.last_error = str(err) or type(err).__name__
        self._consecutive_failures += 1
        if (
            self._consecutive_failures >= _DEGRADED_FAILURE_THRESHOLD
            and not self._degraded
        ):
            self._degraded = True

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
