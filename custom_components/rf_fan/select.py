"""Select platform for RF Fan (color temperature, assumed brightness position)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .actions import caps_from_data
from .const import (
    ACTION_LIGHT_KELVIN,
    ACTION_LIGHT_KELVIN_DOWN,
    ACTION_LIGHT_KELVIN_UP,
    AXIS_COLOR,
    COLOR_CONTROL_NONE,
    COLOR_CONTROL_RELATIVE,
    COLOR_TEMP_OPTIONS,
    EVENT_RF_FAN_RECEIVED,
    LIGHT_LEVEL_RELATIVE,
    LIGHT_LEVEL_STEPS,
)
from .entity import RfFanBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the color select, and the assumed brightness position if relevant."""
    caps = caps_from_data(dict(config_entry.data))
    entities: list[SelectEntity] = []

    if caps["color_control"] != COLOR_CONTROL_NONE:
        entities.append(RfFanColorTempSelect(hass, config_entry))
    if caps["light_level"] == LIGHT_LEVEL_RELATIVE:
        entities.append(RfFanBrightnessPositionSelect(hass, config_entry))

    if entities:
        async_add_entities(entities)


class RfFanColorTempSelect(RfFanBaseEntity, RestoreEntity, SelectEntity):
    """Color temperature selector with assumed state (dead-reckoning).

    Two remote shapes reach the same entity:

    - `cycle`: a single key that walks the positions in a fixed loop. Only one
      direction exists, so the walk always goes forward and comes round.
    - `relative`: two dedicated keys (warmer / cooler), so the walk takes whichever
      way round is shorter.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the select entity."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_color_temp"
        self._attr_translation_key = "color_temperature"
        self._attr_options = COLOR_TEMP_OPTIONS
        self._color_control: str = caps_from_data(dict(config_entry.data))["color_control"]
        self._event_unsub = None
        self._signal_unsub = None

    @property
    def current_option(self) -> str:
        """Return the assumed color position."""
        return COLOR_TEMP_OPTIONS[self._runtime.kelvin_position]

    @property
    def available(self) -> bool:
        """Unavailable while the light is known to be off (the color cycle needs it on)."""
        return self._runtime.light_on is not False

    def _set_kelvin_position(self, position: int) -> None:
        """Record a step that actually went on the air, and refresh."""
        self._runtime.kelvin_position = position
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Walk to the requested color position (ignored while the light is off)."""
        if self._runtime.light_on is False:
            # The lamp only cycles color while powered on; skip to avoid desync.
            return
        relative = self._color_control == COLOR_CONTROL_RELATIVE
        await self._async_walk(
            AXIS_COLOR,
            up_action=ACTION_LIGHT_KELVIN_UP if relative else ACTION_LIGHT_KELVIN,
            # A cycling remote has no second key: forward-only, wrapping round.
            down_action=ACTION_LIGHT_KELVIN_DOWN if relative else None,
            target=COLOR_TEMP_OPTIONS.index(option),
            size=len(COLOR_TEMP_OPTIONS),
            wrap=True,
            get_position=lambda: self._runtime.kelvin_position,
            set_position=self._set_kelvin_position,
        )
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the color position, then subscribe to RF events and the kelvin signal."""
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in COLOR_TEMP_OPTIONS:
            self._runtime.kelvin_position = COLOR_TEMP_OPTIONS.index(last_state.state)

        self._event_unsub = self.hass.bus.async_listen(EVENT_RF_FAN_RECEIVED, self._handle_rf_event)
        self._signal_unsub = async_dispatcher_connect(
            self.hass, self._kelvin_signal(), self._on_kelvin_changed
        )
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe the callbacks."""
        if self._event_unsub is not None:
            self._event_unsub()
            self._event_unsub = None
        if self._signal_unsub is not None:
            self._signal_unsub()
            self._signal_unsub = None

    @callback
    def _on_kelvin_changed(self) -> None:
        """Refresh the state when the light advances the color position."""
        self.async_write_ha_state()

    @callback
    def _handle_rf_event(self, event: Any) -> None:
        """Follow the physical remote's colour keys.

        This is where a relative remote beats a cycling one: each press is a known
        delta, so the assumed position tracks the hardware in both directions
        instead of only forwards.
        """
        if self._is_echo(event.data):
            return

        action = self._event_action(event.data)
        if action in (ACTION_LIGHT_KELVIN, ACTION_LIGHT_KELVIN_UP):
            self._advance_kelvin_position()
            self.async_write_ha_state()
        elif action == ACTION_LIGHT_KELVIN_DOWN:
            self._advance_kelvin_position(-1)
            self.async_write_ha_state()


class RfFanBrightnessPositionSelect(RfFanBaseEntity, RestoreEntity, SelectEntity):
    """Assumed brightness position — declares where the lamp is, emits nothing.

    The light entity's brightness slider MOVES the lamp; this one only says where
    the integration believes it already is. Dead reckoning has no way back once it
    drifts: the lamp never reports, and a remote press Home Assistant did not see is
    invisible to it. Declaring the truth is silent and instant, where the
    resynchronise button is audible and slow.

    `EntityCategory.CONFIG`: it configures the integration's belief, not the fan.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the brightness position select."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_brightness_position"
        self._attr_translation_key = "brightness_position"
        self._attr_options = [str(step) for step in range(1, LIGHT_LEVEL_STEPS + 1)]
        self._signal_unsub = None

    @property
    def current_option(self) -> str | None:
        """Return the assumed brightness position, 1-based for display."""
        position = self._runtime.level_position
        return None if position is None else str(position + 1)

    async def async_select_option(self, option: str) -> None:
        """Declare the position without touching the lamp."""
        self._runtime.level_position = int(option) - 1
        async_dispatcher_send(self.hass, self._level_signal())
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the declared position and follow the light's own updates."""
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self._attr_options:
            self._runtime.level_position = int(last_state.state) - 1

        self._signal_unsub = async_dispatcher_connect(
            self.hass, self._level_signal(), self._on_level_changed
        )
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe the callbacks."""
        if self._signal_unsub is not None:
            self._signal_unsub()
            self._signal_unsub = None

    @callback
    def _on_level_changed(self) -> None:
        """Refresh when the light walks the brightness position."""
        self.async_write_ha_state()
