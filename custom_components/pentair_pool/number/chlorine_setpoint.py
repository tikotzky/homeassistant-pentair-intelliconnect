"""IntelliChlor chlorine-output target (`icd1`, 0-100 %)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.pentair_pool.const import FIELD_ICD1
from custom_components.pentair_pool.entity import PentairPoolEntity
from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE

if TYPE_CHECKING:
    from custom_components.pentair_pool.coordinator import PentairPoolDataUpdateCoordinator

DESCRIPTION = NumberEntityDescription(
    key="chlorine_setpoint",
    translation_key="chlorine_setpoint",
    icon="mdi:water-percent",
    native_min_value=0,
    native_max_value=100,
    native_step=1,
    native_unit_of_measurement=PERCENTAGE,
    has_entity_name=True,
)


class PentairPoolChlorineSetpoint(NumberEntity, PentairPoolEntity):
    """Salt-cell chlorine output % (`icd1`)."""

    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: PentairPoolDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Bind to one device."""
        super().__init__(coordinator, DESCRIPTION, device_id)
        self._attr_name = "Chlorine output"

    @property
    def native_value(self) -> float | None:
        """Current setpoint."""
        v = self.field_value(FIELD_ICD1)
        if v is None:
            return None
        try:
            return float(v)
        except ValueError:
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Send new setpoint."""
        await self.coordinator.async_set_fields(
            self._device_id, {FIELD_ICD1: int(round(value))},
        )
