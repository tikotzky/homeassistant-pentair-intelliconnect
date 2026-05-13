"""
DataUpdateCoordinator for pentair_pool.

State layout exposed to entities (`coordinator.data`):

    {
        device_id: {
            "device_info": {<top-level keys from listdevices -- pname, arn, ...>},
            "fields":      {field_code: {"value": "...", "name": "...", "min": "...", "max": "...", ...}},
            "online":      bool,
            "alarm":       bool,
            "fwVersion":   str | None,
        },
        ...
    }

WebSocket pushes (`event_type=device_data`) merge into the `fields` map
field-by-field. The hourly REST poll is a backstop for missed pushes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from custom_components.pentair_pool.api import (
    PentairPoolApiClient,
    PentairPoolApiClientAuthenticationError,
    PentairPoolApiClientError,
    PentairPoolWebSocket,
)
from custom_components.pentair_pool.const import LOGGER
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

if TYPE_CHECKING:
    from custom_components.pentair_pool.data import PentairPoolConfigEntry


class PentairPoolDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Manages REST polling + WS push integration for one Pentair account."""

    config_entry: PentairPoolConfigEntry

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and prepare the WebSocket holders.

        We run TWO subscriptions in parallel -- one per `active_screen`
        value the Pentair cloud honors -- because each screen pushes a
        different field set:

          - `poolScreen`: dashboard fields incl. the heater setpoint (htd2)
          - `product`:    device-detail fields incl. pump state (ra0/ra4),
                          heater mode (htd1), cooldown raw (htd14), and the
                          chlorine setpoint (icd1). The official app also
                          PUTs `appuse=1` periodically from this screen, so
                          this subscription mirrors that.

        The union of the two covers every field this integration reads, so
        the 60 s REST poll is only a defensive fallback for missed pushes.
        """
        super().__init__(*args, **kwargs)
        self._ws_pool: PentairPoolWebSocket | None = None
        self._ws_product: PentairPoolWebSocket | None = None

    @property
    def client(self) -> PentairPoolApiClient:
        """The API client tied to this entry."""
        return self.config_entry.runtime_data.client

    async def _async_setup(self) -> None:
        """One-time login before the first refresh."""
        LOGGER.debug("Pentair coordinator: running first-time login")
        try:
            await self.client.async_login()
        except PentairPoolApiClientAuthenticationError as err:
            LOGGER.warning("Pentair login failed: %s", err)
            raise ConfigEntryAuthFailed(
                translation_domain="pentair_pool",
                translation_key="authentication_failed",
            ) from err

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Full-state refresh via REST. Also (re)starts the WS subscription."""
        try:
            listing = await self.client.async_list_devices()
        except PentairPoolApiClientAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                translation_domain="pentair_pool",
                translation_key="authentication_failed",
            ) from err
        except PentairPoolApiClientError as err:
            raise UpdateFailed(
                translation_domain="pentair_pool",
                translation_key="update_failed",
            ) from err

        devices: list[dict[str, Any]] = listing.get("response", [])
        state: dict[str, dict[str, Any]] = {}

        for dev in devices:
            device_id = dev.get("deviceId") or _arn_to_device_id(dev.get("arn"))
            if not device_id:
                continue
            try:
                detail = await self.client.async_get_device(device_id)
            except PentairPoolApiClientError as err:
                LOGGER.warning("get_device(%s) failed: %s", device_id, err)
                continue
            # Response shape: {"response": {"data": [{"fields": {...}, "online": ..., ...}]}}
            response = detail.get("response") or {}
            data_items = response.get("data") if isinstance(response, dict) else None
            if not data_items:
                # Some endpoints return {"response": [{...}]} instead; tolerate both.
                data_items = response if isinstance(response, list) else [response]
            detail_data = (data_items or [{}])[0] or {}
            state[device_id] = {
                "device_info": dev,
                "fields": detail_data.get("fields", {}) or {},
                "online": detail_data.get("online", True),
                "alarm": detail_data.get("alarm", False),
                "fwVersion": detail_data.get("fwVersion"),
            }

        await self._ensure_ws_started(list(state))
        return state

    # --------------------------------------------------------------- WebSocket

    async def _ensure_ws_started(self, device_ids: list[str]) -> None:
        """Start (or restart) both WS subscriptions to cover the union of fields."""
        if not device_ids:
            return
        session = async_get_clientsession(self.hass)

        def _make(active_screen: str, send_appuse: bool) -> PentairPoolWebSocket:
            ws = PentairPoolWebSocket(
                session,
                self.client,
                device_ids,
                self._handle_ws_update,
                active_screen=active_screen,
                send_appuse=send_appuse,
            )
            ws.start()
            return ws

        if self._ws_pool is None:
            self._ws_pool = _make("poolScreen", send_appuse=False)
        elif set(self._ws_pool._device_ids) != set(device_ids):  # noqa: SLF001
            await self._ws_pool.stop()
            self._ws_pool = _make("poolScreen", send_appuse=False)

        if self._ws_product is None:
            self._ws_product = _make("product", send_appuse=True)
        elif set(self._ws_product._device_ids) != set(device_ids):  # noqa: SLF001
            await self._ws_product.stop()
            self._ws_product = _make("product", send_appuse=True)

    async def async_shutdown(self) -> None:
        """Stop both WS tasks on unload."""
        for attr in ("_ws_pool", "_ws_product"):
            ws = getattr(self, attr)
            if ws is not None:
                await ws.stop()
                setattr(self, attr, None)
        await super().async_shutdown()

    async def _handle_ws_update(self, device_id: str, fields: dict[str, dict]) -> None:
        """Merge a delta from a device_data WS frame into our state."""
        if self.data is None:
            return
        snapshot = dict(self.data)
        per_device = dict(snapshot.get(device_id) or {})
        existing_fields = dict(per_device.get("fields") or {})
        for k, v in fields.items():
            existing_fields[k] = v
        per_device["fields"] = existing_fields
        snapshot[device_id] = per_device
        self.async_set_updated_data(snapshot)

    # ----------------------------------------------------------- command API

    async def async_set_fields(self, device_id: str, payload: dict[str, Any]) -> None:
        """Send a PUT and optimistically update local state.

        The authoritative state will arrive on the WS shortly; this just makes
        the HA UI snappy after a button tap.
        """
        try:
            await self.client.async_set_fields(device_id, payload)
        except PentairPoolApiClientAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                translation_domain="pentair_pool",
                translation_key="authentication_failed",
            ) from err

        if self.data is None:
            return
        snapshot = dict(self.data)
        per_device = dict(snapshot.get(device_id) or {})
        existing_fields = dict(per_device.get("fields") or {})
        for k, v in payload.items():
            existing = dict(existing_fields.get(k) or {})
            existing["value"] = str(v)
            existing_fields[k] = existing
        per_device["fields"] = existing_fields
        snapshot[device_id] = per_device
        self.async_set_updated_data(snapshot)


def _arn_to_device_id(arn: str | None) -> str | None:
    """`arn:aws:iot:us-west-2:xxx:thing/PNRA1PIFXXXXXXXXXX` -> `PNRA1PIFXXXXXXXXXX`."""
    if not arn:
        return None
    if "/" in arn:
        return arn.rsplit("/", 1)[-1]
    return None
