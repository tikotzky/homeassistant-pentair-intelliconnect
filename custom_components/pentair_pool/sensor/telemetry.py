"""Read-only telemetry sensors for the IntelliConnect."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from custom_components.pentair_pool.const import (
    FIELD_HTD1,
    FIELD_HTD14,
    FIELD_ICS1,
    FIELD_ICS2,
    FIELD_ICS9,
    FIELD_ICS11,
    FIELD_ICS12,
    FIELD_ICS13,
    FIELD_ICS15,
    FIELD_RA4,
    FIELD_T0,
    FIELD_T1,
    HTD1_LABELS,
)
from custom_components.pentair_pool.entity import PentairPoolEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTemperature, UnitOfTime

if TYPE_CHECKING:
    from custom_components.pentair_pool.coordinator import PentairPoolDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class PentairSensorDescription(SensorEntityDescription):
    """SensorEntityDescription with a per-field decoder."""

    value_fn: Callable[[str], object] = lambda v: v


def _as_int(v: str) -> int | None:
    try:
        return int(v)
    except TypeError, ValueError:
        return None


def _heater_mode_label(v: str) -> str:
    """Map htd1 numeric value to a friendly label."""
    return HTD1_LABELS.get(v, f"Mode {v}")


SENSORS: tuple[tuple[str, PentairSensorDescription], ...] = (
    (
        FIELD_HTD1,
        PentairSensorDescription(
            key="heater_mode",
            translation_key="heater_mode",
            icon="mdi:radiator",
            has_entity_name=True,
            value_fn=_heater_mode_label,
        ),
    ),
    (
        FIELD_T0,
        PentairSensorDescription(
            key="water_temperature",
            translation_key="water_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
            has_entity_name=True,
            value_fn=_as_int,
        ),
    ),
    (
        FIELD_T1,
        PentairSensorDescription(
            key="air_temperature",
            translation_key="air_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
            has_entity_name=True,
            value_fn=_as_int,
        ),
    ),
    (
        FIELD_RA4,
        PentairSensorDescription(
            key="filter_pump_power",
            translation_key="filter_pump_power",
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfPower.WATT,
            has_entity_name=True,
            value_fn=_as_int,
        ),
    ),
    # NOTE: htd14 is exposed by a dedicated countdown entity in sensor/cooldown.py
    # (it ticks locally every second between server updates). Don't duplicate here.
    (
        FIELD_ICS1,
        PentairSensorDescription(
            key="chlorine_actual",
            translation_key="chlorine_actual",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            has_entity_name=True,
            value_fn=_as_int,
        ),
    ),
    (
        FIELD_ICS2,
        PentairSensorDescription(
            key="salt_ppm",
            translation_key="salt_ppm",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement="ppm",
            has_entity_name=True,
            value_fn=_as_int,
        ),
    ),
    (
        FIELD_ICS9,
        PentairSensorDescription(
            key="salt_cell_temp",
            translation_key="salt_cell_temp",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
            has_entity_name=True,
            value_fn=_as_int,
        ),
    ),
    (
        FIELD_ICS13,
        PentairSensorDescription(
            key="boost_remaining",
            translation_key="boost_remaining",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            has_entity_name=True,
            value_fn=_as_int,
        ),
    ),
    (
        FIELD_ICS15,
        PentairSensorDescription(
            key="salt_cell_hours",
            translation_key="salt_cell_hours",
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfTime.HOURS,
            has_entity_name=True,
            value_fn=_as_int,
        ),
    ),
    (
        FIELD_ICS11,
        PentairSensorDescription(
            key="salt_cell_firmware",
            translation_key="salt_cell_firmware",
            has_entity_name=True,
            value_fn=lambda v: v,
        ),
    ),
    (
        FIELD_ICS12,
        PentairSensorDescription(
            key="salt_cell_model",
            translation_key="salt_cell_model",
            has_entity_name=True,
            value_fn=lambda v: v,
        ),
    ),
)


class PentairPoolFieldSensor(SensorEntity, PentairPoolEntity):
    """Generic field-backed sensor."""

    entity_description: PentairSensorDescription

    def __init__(
        self,
        coordinator: PentairPoolDataUpdateCoordinator,
        device_id: str,
        field_code: str,
        description: PentairSensorDescription,
    ) -> None:
        """Bind to one (device, field)."""
        super().__init__(coordinator, description, device_id)
        self._field_code = field_code

    @property
    def native_value(self) -> object:
        """Decode raw field value with the description's value_fn."""
        v = self.field_value(self._field_code)
        if v is None:
            return None
        return self.entity_description.value_fn(v)
