"""Select platform for RF Fan (color temperature)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ACTION_LIGHT_KELVIN,
    COLOR_TEMP_OPTIONS,
    CONF_HAS_COLOR_TEMP,
    EVENT_RF_FAN_RECEIVED,
)
from .entity import RfFanBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select entity if the fan supports color temperature."""
    if not config_entry.data.get(CONF_HAS_COLOR_TEMP, False):
        return

    async_add_entities([RfFanColorTempSelect(hass, config_entry)])


class RfFanColorTempSelect(RfFanBaseEntity, RestoreEntity, SelectEntity):
    """Color temperature selector with assumed state (dead-reckoning)."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the select entity."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_color_temp"
        self._attr_translation_key = "color_temperature"
        self._attr_options = COLOR_TEMP_OPTIONS
        self._event_unsub = None
        self._signal_unsub = None

    @property
    def current_option(self) -> str:
        """Return the assumed color position."""
        return COLOR_TEMP_OPTIONS[self._entry_runtime().get("kelvin_position", 0)]

    @property
    def available(self) -> bool:
        """Unavailable while the light is known to be off (the color cycle needs it on)."""
        return self._entry_runtime().get("light_on") is not False

    async def async_select_option(self, option: str) -> None:
        """Cycle to the requested color position (ignored while the light is off)."""
        runtime = self._entry_runtime()
        if runtime.get("light_on") is False:
            # The lamp only cycles color while powered on; skip to avoid desync.
            return
        target = COLOR_TEMP_OPTIONS.index(option)
        steps = (target - runtime.get("kelvin_position", 0)) % len(COLOR_TEMP_OPTIONS)
        await self._async_transmit_times(ACTION_LIGHT_KELVIN, steps)
        runtime["kelvin_position"] = target
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the color position, then subscribe to RF events and the kelvin signal."""
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in COLOR_TEMP_OPTIONS:
            self._entry_runtime()["kelvin_position"] = COLOR_TEMP_OPTIONS.index(last_state.state)

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
        """Advance the color position when the remote emits the kelvin action."""
        if self._recently_transmitted():
            return

        action = self._event_action(event.data)
        if action == ACTION_LIGHT_KELVIN:
            self._advance_kelvin_position()
            self.async_write_ha_state()
