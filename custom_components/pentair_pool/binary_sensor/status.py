"""Device-status binary sensors (online + alarm)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.pentair_pool.entity import PentairPoolEntity
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

if TYPE_CHECKING:
    from custom_components.pentair_pool.coordinator import PentairPoolDataUpdateCoordinator

ONLINE_DESCRIPTION = BinarySensorEntityDescription(
    key="online",
    translation_key="online",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    has_entity_name=True,
)

ALARM_DESCRIPTION = BinarySensorEntityDescription(
    key="alarm",
    translation_key="alarm",
    device_class=BinarySensorDeviceClass.PROBLEM,
    has_entity_name=True,
)


class PentairPoolOnlineBinarySensor(BinarySensorEntity, PentairPoolEntity):
    """Top-level `online` flag from the device snapshot."""

    def __init__(
        self,
        coordinator: PentairPoolDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Bind to one device."""
        super().__init__(coordinator, ONLINE_DESCRIPTION, device_id)
        self._attr_name = "Online"

    @property
    def is_on(self) -> bool:
        """True when the device is reachable."""
        return bool(self.device_state.get("online", True))

    @property
    def available(self) -> bool:
        """Always available -- this entity is the connectivity indicator."""
        # The PentairPoolEntity base hides offline devices; for the connectivity
        # binary_sensor we want the entity to remain visible so users can see
        # when the device went offline.
        return True


class PentairPoolAlarmBinarySensor(BinarySensorEntity, PentairPoolEntity):
    """Top-level `alarm` flag from the device snapshot."""

    def __init__(
        self,
        coordinator: PentairPoolDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Bind to one device."""
        super().__init__(coordinator, ALARM_DESCRIPTION, device_id)
        self._attr_name = "Alarm"

    @property
    def is_on(self) -> bool:
        """True when the device is reporting an alarm."""
        return bool(self.device_state.get("alarm", False))
