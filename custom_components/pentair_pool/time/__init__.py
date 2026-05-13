"""Time platform: editable Daily Schedule start / end."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.pentair_pool.const import FIELD_RA1, FIELD_RA2, PARALLEL_UPDATES as PARALLEL_UPDATES

from .schedule import PentairPoolScheduleEnd, PentairPoolScheduleStart

if TYPE_CHECKING:
    from custom_components.pentair_pool.data import PentairPoolConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: PentairPoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """One pair of time entities per device that has ra1/ra2 schedule fields."""
    coordinator = entry.runtime_data.coordinator
    entities = []
    for device_id, dev in (coordinator.data or {}).items():
        fields = dev.get("fields") or {}
        if FIELD_RA1 in fields:
            entities.append(PentairPoolScheduleStart(coordinator, device_id))
        if FIELD_RA2 in fields:
            entities.append(PentairPoolScheduleEnd(coordinator, device_id))
    async_add_entities(entities)
