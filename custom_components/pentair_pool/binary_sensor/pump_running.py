"""Physical-pump-state binary sensor.

Reports whether Relay 1 is actually drawing power. This is the "truth"
companion to `switch.<device>_filter_pump` (which represents user intent).
When they disagree, the firmware is either:
  - running the pump via Daily Schedule despite the intent being off, or
  - holding the pump on for heater cooldown despite the intent being off, or
  - the command hasn't propagated yet (typical lag is 1-3 s).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.pentair_pool.const import FIELD_RA4
from custom_components.pentair_pool.entity import PentairPoolEntity
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

if TYPE_CHECKING:
    from custom_components.pentair_pool.coordinator import PentairPoolDataUpdateCoordinator

DESCRIPTION = BinarySensorEntityDescription(
    key="filter_pump_running",
    translation_key="filter_pump_running",
    device_class=BinarySensorDeviceClass.RUNNING,
    has_entity_name=True,
)


class PentairPoolPumpRunningBinarySensor(BinarySensorEntity, PentairPoolEntity):
    """`Relay1_Power > 0` indicator."""

    def __init__(
        self,
        coordinator: PentairPoolDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Bind to one device."""
        super().__init__(coordinator, DESCRIPTION, device_id)
        self._attr_name = "Filter pump running"

    @property
    def is_on(self) -> bool | None:
        """True when the pump is drawing power."""
        v = self.field_value(FIELD_RA4)
        if v is None:
            return None
        try:
            return int(v) > 0
        except ValueError:
            return None
