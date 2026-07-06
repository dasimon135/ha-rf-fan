"""Plateforme button pour RF Fan (minuteries de sommeil)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_HAS_COLOR_TEMP, CONF_HAS_TIMERS, TIMER_HOURS, timer_action
from .entity import RfFanBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurer les boutons (minuteries et/ou calibration couleur)."""
    entities: list[ButtonEntity] = []

    if config_entry.data.get(CONF_HAS_TIMERS, False):
        entities.extend(
            RfFanTimerButton(hass, config_entry, hours) for hours in TIMER_HOURS
        )

    if config_entry.data.get(CONF_HAS_COLOR_TEMP, False):
        entities.append(RfFanKelvinCalibrateButton(hass, config_entry))

    if entities:
        async_add_entities(entities)


class RfFanTimerButton(RfFanBaseEntity, ButtonEntity):
    """Bouton déclenchant une minuterie de sommeil de N heures."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, hours: int) -> None:
        """Initialiser le bouton minuterie."""
        super().__init__(hass, config_entry)
        self._hours = hours
        self._attr_unique_id = f"{config_entry.entry_id}_timer_{hours}h"
        self._attr_name = f"Minuterie {hours}h"

    async def async_press(self) -> None:
        """Émettre l'action minuterie correspondante."""
        await self._async_transmit_action(timer_action(self._hours))


class RfFanKelvinCalibrateButton(RfFanBaseEntity, ButtonEntity):
    """Bouton de calibration : réinitialise la position couleur supposée à « Chaud »."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialiser le bouton de calibration couleur."""
        super().__init__(hass, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_kelvin_calibrate"
        self._attr_name = "Couleur → Chaud (calibrer)"

    async def async_press(self) -> None:
        """Remettre la position couleur à zéro sans émettre de code RF."""
        runtime = self._entry_runtime()
        runtime["kelvin_position"] = 0
        async_dispatcher_send(self.hass, self._kelvin_signal())
