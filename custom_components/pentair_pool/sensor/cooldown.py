"""Heater cooldown countdown sensor.

Shows the user-visible "time until the pump physically stops" during a heater
cooldown sequence. The Pentair app displays this exact value in its pump
card as "Timer Running -- NN min left", and it is sourced from the relay's
own timer-status field `ras0 = Relay1_Timer_Status` (live seconds remaining
until the firmware opens the pump relay).

We deliberately do NOT use `htd14 = Heater_Cooldown` here -- that field is
the heater's internal "full cool" timer and continues counting past the
moment the pump physically stops (empirically by ~60-90 seconds, while the
heat exchanger settles internally). Sourcing the display from `ras0`
matches the Pentair app exactly and reaches 0 at the moment of pump-stop.

The cloud only pushes `ras0` periodically (10-30 s typical), so we re-anchor
on each push and tick locally at 1 Hz between pushes for a smooth display.
As a defense-in-depth check we also snap the display to 0 the moment `ra4`
(pump wattage) reads 0, in case a push is missed near the end.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import TYPE_CHECKING

from custom_components.pentair_pool.const import FIELD_RA4, FIELD_RAS0
from custom_components.pentair_pool.entity import PentairPoolEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval

if TYPE_CHECKING:
    from custom_components.pentair_pool.coordinator import PentairPoolDataUpdateCoordinator

DESCRIPTION = SensorEntityDescription(
    key="heater_cooldown",
    translation_key="heater_cooldown",
    icon="mdi:timer-sand",
    device_class=SensorDeviceClass.DURATION,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfTime.SECONDS,
    has_entity_name=True,
)


class PentairPoolCooldownCountdown(SensorEntity, PentairPoolEntity):
    """Local 1 Hz tick + re-baseline on server push, driven by ras0."""

    def __init__(
        self,
        coordinator: PentairPoolDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Bind to one device."""
        super().__init__(coordinator, DESCRIPTION, device_id)
        self._attr_name = "Heater cooldown"
        self._baseline: int | None = None
        self._baseline_at: float = 0.0
        self._unsub_tick = None
        self._refresh_requested_at: float | None = None

    # ------------------------------------------------------------------ life

    async def async_added_to_hass(self) -> None:
        """Seed from current coordinator state, then start the 1 Hz tick."""
        await super().async_added_to_hass()
        self._sync_baseline()
        self._unsub_tick = async_track_time_interval(
            self.hass,
            self._on_tick,
            dt.timedelta(seconds=1),
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel the tick."""
        if self._unsub_tick is not None:
            self._unsub_tick()
            self._unsub_tick = None
        await super().async_will_remove_from_hass()

    # --------------------------------------------------------------- updates

    @callback
    def _handle_coordinator_update(self) -> None:
        """Re-baseline whenever the coordinator pushes a (different) value."""
        self._sync_baseline()
        super()._handle_coordinator_update()

    @callback
    def _on_tick(self, _now: dt.datetime) -> None:
        """Re-render every second.

        On transition to 0, kick a coordinator refresh so the rest of the
        entities pick up the post-cooldown state (pump ra4=0, htd1
        transition) without waiting for the 60 s poll.
        """
        if self._baseline is None:
            return
        remaining = self._remaining()
        if remaining > 0:
            self.async_write_ha_state()
            return
        # remaining == 0: nudge a REST poll once per cooldown so HA picks up
        # fresh ra4 / htd1 promptly. Throttle to avoid hammering the cloud
        # if the sensor re-fires.
        now = time.monotonic()
        if self._refresh_requested_at is None or now - self._refresh_requested_at > 30:
            self._refresh_requested_at = now
            self.hass.async_create_task(self.coordinator.async_request_refresh())
            self.async_write_ha_state()

    # ---------------------------------------------------------------- state

    def _sync_baseline(self) -> None:
        v = self.field_value(FIELD_RAS0)
        try:
            new_val = int(v) if v is not None else None
        except ValueError:
            new_val = None
        if new_val is None:
            self._baseline = None
            return
        if new_val != self._baseline:
            self._baseline = new_val
            self._baseline_at = time.monotonic()

    def _pump_stopped(self) -> bool:
        """True if the pump physically reports 0 W -- ends cooldown display."""
        v = self.field_value(FIELD_RA4)
        if v is None:
            return False
        try:
            return int(v) == 0
        except TypeError, ValueError:
            return False

    def _remaining(self) -> int:
        if self._pump_stopped():
            return 0
        if self._baseline is None:
            return 0
        elapsed = time.monotonic() - self._baseline_at
        return max(0, int(self._baseline - elapsed))

    @property
    def native_value(self) -> int | None:
        """Seconds remaining, or 0 once the pump is verifiably off."""
        # Always report 0 once the pump is verifiably off, even if we never
        # received a ras0 baseline this session.
        if self._pump_stopped():
            return 0
        if self._baseline is None:
            return None
        return self._remaining()

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        """Diagnostic attributes (formatted MM:SS, push lag, pump-stop flag)."""
        if self._baseline is None:
            return {"pump_stopped": self._pump_stopped()}
        rem = self._remaining()
        return {
            # MM:SS for dashboard cards that prefer it over HA's auto-formatted
            # DURATION display.
            "formatted": f"{rem // 60}:{rem % 60:02d}",
            "ras0_last_push": self._baseline,
            "baseline_received_seconds_ago": int(time.monotonic() - self._baseline_at),
            "pump_stopped": self._pump_stopped(),
        }
