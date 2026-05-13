"""Diagnostics for pentair_pool.

Returns a redacted snapshot of coordinator state -- useful for bug reports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import PentairPoolConfigEntry

REDACT_KEYS = {CONF_PASSWORD, CONF_USERNAME, "token", "x-amz-id-token", "x-amz-security-token"}


async def async_get_config_entry_diagnostics(
    _hass: HomeAssistant,
    entry: PentairPoolConfigEntry,
) -> dict[str, Any]:
    """Snapshot of the integration's state with credentials redacted."""
    coordinator = entry.runtime_data.coordinator
    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), REDACT_KEYS),
        },
        "devices": coordinator.data,
    }
