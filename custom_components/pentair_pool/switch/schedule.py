"""Daily Schedule enable/disable switch."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from custom_components.pentair_pool.const import (
    FIELD_RA0,
    RA0_OFF_NO_SCHEDULE,
    RA0_OFF_SCHEDULED,
    RA0_ON_NO_SCHEDULE,
    RA0_ON_SCHEDULED,
)
from custom_components.pentair_pool.entity import PentairPoolEntity
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory

if TYPE_CHECKING:
    from custom_components.pentair_pool.coordinator import PentairPoolDataUpdateCoordinator

SCHEDULE_ON = {RA0_OFF_SCHEDULED, RA0_ON_SCHEDULED, "4"}
PUMP_ON = {RA0_ON_NO_SCHEDULE, RA0_ON_SCHEDULED}

DESCRIPTION = SwitchEntityDescription(
    key="daily_schedule",
    translation_key="daily_schedule",
    icon="mdi:calendar-clock",
    entity_category=EntityCategory.CONFIG,
    has_entity_name=True,
)


class PentairPoolDailyScheduleSwitch(SwitchEntity, PentairPoolEntity):
    """Toggle Daily Schedule, preserving the current pump-on/off bit."""

    def __init__(
        self,
        coordinator: PentairPoolDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Bind to one device."""
        super().__init__(coordinator, DESCRIPTION, device_id)
        self._attr_name = "Daily schedule"

    @property
    def is_on(self) -> bool | None:
        """Schedule state from `ra0`."""
        v = self.field_value(FIELD_RA0)
        if v is None:
            return None
        return v in SCHEDULE_ON

    async def async_turn_on(self, **_: Any) -> None:
        """Enable schedule, preserving pump on/off."""
        pump = (self.field_value(FIELD_RA0) or "") in PUMP_ON
        target = RA0_ON_SCHEDULED if pump else RA0_OFF_SCHEDULED
        await self.coordinator.async_set_fields(self._device_id, {FIELD_RA0: target})

    async def async_turn_off(self, **_: Any) -> None:
        """Disable schedule, preserving pump on/off."""
        pump = (self.field_value(FIELD_RA0) or "") in PUMP_ON
        target = RA0_ON_NO_SCHEDULE if pump else RA0_OFF_NO_SCHEDULE
        await self.coordinator.async_set_fields(self._device_id, {FIELD_RA0: target})
