"""The ``plan_activated`` binary sensor: is any civil-protection plan activated?

The single ``SAFETY`` question of the integration (docs/03-feature-spec.md
§3.3): ``on`` when at least one activation carries ``activated`` cert,
``off`` otherwise, including the two ``off`` states that must never read as
"something is happening": a feed of prealertas only, and the empty feed ``[]``.

This entity is why the prealerta is modelled as a first-class phase (AD-6): a
prealerta row leaves this sensor ``off`` (the source itself says a prealerta
does not activate the plan) while leaving the maximum phase at ``prealerta``.
Both are true at once, and no known consumer of this feed distinguishes them
(docs/02-existing-integrations.md §6).

``activated`` is already resolved per row by ``resolve_activated``
(``models.py``): ``False`` only on the literal ``no``, derived from the
authoritative ``plafase`` otherwise (AD-6). A literal ``plaactivat == "SI"``
comparison here would re-import the trap the models module exists to defuse
(trap 1 and trap 14: ``Si``, ``" SI "`` and an absent field must all read as
activated on an ``EMERGÈNCIA`` row).

The attribute is ``acronyms``: the sorted, deduplicated list of activated
acronyms. It is **not** named ``plans``: that name designates exactly one
shape in this integration, the list of objects of ``sensor...._plans``
(docs/04-architecture.md §6), and a name with two incompatible shapes makes a
mis-aimed ``selectattr`` fail loudly instead of silently returning nonsense.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CecatConfigEntry
from .entity import CecatEntity

__all__ = ["PLAN_ACTIVATED_DESCRIPTION", "CecatPlanActivatedBinarySensor"]

PLAN_ACTIVATED_DESCRIPTION = BinarySensorEntityDescription(
    key="plan_activated",
)


class CecatPlanActivatedBinarySensor(CecatEntity, BinarySensorEntity):
    """``on`` exactly while some plan row carries ``activated`` cert."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_translation_key = "plan_activated"

    @property
    def is_on(self) -> bool | None:
        """Any activation with ``activated`` cert (docs/03 §3.3).

        Never ``None``: the coordinator's first refresh completes before the
        platform sets up, so ``data`` is always a ``CecatState`` here, and
        ``any()`` over its (possibly empty) activations is a plain ``bool``.
        ``[]`` reads as ``off``, never ``unknown`` (criterion 1 of
        docs/03-feature-spec.md §9).
        """
        return any(
            activation.activated for activation in self.coordinator.data.activations
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """``acronyms``: sorted, deduplicated acronyms of the activated rows.

        Deduplicated because the question is "which plans are activated", not
        "how many rows say so": two PROCICAT phases live in one entry here.
        Sorted so a reordered feed never produces a spurious attribute change.
        """
        return {
            "acronyms": sorted(
                {
                    activation.acronym
                    for activation in self.coordinator.data.activations
                    if activation.activated
                }
            )
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CecatConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the one ``plan_activated`` entity fed by the entry's coordinator."""
    coordinator = entry.runtime_data
    async_add_entities(
        [CecatPlanActivatedBinarySensor(coordinator, PLAN_ACTIVATED_DESCRIPTION)]
    )
