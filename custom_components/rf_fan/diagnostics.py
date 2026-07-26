"""Diagnostics support for RF Fan."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import COLOR_TEMP_OPTIONS, CONF_CODES, CONF_ESPHOME_DEVICE, CONF_GATEWAY_SERVICE
from .data import RfFanConfigEntry

TO_REDACT = {CONF_ESPHOME_DEVICE, CONF_GATEWAY_SERVICE}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RfFanConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    The captured RF codes are included (they are not sensitive and are the most
    useful thing when debugging a device); the ESPHome gateway name is redacted.

    The `runtime` section carries the assumed state. The fan never reports
    anything back, so this dead-reckoned state is the only way to tell a
    desynchronised colour position or a stuck anti-echo window from a genuine
    hardware problem — and none of it survives a restart in a readable form.
    """
    data = dict(entry.data)
    codes = data.get(CONF_CODES, {})
    runtime = entry.runtime_data
    now = hass.loop.time()

    position = runtime.kelvin_position
    return {
        "config": async_redact_data(data, TO_REDACT),
        "options": dict(entry.options),
        "summary": {
            "action_count": len(codes),
            "actions_with_code": sorted(a for a, c in codes.items() if c),
        },
        "runtime": {
            "kelvin_position": position,
            "colour": COLOR_TEMP_OPTIONS[position]
            if 0 <= position < len(COLOR_TEMP_OPTIONS)
            else None,
            "light_on": runtime.light_on,
            "timer_ends_at": runtime.timer_ends_at.isoformat()
            if runtime.timer_ends_at
            else None,
            # Codes are not listed: only how many echo windows are still open, which
            # is what tells a suppressed remote press from an ignored one.
            "armed_echo_codes": sum(
                1 for until in runtime.echo_codes.values() if until > now
            ),
        },
    }
