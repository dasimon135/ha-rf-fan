"""Plateforme select pour RF Fan (température de couleur)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ACTION_LIGHT_KELVIN,
    COLOR_TEMP_OPTIONS,
    CONF_HAS_COLOR_TEMP,
    DOMAIN,
    EVENT_RF_FAN_RECEIVED,
)
from .entity import RfFanBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurer l'entité select si le ventilateur gère la température de couleur."""
    if not config_entry.data.get(CONF_HAS_COLOR_TEMP, False):
        return

    async_add_entities([RfFanColorTempSelect(hass, config_entry)])


class RfFanColorTempSelect(RfFanBaseEntity, SelectEntity):
    """Sélecteur de température de couleur à état supposé (dead-reckoning)."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialiser l'entité select."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_color_temp"
        self._attr_name = "Température couleur"
        self._attr_options = COLOR_TEMP_OPTIONS
        self._event_unsub = None
        self._signal_unsub = None

    @property
    def _kelvin_signal(self) -> str:
        """Nom du signal dispatcher couplant la lumière à ce sélecteur."""
        return f"{DOMAIN}_{self._config_entry.entry_id}_kelvin"

    @property
    def current_option(self) -> str:
        """Retourner la position couleur supposée."""
        return COLOR_TEMP_OPTIONS[self._entry_runtime()["kelvin_position"]]

    async def async_select_option(self, option: str) -> None:
        """Cycler jusqu'à la position couleur demandée."""
        target = COLOR_TEMP_OPTIONS.index(option)
        runtime = self._entry_runtime()
        steps = (target - runtime["kelvin_position"]) % len(COLOR_TEMP_OPTIONS)
        await self._async_transmit_times(ACTION_LIGHT_KELVIN, steps)
        runtime["kelvin_position"] = target
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """S'abonner aux événements RF et au signal de couplage kelvin."""
        self._event_unsub = self.hass.bus.async_listen(EVENT_RF_FAN_RECEIVED, self._handle_rf_event)
        self._signal_unsub = async_dispatcher_connect(
            self.hass, self._kelvin_signal, self._on_kelvin_changed
        )

    async def async_will_remove_from_hass(self) -> None:
        """Désabonner les callbacks."""
        if self._event_unsub is not None:
            self._event_unsub()
            self._event_unsub = None
        if self._signal_unsub is not None:
            self._signal_unsub()
            self._signal_unsub = None

    @callback
    def _on_kelvin_changed(self) -> None:
        """Rafraîchir l'état quand la lumière avance la position couleur."""
        self.async_write_ha_state()

    @callback
    def _handle_rf_event(self, event: Any) -> None:
        """Avancer la position couleur quand la télécommande émet l'action kelvin."""
        action = self._event_action(event.data)
        if action == ACTION_LIGHT_KELVIN:
            runtime = self._entry_runtime()
            runtime["kelvin_position"] = (
                runtime["kelvin_position"] + 1
            ) % len(COLOR_TEMP_OPTIONS)
            self.async_write_ha_state()
