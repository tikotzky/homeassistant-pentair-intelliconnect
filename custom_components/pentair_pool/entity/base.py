"""
Base entity class for pentair_pool.

Pentair Cloud groups everything under one account, but each physical
controller (e.g. an IntelliConnect with `deviceType=PIF0`) becomes its
own HA device. The entity base therefore takes a `device_id` and
projects a per-device `DeviceInfo`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from custom_components.pentair_pool.const import ATTRIBUTION, DOMAIN
from custom_components.pentair_pool.coordinator import PentairPoolDataUpdateCoordinator
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

if TYPE_CHECKING:
    from homeassistant.helpers.entity import EntityDescription


class PentairPoolEntity(CoordinatorEntity[PentairPoolDataUpdateCoordinator]):
    """Common base wiring (device info, unique_id, coordinator hookup)."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PentairPoolDataUpdateCoordinator,
        entity_description: EntityDescription,
        device_id: str,
    ) -> None:
        """Bind one entity to one Pentair device."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_{entity_description.key}"

    # ----------------------------------------------------------------- helpers

    @property
    def device_state(self) -> dict[str, Any]:
        """The per-device dict from `coordinator.data` (empty if not yet loaded)."""
        return (self.coordinator.data or {}).get(self._device_id) or {}

    @property
    def fields(self) -> dict[str, dict[str, Any]]:
        """The device's `fields` map."""
        return self.device_state.get("fields") or {}

    def field_value(self, code: str) -> str | None:
        """Return the string value for a field, or None if not present."""
        f = self.fields.get(code)
        return f.get("value") if f else None

    @property
    def device_info(self) -> DeviceInfo:
        """Build per-device DeviceInfo from the listdevices payload."""
        dev = self.device_state.get("device_info") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=dev.get("pname") or self._device_id,
            manufacturer="Pentair",
            model=dev.get("deviceType"),
            sw_version=self.device_state.get("fwVersion"),
        )

    @property
    def available(self) -> bool:
        """Available if the coordinator + last device snapshot say online."""
        return super().available and bool(self.device_state.get("online", True))
