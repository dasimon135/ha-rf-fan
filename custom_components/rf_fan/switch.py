"""Switch platform for RF Fan (sound toggle)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import ACTION_SOUND_TOGGLE, CONF_HAS_SOUND, EVENT_RF_FAN_RECEIVED
from .entity import RfFanBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sound switch if the fan supports sound."""
    if not config_entry.data.get(CONF_HAS_SOUND, False):
        return

    async_add_entities([RfFanSoundSwitch(hass, config_entry)])


class RfFanSoundSwitch(RfFanBaseEntity, RestoreEntity, SwitchEntity):
    """Sound switch with assumed state (single toggle)."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the sound switch."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_sound"
        self._attr_name = "Son"
        self._is_on: bool | None = None
        self._event_unsub = None

    @property
    def is_on(self) -> bool | None:
        """Return the assumed sound state."""
        return self._is_on

    async def async_added_to_hass(self) -> None:
        """Restore the assumed sound state, then subscribe to RF events."""
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ("on", "off"):
            self._is_on = last_state.state == "on"
        self._event_unsub = self.hass.bus.async_listen(EVENT_RF_FAN_RECEIVED, self._handle_rf_event)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe the callbacks."""
        if self._event_unsub is not None:
            self._event_unsub()
            self._event_unsub = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the sound."""
        if self._is_on is not True:
            sent = await self._async_transmit_action(ACTION_SOUND_TOGGLE)
            if sent:
                self._is_on = True
                self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the sound."""
        if self._is_on is not False:
            sent = await self._async_transmit_action(ACTION_SOUND_TOGGLE)
            if sent:
                self._is_on = False
                self.async_write_ha_state()

    @callback
    def _handle_rf_event(self, event: Any) -> None:
        """Toggle the sound state from the received RF action."""
        if self._recently_transmitted():
            return

        action = self._event_action(event.data)
        if action == ACTION_SOUND_TOGGLE and self._is_on is not None:
            self._is_on = not self._is_on
            self.async_write_ha_state()
