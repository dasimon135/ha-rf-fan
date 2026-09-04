"""Button platform for RF Fan (sleep timers, calibration, free-form keys)."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .actions import (
    caps_from_data,
    extra_button_count,
    extra_names,
    timer_hours_from_data,
)
from .const import (
    ACTION_LIGHT_BRIGHT_DOWN,
    ACTION_TIMER_OFF,
    COLOR_CONTROL_NONE,
    CONF_HAS_TIMER_OFF,
    LIGHT_LEVEL_RELATIVE,
    STEP_GAP_SEC,
    extra_action,
    extra_default_name,
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

    # One button per duration the remote actually has, in TIMER_HOURS order.
    entities.extend(
        RfFanTimerButton(hass, config_entry, hours)
        for hours in timer_hours_from_data(dict(config_entry.data))
    )
    if config_entry.data.get(CONF_HAS_TIMER_OFF, False):
        entities.append(RfFanTimerOffButton(hass, config_entry))

    if caps["color_control"] != COLOR_CONTROL_NONE:
        entities.append(RfFanKelvinCalibrateButton(hass, config_entry))

    if caps["light_level"] == LIGHT_LEVEL_RELATIVE:
        entities.append(RfFanBrightnessResyncButton(hass, config_entry))

    data = dict(config_entry.data)
    names = extra_names(data)
    entities.extend(
        RfFanExtraButton(hass, config_entry, index, names.get(extra_action(index), ""))
        for index in range(1, extra_button_count(data) + 1)
    )

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


class RfFanTimerOffButton(RfFanBaseEntity, ButtonEntity):
    """Button that cancels a running sleep timer.

    Unlike the calibration buttons this one DOES emit: the fan is holding a
    countdown of its own, and only a frame can call it off. The assumed
    switch-off time is cleared to match -- but only once the code is on the air,
    for the same reason the timer buttons only claim a time once theirs is.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the timer-cancel button."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_{ACTION_TIMER_OFF}"
        self._attr_translation_key = "timer_off"

    async def async_press(self) -> None:
        """Emit the cancel action and drop the assumed switch-off time."""
        if not await self._async_transmit_action(ACTION_TIMER_OFF):
            return
        self._runtime.timer_ends_at = None
        async_dispatcher_send(self.hass, self._timer_signal())


class RfFanKelvinCalibrateButton(RfFanBaseEntity, ButtonEntity):
    """Calibration button: resets the assumed colour position to the first one."""

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
            ACTION_LIGHT_BRIGHT_DOWN, self._light_level_steps - 1, gap=STEP_GAP_SEC
        ):
            # Nothing went on the air (unmapped code): the lamp has not moved, so
            # claiming it sits at the bottom would replace one wrong position with
            # another.
            return
        self._runtime.level_position = 0
        async_dispatcher_send(self.hass, self._level_signal())


class RfFanExtraButton(RfFanBaseEntity, ButtonEntity):
    """A remote key this integration has no concept of, replayed under its owner's name.

    Everything else here means something: a timer ends, a calibration declares a
    position. This one means "send that code", and it is the honest shape for a key
    whose effect nobody can describe -- @elmr91's remote has a "memory" button and
    neither Home Assistant nor this integration knows what the fan does with it
    (issue #18).

    So there is no state, assumed or otherwise: a checkbox saying "memory on" would
    display a belief that nothing can establish and nothing can correct.

    The name is the user's; the `translation_key` stays set anyway, because the
    bundled card identifies these by key rather than by elimination -- guessing a
    button's role from what it is NOT is what once wired a colour row to the button
    that walks the lamp down to its end stop (#29).

    The key carries the INDEX (`extra_3`), not just the family. The frontend's
    registry hands a card `translation_key`, `platform` and `entity_category` but
    never the unique id, so the index in the key is the only thing that can put the
    chips in the order of the keys on the remote rather than in alphabetical order
    of whatever their owner called them.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        index: int,
        label: str,
    ) -> None:
        """Initialize one free-form button."""
        super().__init__(hass, config_entry)
        self._action = extra_action(index)
        self._attr_unique_id = f"{config_entry.entry_id}_{self._action}"
        self._attr_translation_key = self._action
        # An explicit name outranks the translation key, which is what lets the
        # entity carry the user's label while staying identifiable by that key.
        self._attr_name = label or extra_default_name(index)

    async def async_press(self) -> None:
        """Transmit the learned code.

        Counted as a toggle (`TOGGLE_ACTIONS`), which is the safe default for a key
        whose effect is unknowable: the two mistakes are not symmetric. An absolute
        code sent an odd number of times lands exactly where an even number would,
        while a real toggle sent an even number of times nets zero flips and the
        button appears dead -- with nothing to debug from the outside.
        """
        await self._async_transmit_action(self._action)
