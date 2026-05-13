"""Daily Schedule start/end time entities.

The Pentair firmware stores schedule times as seconds-since-midnight UTC.
Home Assistant works in local time, so each entity converts on the wire:

  Read:  ra* (UTC seconds-of-day)  ->  local datetime.time()
  Write: local datetime.time()      ->  UTC seconds-of-day

We use HA's own timezone (`hass.config.time_zone`) for the conversion, which
matches the Pentair-side timezone in practice because the controller is
provisioned at the user's home location and the user runs HA there too. If
they differ, the schedule will still fire at the correct UTC instant, but the
displayed local time may differ from what the Pentair app shows.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from custom_components.pentair_pool.const import FIELD_RA1, FIELD_RA2
from custom_components.pentair_pool.entity import PentairPoolEntity
from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from custom_components.pentair_pool.coordinator import PentairPoolDataUpdateCoordinator


def _utc_seconds_to_local_time(seconds: int, tz: dt.tzinfo) -> dt.time:
    """0..86399 (seconds-of-day UTC) -> local datetime.time().

    Uses today's date as the carrier so DST is applied correctly. Schedules
    run every day, so picking "today" is fine.
    """
    today_utc_midnight = dt.datetime.combine(
        dt_util.utcnow().date(),
        dt.time(),
        tzinfo=dt.UTC,
    )
    utc_instant = today_utc_midnight + dt.timedelta(seconds=seconds)
    return utc_instant.astimezone(tz).time()


def _local_time_to_utc_seconds(local: dt.time, tz: dt.tzinfo) -> int:
    """Inverse of `_utc_seconds_to_local_time`."""
    today_local = dt.datetime.now(tz).date()
    local_instant = dt.datetime.combine(today_local, local, tzinfo=tz)
    utc_instant = local_instant.astimezone(dt.UTC)
    utc_midnight = dt.datetime.combine(utc_instant.date(), dt.time(), tzinfo=dt.UTC)
    return int((utc_instant - utc_midnight).total_seconds()) % 86400


class _ScheduleTimeBase(TimeEntity, PentairPoolEntity):
    """Shared base for start/end."""

    field_code: str = ""

    def __init__(
        self,
        coordinator: PentairPoolDataUpdateCoordinator,
        device_id: str,
        description: TimeEntityDescription,
    ) -> None:
        super().__init__(coordinator, description, device_id)

    @property
    def native_value(self) -> dt.time | None:
        v = self.field_value(self.field_code)
        if v is None:
            return None
        try:
            seconds = int(v) % 86400
        except ValueError:
            return None
        tz = dt_util.get_time_zone(self.hass.config.time_zone) or dt.UTC
        return _utc_seconds_to_local_time(seconds, tz)

    async def async_set_value(self, value: dt.time) -> None:
        tz = dt_util.get_time_zone(self.hass.config.time_zone) or dt.UTC
        utc_seconds = _local_time_to_utc_seconds(value, tz)
        await self.coordinator.async_set_fields(self._device_id, {self.field_code: utc_seconds})


class PentairPoolScheduleStart(_ScheduleTimeBase):
    """Daily Schedule start time (`ra1`)."""

    field_code = FIELD_RA1

    def __init__(self, coordinator: PentairPoolDataUpdateCoordinator, device_id: str) -> None:
        """Bind to one device's `ra1` field."""
        super().__init__(
            coordinator,
            device_id,
            TimeEntityDescription(
                key="schedule_start",
                translation_key="schedule_start",
                icon="mdi:clock-start",
                entity_category=EntityCategory.CONFIG,
                has_entity_name=True,
            ),
        )
        self._attr_name = "Daily schedule start"


class PentairPoolScheduleEnd(_ScheduleTimeBase):
    """Daily Schedule end time (`ra2`)."""

    field_code = FIELD_RA2

    def __init__(self, coordinator: PentairPoolDataUpdateCoordinator, device_id: str) -> None:
        """Bind to one device's `ra2` field."""
        super().__init__(
            coordinator,
            device_id,
            TimeEntityDescription(
                key="schedule_end",
                translation_key="schedule_end",
                icon="mdi:clock-end",
                entity_category=EntityCategory.CONFIG,
                has_entity_name=True,
            ),
        )
        self._attr_name = "Daily schedule stop"
