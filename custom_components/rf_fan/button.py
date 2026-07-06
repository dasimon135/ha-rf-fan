"""Plateforme button pour RF Fan (minuteries de sommeil)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_HAS_TIMERS, TIMER_HOURS, timer_action
from .entity import RfFanBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurer les boutons minuterie si le ventilateur gère les minuteries."""
    if not config_entry.data.get(CONF_HAS_TIMERS, False):
        return

    async_add_entities(
        [RfFanTimerButton(hass, config_entry, hours) for hours in TIMER_HOURS]
    )


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
