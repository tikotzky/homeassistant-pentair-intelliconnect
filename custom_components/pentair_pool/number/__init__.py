"""Number platform for pentair_pool."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.pentair_pool.const import FIELD_ICD1, PARALLEL_UPDATES as PARALLEL_UPDATES

from .chlorine_setpoint import PentairPoolChlorineSetpoint

if TYPE_CHECKING:
    from custom_components.pentair_pool.data import PentairPoolConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PentairPoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one chlorine-setpoint number per device with `icd1`."""
    coordinator = entry.runtime_data.coordinator
    entities = [
        PentairPoolChlorineSetpoint(coordinator, device_id)
        for device_id, dev in (coordinator.data or {}).items()
        if FIELD_ICD1 in (dev.get("fields") or {})
    ]
    async_add_entities(entities)
