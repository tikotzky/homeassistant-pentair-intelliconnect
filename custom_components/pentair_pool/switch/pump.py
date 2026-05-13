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
from homeassistant.core import callback

if TYPE_CHECKING:
    from custom_components.pentair_pool.coordinator import PentairPoolDataUpdateCoordinator

SCHEDULE_ON = {RA0_OFF_SCHEDULED, RA0_ON_SCHEDULED, RA0_TIMER_DONE_SCHEDULED}

DESCRIPTION = SwitchEntityDescription(
    key="filter_pump",
    translation_key="filter_pump",
    icon="mdi:pump",
    has_entity_name=True,
)


class PentairPoolPumpSwitch(SwitchEntity, PentairPoolEntity):
    """Filter pump switch.

    `is_on` follows the pump's actual running state (`ra4 > 0`) so the
    switch reads ON whenever the pump is circulating water -- whether
    that's a manual override, a Daily Schedule firing, or a heater
    cooldown extending the run. This matches what the Pentair app shows.

    When the user toggles the switch we hold an optimistic "pending"
    state that overrides the displayed value until reality (`ra4`)
    catches up. That gives two important properties:

      1. Tap responsiveness: the switch flips immediately on tap and
         doesn't bounce back during the 1-3 s the firmware takes to
         apply the command or while WS pushes are in flight.
      2. Cooldown intent preservation: if the user taps OFF while the
         heater is in cooldown (`ra4` won't drop for several minutes),
         the switch stays OFF the entire time -- their intent is clearly
         "stop", and the pump will eventually obey when cooldown ends.

    Writes always target `ra0`, preserving the schedule bit so the user
    doesn't accidentally disable their Daily Schedule by toggling the
    pump on/off.
    """

    def __init__(
        self,
        coordinator: PentairPoolDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Bind to one device."""
        super().__init__(coordinator, DESCRIPTION, device_id)
        self._attr_name = "Filter pump"
        # `None` = follow truth (ra4). `True`/`False` = optimistic override
        # in effect because the user just toggled and reality hasn't caught
        # up yet. Cleared automatically when ra4 confirms the new state.
        self._pending: bool | None = None

    # ----------------------------------------------------------- state read

    def _running_from_truth(self) -> bool | None:
        v = self.field_value(FIELD_RA4)
        if v is None:
            return None
        try:
            return int(v) > 0
        except ValueError:
            return None

    @property
    def is_on(self) -> bool | None:
        """Real running state, with the user's pending override on top."""
        running = self._running_from_truth()
        if self._pending is not None and running != self._pending:
            return self._pending
        return running

    @property
    def extra_state_attributes(self) -> dict[str, str | bool | None]:
        """Expose ra0/ra4 plus any optimistic-override that's currently held."""
        return {
            "ra0": self.field_value(FIELD_RA0),
            "ra4_watts": self.field_value(FIELD_RA4),
            "pending_override": self._pending,
        }

    # ------------------------------------------------- pending reconciliation

    @callback
    def _handle_coordinator_update(self) -> None:
        """Clear the pending override once `ra4` matches what the user asked for."""
        if self._pending is not None:
            running = self._running_from_truth()
            if running is not None and running == self._pending:
                self._pending = None
        super()._handle_coordinator_update()

    # --------------------------------------------------------------- writes

    async def async_turn_on(self, **_: Any) -> None:
        """Manual override: pump on. Preserves the schedule bit."""
        sched = (self.field_value(FIELD_RA0) or "") in SCHEDULE_ON
        target = RA0_ON_SCHEDULED if sched else RA0_ON_NO_SCHEDULE
        await self.coordinator.async_set_fields(self._device_id, {FIELD_RA0: target})
        self._pending = True
        self.async_write_ha_state()

    async def async_turn_off(self, **_: Any) -> None:
        """Manual override: pump off. Preserves the schedule bit.

        If the heater is in cooldown the pump will keep physically running
        for a few minutes; the optimistic OFF state is held until `ra4`
        drops to 0, so the switch stays OFF for that whole window.
        """
        sched = (self.field_value(FIELD_RA0) or "") in SCHEDULE_ON
        target = RA0_OFF_SCHEDULED if sched else RA0_OFF_NO_SCHEDULE
        await self.coordinator.async_set_fields(self._device_id, {FIELD_RA0: target})
        self._pending = False
        self.async_write_ha_state()
