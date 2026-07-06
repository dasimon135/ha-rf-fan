"""Base entité pour RF Fan."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from .const import CONF_CODES, CONF_ESPHOME_DEVICE, CONF_FAN_NAME, CONF_REPEAT_COUNT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class RfFanBaseEntity(Entity):
    """Entité de base pour le ventilateur RF."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialiser l'entité de base."""
        self.hass = hass
        self._config_entry = config_entry
        self._esphome_device: str = config_entry.data[CONF_ESPHOME_DEVICE]
        self._fan_name: str = config_entry.data[CONF_FAN_NAME]
        self._codes: dict[str, str] = config_entry.data[CONF_CODES]

        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": self._fan_name,
            "manufacturer": "Generic RF",
            "model": "RF Fan",
        }

    def _repeat_count(self) -> int:
        """Retourner le nombre de répétitions RF."""
        return int(
            self._config_entry.options.get(
                CONF_REPEAT_COUNT,
                self._config_entry.data.get(CONF_REPEAT_COUNT, 2),
            )
        )

    async def _async_transmit_action(self, action: str) -> bool:
        """Transmettre une action RF via ESPHome si elle est mappée."""
        code = self._codes.get(action)
        if not code:
            _LOGGER.debug("Action non mappée ignorée: %s", action)
            return False

        service_name = f"{self._esphome_device.replace('-', '_')}_transmit_rf_fan"
        try:
            await self.hass.services.async_call(
                "esphome",
                service_name,
                {
                    "action": action,
                    "code": code,
                    "repeat_count": self._repeat_count(),
                },
                blocking=True,
            )
        except Exception as err:  # pragma: no cover
            _LOGGER.warning("Erreur envoi RF (%s): %s", action, err)
            return False

        return True

    async def _async_transmit_times(self, action: str, times: int) -> bool:
        """Émettre `times` fois le code d'une action (cycle). True si au moins une émission."""
        sent_any = False
        for _ in range(max(0, times)):
            if await self._async_transmit_action(action):
                sent_any = True
        return sent_any

    def _entry_runtime(self) -> dict:
        """Dict d'état partagé de l'entrée (créé dans __init__.py async_setup_entry)."""
        return self.hass.data[DOMAIN][self._config_entry.entry_id]

    def _is_own_event(self, event_data: dict[str, Any]) -> bool:
        """Vérifier que l'événement RF vient de la passerelle configurée."""
        device = event_data.get("device")
        if not isinstance(device, str) or not device:
            return True
        return device == self._esphome_device

    def _event_action(self, event_data: dict[str, Any]) -> str | None:
        """Extraire l'action RF reçue depuis l'événement ESPHome."""
        if not self._is_own_event(event_data):
            return None

        action = event_data.get("action")
        if isinstance(action, str) and action and action != "sniff":
            return action

        code = event_data.get("code")
        if not isinstance(code, str) or not code:
            return None

        for mapped_action, mapped_code in self._codes.items():
            if mapped_code == code:
                return mapped_action
        return None
