"""Constantes pour l'intégration RF fan générique."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "rf_fan"

EVENT_RF_FAN_RECEIVED: Final = "esphome.rf_fan_received"

CONF_ESPHOME_DEVICE: Final = "esphome_device"
CONF_FAN_NAME: Final = "fan_name"
CONF_SPEED_COUNT: Final = "speed_count"
CONF_HAS_LIGHT: Final = "has_light"
CONF_REPEAT_COUNT: Final = "repeat_count"
CONF_CODES: Final = "codes"

DEFAULT_SPEED_COUNT: Final = 3
DEFAULT_HAS_LIGHT: Final = True
DEFAULT_REPEAT_COUNT: Final = 2

ACTION_FAN_ON: Final = "fan_on"
ACTION_FAN_OFF: Final = "fan_off"
ACTION_LIGHT_ON: Final = "light_on"
ACTION_LIGHT_OFF: Final = "light_off"
ACTION_LIGHT_TOGGLE: Final = "light_toggle"


def speed_action(index: int) -> str:
    """Retourner la clé d'action de vitesse pour un index donné."""
    return f"fan_speed_{index}"
