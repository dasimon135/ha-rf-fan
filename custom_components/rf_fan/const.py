"""Constantes pour l'intégration RF fan générique."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "rf_fan"

EVENT_RF_FAN_RECEIVED: Final = "esphome.rf_fan_received"

CONF_ESPHOME_DEVICE: Final = "esphome_device"
CONF_FAN_NAME: Final = "fan_name"
CONF_SPEED_COUNT: Final = "speed_count"
CONF_HAS_LIGHT: Final = "has_light"
CONF_LIGHT_CONTROL: Final = "light_control"
CONF_HAS_FAN_ON: Final = "has_fan_on"
LIGHT_CONTROL_NONE: Final = "none"
LIGHT_CONTROL_TOGGLE: Final = "toggle"
LIGHT_CONTROL_ON_OFF: Final = "on_off"
LIGHT_CONTROL_OPTIONS: Final = [LIGHT_CONTROL_NONE, LIGHT_CONTROL_TOGGLE, LIGHT_CONTROL_ON_OFF]
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

# Capacités (config flow)
CONF_HAS_DIRECTION: Final = "has_direction"
CONF_HAS_NATURAL_PRESET: Final = "has_natural_preset"
CONF_HAS_COLOR_TEMP: Final = "has_color_temp"
CONF_HAS_TIMERS: Final = "has_timers"
CONF_HAS_SOUND: Final = "has_sound"

# Nouvelles actions
ACTION_FAN_REVERSE: Final = "fan_reverse"
ACTION_FAN_NATURAL: Final = "fan_natural"
ACTION_LIGHT_KELVIN: Final = "light_kelvin"
ACTION_SOUND_TOGGLE: Final = "sound_toggle"
TIMER_HOURS: Final = (1, 2, 4, 8)

# Preset flux naturel
PRESET_NORMAL: Final = "normal"
PRESET_NATURAL: Final = "natural"

# Positions couleur (select kelvin) : ordre du cycle matériel
COLOR_TEMP_OPTIONS: Final = ["Chaud", "Neutre", "Froid"]

# Fenêtre anti-écho globale à l'entrée : après toute émission, toute réception RF de
# l'entrée est ignorée pendant ce nombre de secondes pour écarter l'écho de notre propre
# émission renvoyé par la passerelle (effet de bord : un appui télécommande physique dans
# cette fenêtre, juste après une commande HA, est ignoré).
ECHO_SUPPRESS_SEC: Final = 1.0


def speed_action(index: int) -> str:
    """Retourner la clé d'action de vitesse pour un index donné."""
    return f"fan_speed_{index}"


def timer_action(hours: int) -> str:
    """Clé d'action pour la minuterie de N heures."""
    return f"timer_{hours}h"
