"""Light platform for RF Fan."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .actions import caps_from_data
from .const import (
    ACTION_LIGHT_BRIGHT_DOWN,
    ACTION_LIGHT_BRIGHT_UP,
    ACTION_LIGHT_OFF,
    ACTION_LIGHT_ON,
    ACTION_LIGHT_TOGGLE,
    AXIS_LEVEL,
    COLOR_CONTROL_NONE,
    CONF_HAS_LIGHT,
    DEFAULT_LIGHT_LEVEL_STEPS,
    EVENT_RF_FAN_RECEIVED,
    LIGHT_LEVEL_RELATIVE,
)
from .entity import RfFanBaseEntity


def brightness_to_position(brightness: int, steps: int = DEFAULT_LIGHT_LEVEL_STEPS) -> int:
    """Map Home Assistant's 1-255 brightness onto a 0-based step position.

    Position p means "p presses up from the bottom", so position 0 is the dimmest
    the lamp goes while still on — never off. Turning the light off is a separate
    action, not the bottom of the range.
    """
    position = round(brightness * steps / 255) - 1
    return max(0, min(steps - 1, position))


def position_to_brightness(position: int, steps: int = DEFAULT_LIGHT_LEVEL_STEPS) -> int:
    """Map a step position back onto 1-255, so the top position reads as full."""
    return max(1, min(255, round(255 * (position + 1) / steps)))


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the light entity if the fan has a light."""
    if not config_entry.data.get(CONF_HAS_LIGHT, True):
        return

    async_add_entities([RfFanLightEntity(hass, config_entry)])


