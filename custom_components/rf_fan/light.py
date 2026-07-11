"""Light platform for RF Fan."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ACTION_LIGHT_OFF,
    ACTION_LIGHT_ON,
    ACTION_LIGHT_TOGGLE,
    CONF_HAS_COLOR_TEMP,
    CONF_HAS_LIGHT,
    EVENT_RF_FAN_RECEIVED,
)
from .entity import RfFanBaseEntity


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
    """Generic RF light (on/off)."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the light entity."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_light"
        self._attr_name = "Lampe"
        self._is_on: bool | None = None
        self._event_unsub = None
        self._has_color_temp: bool = config_entry.data.get(CONF_HAS_COLOR_TEMP, False)

    @property
    def is_on(self) -> bool | None:
        """Return the assumed on/off state."""
        return self._is_on

    async def async_added_to_hass(self) -> None:
        """Restore the assumed on/off state (without a color bump), then subscribe to RF events."""
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ("on", "off"):
            self._is_on = last_state.state == "on"
            # Share the restored state so the color select gates correctly on startup.
            self._entry_runtime()["light_on"] = self._is_on
            async_dispatcher_send(self.hass, self._kelvin_signal())
        self._event_unsub = self.hass.bus.async_listen(EVENT_RF_FAN_RECEIVED, self._handle_rf_event)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe the callbacks."""
        if self._event_unsub is not None:
            self._event_unsub()
            self._event_unsub = None

    def _bump_kelvin(self) -> None:
        """Advance the color position by one step (the hardware advances on each power-on)."""
        if not self._has_color_temp:
            return
        self._advance_kelvin_position()
        async_dispatcher_send(self.hass, self._kelvin_signal())

    def _publish_light_state(self) -> None:
        """Share the assumed on/off state (so the color select can gate on it) and refresh."""
        self._entry_runtime()["light_on"] = self._is_on
        async_dispatcher_send(self.hass, self._kelvin_signal())
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        was_on = self._is_on
        sent = await self._async_transmit_action(ACTION_LIGHT_ON)
        if not sent:
            sent = await self._async_transmit_action(ACTION_LIGHT_TOGGLE)
        if sent:
            self._is_on = True
            # The hardware only advances the color on a real OFF->ON transition.
            if not was_on:
                self._bump_kelvin()
            self._publish_light_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        sent = await self._async_transmit_action(ACTION_LIGHT_OFF)
        if not sent:
            sent = await self._async_transmit_action(ACTION_LIGHT_TOGGLE)
        if sent:
            self._is_on = False
            self._publish_light_state()

    @callback
    def _handle_rf_event(self, event: Any) -> None:
        """Update the light state from the received RF actions."""
        if self._recently_transmitted():
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
