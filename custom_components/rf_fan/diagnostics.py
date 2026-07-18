"""Diagnostics support for RF Fan."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_CODES, CONF_ESPHOME_DEVICE, CONF_GATEWAY_SERVICE

TO_REDACT = {CONF_ESPHOME_DEVICE, CONF_GATEWAY_SERVICE}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    The captured RF codes are included (they are not sensitive and are the most
    useful thing when debugging a device); the ESPHome gateway name is redacted.
    """
    data = dict(entry.data)
    codes = data.get(CONF_CODES, {})
    return {
        "config": async_redact_data(data, TO_REDACT),
        "options": dict(entry.options),
        "summary": {
            "action_count": len(codes),
            "actions_with_code": sorted(a for a, c in codes.items() if c),
        },
    }
