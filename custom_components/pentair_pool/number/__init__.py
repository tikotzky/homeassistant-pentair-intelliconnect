"""Number platform for pentair_pool."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.pentair_pool.const import PARALLEL_UPDATES as PARALLEL_UPDATES
from homeassistant.components.number import NumberEntityDescription

from .target_humidity import ENTITY_DESCRIPTIONS as HUMIDITY_DESCRIPTIONS, PentairPoolHumidityNumber

if TYPE_CHECKING:
    from custom_components.pentair_pool.data import PentairPoolConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

# Combine all entity descriptions from different modules
ENTITY_DESCRIPTIONS: tuple[NumberEntityDescription, ...] = (*HUMIDITY_DESCRIPTIONS,)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PentairPoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform."""
    async_add_entities(
        PentairPoolHumidityNumber(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
        )
        for entity_description in HUMIDITY_DESCRIPTIONS
    )