class RfFanLightEntity(RfFanBaseEntity, RestoreEntity, LightEntity):
    """Generic RF light: on/off, plus dead-reckoned brightness when the remote steps it.

    `ColorMode.BRIGHTNESS` is declared only when the remote actually has +/- keys.
    Declaring it otherwise would put a slider in front of the user that cannot move
    anything. Where it is declared, the brightness is genuinely assumed: the lamp
    never reports back, so the position is "presses counted from the bottom" and the
    resynchronise button is the way back when it drifts.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the light entity."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_light"
        self._attr_translation_key = "light"
        self._is_on: bool | None = None
        self._event_unsub = None
        self._signal_unsub = None

        caps = caps_from_data(dict(config_entry.data))
        self._has_color_temp: bool = caps["color_control"] != COLOR_CONTROL_NONE
        self._has_level: bool = caps["light_level"] == LIGHT_LEVEL_RELATIVE

        if self._has_level:
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        else:
            self._attr_color_mode = ColorMode.ONOFF
            self._attr_supported_color_modes = {ColorMode.ONOFF}

    @property
    def is_on(self) -> bool | None:
        """Return the assumed on/off state."""
        return self._is_on

    @property
    def brightness(self) -> int | None:
        """Return the assumed brightness, or None while the position is unknown."""
        if not self._has_level:
            return None
        position = self._runtime.level_position
        return (
            None
            if position is None
            else position_to_brightness(position, self._light_level_steps)
        )

    async def async_added_to_hass(self) -> None:
        """Restore the assumed state (without a color bump), then subscribe to RF events."""
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ("on", "off"):
            self._is_on = last_state.state == "on"
            # Share the restored state so the color select gates correctly on startup.
            self._runtime.light_on = self._is_on
            if self._has_level and self._runtime.level_position is None:
                restored = last_state.attributes.get(ATTR_BRIGHTNESS)
                if isinstance(restored, (int, float)) and restored > 0:
                    self._runtime.level_position = brightness_to_position(
                        int(restored), self._light_level_steps
                    )
            async_dispatcher_send(self.hass, self._kelvin_signal())
        self._event_unsub = self.hass.bus.async_listen(EVENT_RF_FAN_RECEIVED, self._handle_rf_event)
        if self._has_level:
            self._signal_unsub = async_dispatcher_connect(
                self.hass, self._level_signal(), self._on_level_changed
            )

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe the callbacks."""
        if self._event_unsub is not None:
            self._event_unsub()
            self._event_unsub = None
        if self._signal_unsub is not None:
            self._signal_unsub()
            self._signal_unsub = None

    @callback
    def _on_level_changed(self) -> None:
        """Refresh when the position select declares a different brightness."""
        self.async_write_ha_state()

    def _bump_kelvin(self) -> None:
        """Advance the color position by one step (the hardware advances on each power-on)."""
        if not self._has_color_temp:
            return
        self._advance_kelvin_position()
        async_dispatcher_send(self.hass, self._kelvin_signal())

    def _publish_light_state(self) -> None:
        """Share the assumed on/off state (so the color select can gate on it) and refresh."""
        self._runtime.light_on = self._is_on
        async_dispatcher_send(self.hass, self._kelvin_signal())
        self.async_write_ha_state()

    def _set_level_position(self, position: int) -> None:
        """Record a brightness step that actually went on the air, and refresh."""
        self._runtime.level_position = position
        async_dispatcher_send(self.hass, self._level_signal())
        self.async_write_ha_state()

    async def _async_walk_brightness(self, brightness: int) -> None:
        """Step the lamp to the position matching `brightness`."""
        await self._async_walk(
            AXIS_LEVEL,
            up_action=ACTION_LIGHT_BRIGHT_UP,
            down_action=ACTION_LIGHT_BRIGHT_DOWN,
            target=brightness_to_position(brightness, self._light_level_steps),
            size=self._light_level_steps,
            # A brightness range has two end stops; it does not come round.
            wrap=False,
            get_position=lambda: self._runtime.level_position,
            set_position=self._set_level_position,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light, and step it to a requested brightness."""
        was_on = self._is_on
        sent = await self._async_transmit_action(ACTION_LIGHT_ON)
        if not sent:
            sent = await self._async_transmit_action(ACTION_LIGHT_TOGGLE)
        if not sent:
            return

        self._is_on = True
        # The hardware only advances the color on a real OFF->ON transition.
        if not was_on:
            self._bump_kelvin()
        self._publish_light_state()

        # Applied after the power: the +/- keys only reach a lamp that is already lit.
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if self._has_level and brightness is not None:
            await self._async_walk_brightness(int(brightness))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        sent = await self._async_transmit_action(ACTION_LIGHT_OFF)
        if not sent:
            sent = await self._async_transmit_action(ACTION_LIGHT_TOGGLE)
        if sent:
            self._is_on = False
            self._publish_light_state()

    def _step_level(self, delta: int) -> None:
        """Move the assumed brightness one notch, clamping at both ends."""
        current = self._runtime.level_position
        moved = (0 if current is None else current) + delta
        self._runtime.level_position = max(0, min(self._light_level_steps - 1, moved))
        async_dispatcher_send(self.hass, self._level_signal())
        self.async_write_ha_state()

    @callback
    def _handle_rf_event(self, event: Any) -> None:
        """Update the light state from the received RF actions."""
        # Short-circuit order matters: an echo of our own transmission is not a
        # remote press at all, so it must never be recorded as the start of a burst.
        if self._is_echo(event.data) or self._is_repeat(event):
            return

        action = self._event_action(event.data)
        if action is None:
            return

        if action == ACTION_LIGHT_ON:
            was_on = self._is_on
            self._is_on = True
            if not was_on:
                self._bump_kelvin()
            self._publish_light_state()
            return

        if action == ACTION_LIGHT_OFF:
            self._is_on = False
            self._publish_light_state()
            return

        if action == ACTION_LIGHT_TOGGLE and self._is_on is not None:
            self._is_on = not self._is_on
            if self._is_on:
                self._bump_kelvin()
            self._publish_light_state()
            return

        # A press on the physical +/- keys is a known delta, so the assumed
        # brightness follows the remote as well as it follows Home Assistant.
        if action == ACTION_LIGHT_BRIGHT_UP:
            self._step_level(1)
        elif action == ACTION_LIGHT_BRIGHT_DOWN:
            self._step_level(-1)
