"""Service actions package for pentair_pool."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.pentair_pool.const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall


SERVICE_RELOAD_DATA = "reload_data"


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration-level services.

    `pentair_pool.reload_data` forces a coordinator refresh for every
    configured account, which is useful after manually changing settings
    on a controller.
    """

    async def handle_reload_data(_call: ServiceCall) -> None:
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator = entry.runtime_data.coordinator if hasattr(entry, "runtime_data") else None
            if coordinator is not None:
                await coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_RELOAD_DATA):
        hass.services.async_register(DOMAIN, SERVICE_RELOAD_DATA, handle_reload_data)
    LOGGER.debug("pentair_pool services registered")
