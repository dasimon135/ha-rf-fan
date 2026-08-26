"""Typed runtime data shared by the entities of a config entry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event


@dataclass
class RfFanRuntimeData:
    """Assumed state shared across the platforms of one config entry."""

    # Dead-reckoned position in COLOR_TEMP_OPTIONS.
    kelvin_position: int = 0
    # Dead-reckoned brightness position in 0..LIGHT_LEVEL_STEPS-1, for a light whose
    # remote has +/- keys instead of a level to set. None until it is established.
    level_position: int | None = None
    # Walks in flight, keyed by axis ("color", "level"). A walk emits one key press
    # per step with a pause between them, so a nine-step move takes several seconds;
    # moving the control again during it would interleave two walks and leave the
    # assumed position wrong. The rule is *restart*: the running walk is cancelled
    # and the new one starts from where the old one actually stopped. One entry per
    # axis, so a brightness move and a colour move never cancel each other.
    walks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    # Assumed light state (None until known); gates the colour select.
    light_on: bool | None = None
    # Assumed switch-off time recorded by the sleep-timer buttons.
    timer_ends_at: datetime | None = None
    # Codes transmitted recently -> hass.loop.time() until which their echo is
    # discarded. Keyed by code (not a single timestamp) so a remote press of a
    # DIFFERENT button right after a Home Assistant command is still honoured.
    echo_codes: dict[str, float] = field(default_factory=dict)
    # Codes received from a remote -> hass.loop.time() of the last frame carrying
    # them. A press puts the same frame on the air several times; this is what tells
    # the repeats apart from a second press (issue #24).
    receive_seen: dict[str, float] = field(default_factory=dict)
    # (frame, verdict) for the last frame judged by `_is_repeat`. Every platform of
    # the entry listens to the same bus event, so the verdict is computed once and
    # reused: recomputing it per listener would let the first entity slide the window
    # forward and leave all the others concluding the frame was a repeat. The event
    # object itself is held rather than its id, so nothing can be identified with a
    # frame that has since been collected.
    receive_verdict: tuple[Event, bool] | None = None
    # Last sniffed code that matched none of the learned ones. Following the
    # physical remote is exact string matching, so a gateway that reports codes
    # in a different shape than the one they were learned in silently stops
    # updating anything; without this, that is indistinguishable from the
    # feature not existing.
    last_unmatched_code: str | None = None


type RfFanConfigEntry = ConfigEntry[RfFanRuntimeData]
