"""Shared entity base for every cecat platform entity.

One place for the three things all entities share (docs/04-architecture.md §6):
the single service ``DeviceInfo``, the licence-mandated ``ATTRIBUTION``
(docs/01-data-sources.md §11) and the stale-data availability window of
docs/04-architecture.md §8. Platform modules subclass ``CecatEntity`` and their
HA platform class, the same ``entity.py`` pattern as the sibling repos
(docs/02-existing-integrations.md §3).

``available`` delegates to ``CecatCoordinator.available`` on purpose
(AD-12): ``CoordinatorEntity``'s default only tracks ``last_update_success``,
which keeps the last value visible through a transient glitch but can never
tell a frozen-but-empty source from a healthy empty one. Only data older than
``max(6 x interval, 1h)`` takes entities to ``unavailable``.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import CecatCoordinator

__all__ = ["CecatEntity"]


class CecatEntity(CoordinatorEntity[CecatCoordinator]):
    """Base class for cecat entities: device, attribution, availability.

    Binds to the entry's coordinator (``entry.runtime_data``,
    docs/04-architecture.md §9) and to an ``EntityDescription`` whose ``key``
    seeds the ``unique_id``. The ``entry_id`` prefix costs nothing and survives
    a future change of scope even though the integration is
    ``single_config_entry``.
    """

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self, coordinator: CecatCoordinator, description: EntityDescription
    ) -> None:
        """Attach the coordinator, the description key and the shared device."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            entry_type=DeviceEntryType.SERVICE,
            name="Protecció Civil Catalunya",
            manufacturer="Generalitat de Catalunya",
            model="CECAT, Direcció General de Protecció Civil",
            configuration_url="https://analisi.transparenciacatalunya.cat/d/wj9c-j6vf",
        )

    @property
    def available(self) -> bool:
        """Whether the coordinator's data is fresh enough to present (§8).

        The stale window, not bare ``last_update_success``: a transient network
        glitch keeps the last value visible, and only a genuinely stale source
        (older than ``max(6 x interval, 1h)``) takes the entity down.
        """
        return self.coordinator.available
