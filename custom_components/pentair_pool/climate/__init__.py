"""Climate platform for pentair_pool (pool heater)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.pentair_pool.const import FIELD_HTD1, PARALLEL_UPDATES as PARALLEL_UPDATES

from .heater import PentairPoolHeater

if TYPE_CHECKING:
    from custom_components.pentair_pool.data import PentairPoolConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PentairPoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one heater per device that exposes `htd1` (Heater_Mode)."""
    coordinator = entry.runtime_data.coordinator
    entities = [
        PentairPoolHeater(coordinator, device_id)
        for device_id, dev in (coordinator.data or {}).items()
        if FIELD_HTD1 in (dev.get("fields") or {})
    ]
    async_add_entities(entities)
