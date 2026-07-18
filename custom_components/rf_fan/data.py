"""Typed runtime data shared by the entities of a config entry."""

from __future__ import annotations

from dataclasses import dataclass
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
    # hass.loop.time() of the last RF transmission (anti-echo window).
    last_tx: float = 0.0


type RfFanConfigEntry = ConfigEntry[RfFanRuntimeData]
