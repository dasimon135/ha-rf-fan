"""Typed runtime data shared by the entities of a config entry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from homeassistant.config_entries import ConfigEntry


@dataclass
class RfFanRuntimeData:
    """Assumed state shared across the platforms of one config entry."""

    # Dead-reckoned position in COLOR_TEMP_OPTIONS.
    kelvin_position: int = 0
    # Assumed light state (None until known); gates the colour select.
    light_on: bool | None = None
    # Assumed switch-off time recorded by the sleep-timer buttons.
    timer_ends_at: datetime | None = None
    # Codes transmitted recently -> hass.loop.time() until which their echo is
    # discarded. Keyed by code (not a single timestamp) so a remote press of a
    # DIFFERENT button right after a Home Assistant command is still honoured.
    echo_codes: dict[str, float] = field(default_factory=dict)


type RfFanConfigEntry = ConfigEntry[RfFanRuntimeData]
