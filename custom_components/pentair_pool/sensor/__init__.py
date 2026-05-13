"""Sensor platform for pentair_pool."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.pentair_pool.const import FIELD_RAS0, PARALLEL_UPDATES as PARALLEL_UPDATES

from .cooldown import PentairPoolCooldownCountdown
from .telemetry import SENSORS, PentairPoolFieldSensor

if TYPE_CHECKING:
    from custom_components.pentair_pool.data import PentairPoolConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PentairPoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one field-backed sensor per (device, field).

    Also adds the live cooldown countdown for devices that expose `ras0`
    (Relay1_Timer_Status).
    """
    coordinator = entry.runtime_data.coordinator
    entities = []
    for device_id, dev in (coordinator.data or {}).items():
        fields = dev.get("fields") or {}
        for field_code, desc in SENSORS:
            if field_code in fields:
                entities.append(
                    PentairPoolFieldSensor(coordinator, device_id, field_code, desc),
                )
        if FIELD_RAS0 in fields:
            entities.append(PentairPoolCooldownCountdown(coordinator, device_id))
    async_add_entities(entities)
