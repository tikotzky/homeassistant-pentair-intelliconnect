"""Pool-heater climate entity."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from custom_components.pentair_pool.const import (
    FIELD_HTD1,
    FIELD_HTD2,
    FIELD_HTD13,
    FIELD_HTD14,
    FIELD_T0,
    HTD1_AUTO_IDLE,
    HTD1_HEATING,
    HTD1_LABELS,
    HTD1_OFF,
)
from custom_components.pentair_pool.entity import PentairPoolEntity
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

if TYPE_CHECKING:
    from custom_components.pentair_pool.coordinator import PentairPoolDataUpdateCoordinator

DESCRIPTION = ClimateEntityDescription(
    key="heater",
    translation_key="heater",
    has_entity_name=True,
)


class PentairPoolHeater(ClimateEntity, PentairPoolEntity):
    """Pool heater wrapped as an HVAC entity."""

    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_min_temp = 35
    _attr_max_temp = 110
    _attr_target_temperature_step = 1

    def __init__(
        self,
        coordinator: PentairPoolDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Bind to one device."""
        super().__init__(coordinator, DESCRIPTION, device_id)
        self._attr_name = "Heater"

    @property
    def hvac_mode(self) -> HVACMode:
        """Off when htd1 == 0, otherwise heat."""
        v = self.field_value(FIELD_HTD1)
        if v in (None, HTD1_OFF):
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        """Active when firmware reports htd1 == 3 (firing); idle otherwise.

        htd1 == 1 is "Auto idle" -- heater is enabled and monitoring but the
        burner is not lit. The firmware promotes 1 -> 3 once it decides to
        fire (water below setpoint AND pump flow available).
        """
        v = self.field_value(FIELD_HTD1)
        if v == HTD1_OFF:
            return HVACAction.OFF
        if v == HTD1_HEATING:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def target_temperature(self) -> float | None:
        """`htd2` is in tenths of degF."""
        v = self.field_value(FIELD_HTD2)
        if v is None:
            return None
        try:
            return int(v) / 10.0
        except ValueError:
            return None

    @property
    def current_temperature(self) -> float | None:
        """Pool water temp from `t0` (Current_Water_Temp, whole degF)."""
        v = self.field_value(FIELD_T0)
        if v is None:
            return None
        try:
            return float(int(v))
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        """Surface heater-specific state that HVACAction can't represent.

        HA's `hvac_action` is a closed enum (off/heating/cooling/idle), so
        the finer-grained Pentair mode (Auto Idle, Schedule Running, etc.)
        lives here as a free-form `heater_mode` attribute. `htd14` is the
        live cooldown countdown in seconds; the dedicated cooldown sensor
        ticks 1 Hz between server pushes for a smooth display.
        """
        htd1 = self.field_value(FIELD_HTD1)
        return {
            "heater_mode": HTD1_LABELS.get(htd1, f"Mode {htd1}") if htd1 is not None else None,
            "htd1_raw": htd1,
            "cooldown_seconds": self.field_value(FIELD_HTD14),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Send the new setpoint as tenths of degF."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self.coordinator.async_set_fields(
            self._device_id,
            {FIELD_HTD2: int(round(float(temp) * 10))},
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """OFF mirrors the app behavior of writing both htd1 and htd13 to 0."""
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_set_fields(
                self._device_id,
                {FIELD_HTD1: HTD1_OFF, FIELD_HTD13: "0"},
            )
        elif hvac_mode == HVACMode.HEAT:
            # Writing htd1=1 puts the heater in Auto Idle; firmware decides
            # when to promote that to Heating (htd1=3) based on flow + temp.
            await self.coordinator.async_set_fields(
                self._device_id,
                {FIELD_HTD1: HTD1_AUTO_IDLE},
            )
