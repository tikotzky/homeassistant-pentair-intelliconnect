"""Switch platform for pentair_pool."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.pentair_pool.const import FIELD_RA0, PARALLEL_UPDATES as PARALLEL_UPDATES

from .pump import PentairPoolPumpSwitch
from .schedule import PentairPoolDailyScheduleSwitch

if TYPE_CHECKING:
    from custom_components.pentair_pool.data import PentairPoolConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: PentairPoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform.

    Both switches are gated on the presence of `ra0` for that Pentair device,
    so devices without a Relay-1 wired to the IntelliConnect won't produce
    orphan entities.
    """
    coordinator = entry.runtime_data.coordinator
    entities = []
    for device_id, dev in (coordinator.data or {}).items():
        if FIELD_RA0 not in (dev.get("fields") or {}):
            continue
        entities.append(PentairPoolPumpSwitch(coordinator, device_id))
        entities.append(PentairPoolDailyScheduleSwitch(coordinator, device_id))
    async_add_entities(entities)
