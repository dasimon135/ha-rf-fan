"""Plateforme light pour RF Fan."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTION_LIGHT_OFF, ACTION_LIGHT_ON, ACTION_LIGHT_TOGGLE, CONF_HAS_LIGHT, EVENT_RF_FAN_RECEIVED
from .entity import RfFanBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurer l'entité light si le ventilateur a une lumière."""
    if not config_entry.data.get(CONF_HAS_LIGHT, True):
        return

    async_add_entities([RfFanLightEntity(hass, config_entry)])


class RfFanLightEntity(RfFanBaseEntity, LightEntity):
    """Lumière RF générique (on/off)."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialiser l'entité light."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_light"
        self._attr_name = "Light"
        self._is_on: bool | None = None
        self._event_unsub = None

    @property
    def is_on(self) -> bool | None:
        """Retourner l'état on/off supposé."""
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
        """Allumer la lumière."""
        sent = await self._async_transmit_action(ACTION_LIGHT_ON)
        if not sent:
            sent = await self._async_transmit_action(ACTION_LIGHT_TOGGLE)
        if sent:
            self._is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Éteindre la lumière."""
        sent = await self._async_transmit_action(ACTION_LIGHT_OFF)
        if not sent:
            sent = await self._async_transmit_action(ACTION_LIGHT_TOGGLE)
        if sent:
            self._is_on = False
            self.async_write_ha_state()

    @callback
    def _handle_rf_event(self, event: Any) -> None:
        """Mettre à jour l'état light depuis les actions RF reçues."""
        action = self._event_action(event.data)
        if action is None:
            return

        if action == ACTION_LIGHT_ON:
            self._is_on = True
            self.async_write_ha_state()
            return

        if action == ACTION_LIGHT_OFF:
            self._is_on = False
            self.async_write_ha_state()
            return

        if action == ACTION_LIGHT_TOGGLE and self._is_on is not None:
            self._is_on = not self._is_on
            self.async_write_ha_state()
