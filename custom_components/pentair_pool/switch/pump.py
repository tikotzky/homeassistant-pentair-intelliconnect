"""Filter pump on/off switch."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from custom_components.pentair_pool.const import (
    FIELD_RA0,
    FIELD_RA4,
    RA0_OFF_NO_SCHEDULE,
    RA0_OFF_SCHEDULED,
    RA0_ON_NO_SCHEDULE,
    RA0_ON_SCHEDULED,
    RA0_TIMER_DONE_SCHEDULED,
)
from custom_components.pentair_pool.entity import PentairPoolEntity
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription

if TYPE_CHECKING:
    from custom_components.pentair_pool.coordinator import PentairPoolDataUpdateCoordinator

SCHEDULE_ON = {RA0_OFF_SCHEDULED, RA0_ON_SCHEDULED, RA0_TIMER_DONE_SCHEDULED}
PUMP_INTENT_ON = {RA0_ON_NO_SCHEDULE, RA0_ON_SCHEDULED}

DESCRIPTION = SwitchEntityDescription(
    key="filter_pump",
    translation_key="filter_pump",
    icon="mdi:pump",
    has_entity_name=True,
)


class PentairPoolPumpSwitch(SwitchEntity, PentairPoolEntity):
    """Filter pump intent switch.

    `is_on` reflects the user's manual-override **intent** stored in `ra0`,
    NOT the physical pump state (which can lag commands by 1-3 s, or never
    apply if the Daily Schedule is firing or the heater is in cooldown). This
    makes the toggle predictable: tapping it flips the displayed state
    immediately and stays.

    The actual physical state is exposed separately as
    `binary_sensor.<device>_filter_pump_running` (derived from `ra4 > 0`).

    Writes always target `ra0`, preserving the schedule bit so the user
    doesn't accidentally disable their Daily Schedule by toggling the pump.
    """

    def __init__(
        self,
        coordinator: PentairPoolDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Bind to one device."""
        super().__init__(coordinator, DESCRIPTION, device_id)
        self._attr_name = "Filter pump"

    @property
    def is_on(self) -> bool | None:
        """True when ra0 encodes a manual ON intent.

        Schedule-enabled OFF ("2") and schedule-disabled OFF ("0") both
        return False; the firmware may still be running the pump because of
        the schedule -- check `binary_sensor.*_filter_pump_running` for that.
        """
        v = self.field_value(FIELD_RA0)
        if v is None:
            return None
        return v in PUMP_INTENT_ON

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Expose the raw override field for automations + debugging."""
        return {
            "ra0": self.field_value(FIELD_RA0),
            "ra4_watts": self.field_value(FIELD_RA4),
        }

    async def async_turn_on(self, **_: Any) -> None:
        """Set the override on, preserving the schedule bit.

        Note: when the pump is already off and the Daily Schedule isn't
        currently in its window, this will start the pump immediately.
        """
        sched = (self.field_value(FIELD_RA0) or "") in SCHEDULE_ON
        target = RA0_ON_SCHEDULED if sched else RA0_ON_NO_SCHEDULE
        await self.coordinator.async_set_fields(self._device_id, {FIELD_RA0: target})

    async def async_turn_off(self, **_: Any) -> None:
        """Set the override off, preserving the schedule bit.

        Note: this clears the manual override but does NOT cancel the Daily
        Schedule. If the schedule is currently firing, the pump will keep
        running until the schedule window closes. To stop the pump
        unconditionally, also turn off the Daily Schedule switch.
        """
        sched = (self.field_value(FIELD_RA0) or "") in SCHEDULE_ON
        target = RA0_OFF_SCHEDULED if sched else RA0_OFF_NO_SCHEDULE
        await self.coordinator.async_set_fields(self._device_id, {FIELD_RA0: target})
