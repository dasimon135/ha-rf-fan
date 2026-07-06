"""Plateforme switch pour RF Fan (bascule du son)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTION_SOUND_TOGGLE, CONF_HAS_SOUND, EVENT_RF_FAN_RECEIVED
from .entity import RfFanBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurer l'interrupteur son si le ventilateur gère le son."""
    if not config_entry.data.get(CONF_HAS_SOUND, False):
        return

    async_add_entities([RfFanSoundSwitch(hass, config_entry)])


class RfFanSoundSwitch(RfFanBaseEntity, SwitchEntity):
    """Interrupteur de son à état supposé (bascule unique)."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialiser l'interrupteur son."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_sound"
        self._attr_name = "Son"
        self._is_on: bool | None = None
        self._event_unsub = None

    @property
    def is_on(self) -> bool | None:
        """Retourner l'état son supposé."""
        return self._is_on

    async def async_added_to_hass(self) -> None:
        """S'abonner aux événements RF reçus par ESPHome."""
        self._event_unsub = self.hass.bus.async_listen(EVENT_RF_FAN_RECEIVED, self._handle_rf_event)

    async def async_will_remove_from_hass(self) -> None:
        """Désabonner les callbacks."""
        if self._event_unsub is not None:
            self._event_unsub()
            self._event_unsub = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activer le son."""
        if self._is_on is not True:
            sent = await self._async_transmit_action(ACTION_SOUND_TOGGLE)
            if sent:
                self._is_on = True
                self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Désactiver le son."""
        if self._is_on is not False:
            sent = await self._async_transmit_action(ACTION_SOUND_TOGGLE)
            if sent:
                self._is_on = False
                self.async_write_ha_state()

    @callback
    def _handle_rf_event(self, event: Any) -> None:
        """Basculer l'état son depuis l'action RF reçue."""
        if self._recently_transmitted():
            return

        action = self._event_action(event.data)
        if action == ACTION_SOUND_TOGGLE and self._is_on is not None:
            self._is_on = not self._is_on
            self.async_write_ha_state()
