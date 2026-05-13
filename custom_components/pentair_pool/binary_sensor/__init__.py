"""Binary-sensor platform for pentair_pool."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.pentair_pool.const import FIELD_RA4, PARALLEL_UPDATES as PARALLEL_UPDATES

from .pump_running import PentairPoolPumpRunningBinarySensor
from .status import PentairPoolAlarmBinarySensor, PentairPoolOnlineBinarySensor

if TYPE_CHECKING:
    from custom_components.pentair_pool.data import PentairPoolConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PentairPoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add per-device binary sensors."""
    coordinator = entry.runtime_data.coordinator
    entities = []
    for device_id, dev in (coordinator.data or {}).items():
        entities.append(PentairPoolOnlineBinarySensor(coordinator, device_id))
        entities.append(PentairPoolAlarmBinarySensor(coordinator, device_id))
        if FIELD_RA4 in (dev.get("fields") or {}):
            entities.append(PentairPoolPumpRunningBinarySensor(coordinator, device_id))
    async_add_entities(entities)
