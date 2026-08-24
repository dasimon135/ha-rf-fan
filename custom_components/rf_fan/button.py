"""Button platform for RF Fan (sleep timers)."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .actions import caps_from_data
from .const import (
    ACTION_LIGHT_BRIGHT_DOWN,
    COLOR_CONTROL_NONE,
    CONF_HAS_TIMERS,
    LIGHT_LEVEL_RELATIVE,
    LIGHT_LEVEL_STEPS,
    STEP_GAP_SEC,
    TIMER_HOURS,
    timer_action,
)
from .entity import RfFanBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the buttons (timers, colour calibration, brightness resynchronisation)."""
    caps = caps_from_data(dict(config_entry.data))
    entities: list[ButtonEntity] = []

    if config_entry.data.get(CONF_HAS_TIMERS, False):
        entities.extend(
            RfFanTimerButton(hass, config_entry, hours) for hours in TIMER_HOURS
        )

    if caps["color_control"] != COLOR_CONTROL_NONE:
        entities.append(RfFanKelvinCalibrateButton(hass, config_entry))

    if caps["light_level"] == LIGHT_LEVEL_RELATIVE:
        entities.append(RfFanBrightnessResyncButton(hass, config_entry))

    if entities:
        async_add_entities(entities)


class RfFanTimerButton(RfFanBaseEntity, ButtonEntity):
    """Button that triggers an N-hour sleep timer."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, hours: int) -> None:
        """Initialize the timer button."""
        super().__init__(hass, config_entry)
        self._hours = hours
        self._attr_unique_id = f"{config_entry.entry_id}_timer_{hours}h"
        self._attr_translation_key = "timer"
        self._attr_translation_placeholders = {"hours": str(hours)}

    async def async_press(self) -> None:
        """Emit the timer action and record the assumed switch-off time."""
        if not await self._async_transmit_action(timer_action(self._hours)):
            # Nothing went on the air (unmapped code): claiming a switch-off time
            # would make the sensor announce an extinction that will never happen.
            return
        self._runtime.timer_ends_at = dt_util.utcnow() + timedelta(hours=self._hours)
        async_dispatcher_send(self.hass, self._timer_signal())


class RfFanKelvinCalibrateButton(RfFanBaseEntity, ButtonEntity):
    """Calibration button: resets the assumed color position to "Warm"."""

    # Pure UI resync (no RF emitted): a configuration control, not a device control.
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the color calibration button."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_kelvin_calibrate"
        self._attr_translation_key = "recalibrate_color"

    async def async_press(self) -> None:
        """Reset the color position to zero without emitting an RF code."""
        self._runtime.kelvin_position = 0
        async_dispatcher_send(self.hass, self._kelvin_signal())


class RfFanBrightnessResyncButton(RfFanBaseEntity, ButtonEntity):
    """Walks the lamp down to its dimmest step so the assumed position becomes true.

    Unlike the colour calibration button next to it, this one DOES emit. A colour
    cycle has no end stop, so its position can only ever be declared; a brightness
    range has one, and walking into it is the only way to establish the position
    from physical fact rather than from a claim.

    N-1 presses reach the bottom from anywhere, and the extra presses do nothing
    once there. Be aware that on many remotes stepping below the lowest level turns
    the lamp off — the resynchronisation is audible and visible. That is the price
    of physical truth over a declaration; the position select alongside is the
    silent alternative when you already know where the lamp is.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the brightness resynchronisation button."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_brightness_calibrate"
        self._attr_translation_key = "resync_brightness"

    async def async_press(self) -> None:
        """Step down to the bottom of the range and record the position."""
        if not await self._async_transmit_times(
            ACTION_LIGHT_BRIGHT_DOWN, LIGHT_LEVEL_STEPS - 1, gap=STEP_GAP_SEC
        ):
            # Nothing went on the air (unmapped code): the lamp has not moved, so
            # claiming it sits at the bottom would replace one wrong position with
            # another.
            return
        self._runtime.level_position = 0
        async_dispatcher_send(self.hass, self._level_signal())
