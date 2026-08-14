"""Sensor entities: the aggregate phase, the plan count, the source timestamp.

The three entities of docs/03-feature-spec.md §3.1-§3.4, answering the one
question the integration exists for (docs/03 §1): *is any civil-protection
plan active in Catalonia right now, and in which phase?*

* ``max_phase`` (§3.1) is the dashboard entity: the highest phase with an
  order position. The aggregation filters to ``PHASE_ORDER`` *before* it
  orders (docs/04 §4), so an unrecognised literal never wins over a
  recognised phase and ``max()`` never sees a value without a position.
* ``plans`` (§3.2) counts every row in any phase, prealerta included, and is
  the only entity that carries the per-plan detail. It is **not**
  ``active_plans``: a prealerta is not an active plan, and who wants the
  activated count has the ``activated`` attribute or the binary sensor.
* ``last_updated`` (§3.4) exposes the ``Last-Modified`` header, which the
  open-data licence requires republishers to cite and which makes a frozen
  source immediately visible next to a ``none`` state.

None of them ever returns ``None`` as a state for an empty feed: the states
are ``none``, ``0`` and a diagnostic timestamp, never ``unavailable``
(docs/04 §6).
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import CecatEntity
from .models import Phase, PlanActivation, max_phase

MAX_PHASE_DESCRIPTION = SensorEntityDescription(
    key="max_phase",
    translation_key="max_phase",
)

PLANS_DESCRIPTION = SensorEntityDescription(
    key="plans",
    translation_key="plans",
)

LAST_UPDATED_DESCRIPTION = SensorEntityDescription(
    key="last_updated",
    translation_key="last_updated",
)

if TYPE_CHECKING:
    from . import CecatConfigEntry
    from .coordinator import CecatCoordinator


# Coordinator-driven, read-only platform: entities never poll or write, so no
# parallelism limit is needed. Declared explicitly for the silver
# ``parallel_updates`` quality-scale rule, same as the sibling repos.
PARALLEL_UPDATES = 0


# The ENUM options in severity order, including ``unrecognized``: the escape
# hatch must be a first-class state so the state machine can carry it (docs/03
# §3.1: the value is ``unrecognized``, never the reserved ``unknown``).
PHASE_OPTIONS: tuple[str, ...] = (
    Phase.NONE.value,
    Phase.PREALERTA.value,
    Phase.ALERTA.value,
    Phase.EMERGENCIA.value,
    Phase.UNRECOGNIZED.value,
)


def _plan_dict(activation: PlanActivation) -> dict[str, Any]:
    """Serialise one activation into the nine-field schema of docs/03 §3.2.

    ``activated_raw`` is deliberately absent: it is coordinator bookkeeping
    for diagnostics, not part of the public attribute. ``started_at`` is ISO
    8601 (or ``None``), so templates compare strings, and ``phase`` is the
    normalised value next to the always-present ``phase_raw`` literal.
    """
    return {
        "acronym": activation.acronym,
        "name": activation.name,
        "phase": activation.phase.value,
        "phase_raw": activation.phase_raw,
        "activated": activation.activated,
        "started_at": (
            activation.started_at.isoformat()
            if activation.started_at is not None
            else None
        ),
        "started_at_source": activation.started_at_source,
        "description": activation.description,
        "communique_url": activation.communique_url,
    }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CecatConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the three sensors for the entry's coordinator."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            MaxPhaseSensor(coordinator),
            PlansSensor(coordinator),
            LastUpdatedSensor(coordinator),
        ]
    )


class MaxPhaseSensor(CecatEntity, SensorEntity):
    """La fase màxima activa a Catalunya (§3.1), l'entitat principal.

    Attributes ``acronyms`` (strings, at that maximum phase) and
    ``total_plans`` (rows in any phase). The list is named ``acronyms``,
    never ``plans``: that name belongs to the object list of §3.2 alone, so
    the name says the shape (docs/04 §6).
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = list(PHASE_OPTIONS)
    _attr_translation_key = "max_phase"

    def __init__(self, coordinator: CecatCoordinator) -> None:
        """Pin the translation key and the unique-id suffix."""
        super().__init__(coordinator, MAX_PHASE_DESCRIPTION)

    @property
    def native_value(self) -> str:
        """The highest orderable phase; ``none`` for an empty feed.

        ``max_phase`` filters to ``PHASE_ORDER`` before ordering (docs/04
        §4), so a mixture of an unrecognised literal and a known phase
        yields the known one, and only a feed with no orderable phase at
        all yields ``unrecognized``. Never the reserved ``unknown``.
        """
        state = self.coordinator.data
        if state is None:
            return Phase.NONE.value
        return max_phase(activation.phase for activation in state.activations).value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Acronyms sitting at the maximum phase, plus the total row count."""
        state = self.coordinator.data
        if state is None:
            return {"acronyms": [], "total_plans": 0}
        peak = max_phase(activation.phase for activation in state.activations)
        acronyms = sorted(
            {
                activation.acronym
                for activation in state.activations
                if activation.phase is peak
            }
        )
        return {"acronyms": acronyms, "total_plans": len(state.activations)}


class PlansSensor(CecatEntity, SensorEntity):
    """Recompte de plans presents al feed, amb el detall complet (§3.2).

    The state counts distinct ``(acronym, phase)`` pairs in any phase,
    prealerta included. The ``plans`` attribute is the list of per-row
    objects in the canonical ``(acronym, phase)`` order the state already
    carries (docs/04 §6): two rows of the same acronym in different phases
    are two entries, never collapsed into one.
    """

    _attr_translation_key = "plans"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "plans"

    def __init__(self, coordinator: CecatCoordinator) -> None:
        """Pin the translation key and the unique-id suffix."""
        super().__init__(coordinator, PLANS_DESCRIPTION)

    @property
    def native_value(self) -> int:
        """How many ``(acronym, phase)`` entries the feed carries; ``0`` if none."""
        state = self.coordinator.data
        return len(state.activations) if state is not None else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The §3.2 attribute table: ``plans``, ``activated``, ``prealerta``."""
        state = self.coordinator.data
        if state is None:
            return {"plans": [], "activated": 0, "prealerta": 0}
        return {
            "plans": [_plan_dict(activation) for activation in state.activations],
            "activated": sum(
                1 for activation in state.activations if activation.activated
            ),
            "prealerta": sum(
                1
                for activation in state.activations
                if activation.phase is Phase.PREALERTA
            ),
        }


class LastUpdatedSensor(CecatEntity, SensorEntity):
    """El moment de la darrera publicació de la font (§3.4), diagnòstic.

    Parses the ``Last-Modified`` header the coordinator echoes from the
    last successful fetch. ``None`` (an ``unknown`` state) when the header
    is missing or unreadable: that is the documented empty value for this
    entity, distinct from ``unavailable`` (docs/03 §3.4).
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "last_updated"

    def __init__(self, coordinator: CecatCoordinator) -> None:
        """Pin the translation key and the unique-id suffix."""
        super().__init__(coordinator, LAST_UPDATED_DESCRIPTION)

    @property
    def native_value(self) -> datetime | None:
        """``Last-Modified`` as a timezone-aware datetime, or ``None``."""
        state = self.coordinator.data
        raw = state.last_modified if state is not None else None
        if not raw:
            return None
        try:
            parsed = parsedate_to_datetime(raw)
        except (ValueError, TypeError):
            # RFC 822 dates are the documented format, but the source is
            # free text that can change without notice: an unreadable
            # header degrades to the documented empty value.
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
