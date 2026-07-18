"""Constants for the generic RF fan integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "rf_fan"

EVENT_RF_FAN_RECEIVED: Final = "esphome.rf_fan_received"

CONF_ESPHOME_DEVICE: Final = "esphome_device"
# Raw ESPHome service prefix (e.g. "rf_fan_gateway" for the service
# esphome.rf_fan_gateway_transmit_rf_fan). Captured at config-flow time from the
# live service registry; CONF_ESPHOME_DEVICE keeps the prettified (dashed)
# display name. Entries created before v2 are migrated with a best-effort guess.
CONF_GATEWAY_SERVICE: Final = "gateway_service"
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
# Option: skip auto-loading the bundled Lovelace card (global effect: the card
# is registered once for the whole frontend, so any entry opting out disables
# the auto-load; a restart is required for a change to take effect).
CONF_DISABLE_CARD: Final = "disable_card"

DEFAULT_SPEED_COUNT: Final = 3
DEFAULT_REPEAT_COUNT: Final = 2

ACTION_FAN_ON: Final = "fan_on"
ACTION_FAN_OFF: Final = "fan_off"
ACTION_LIGHT_ON: Final = "light_on"
ACTION_LIGHT_OFF: Final = "light_off"
ACTION_LIGHT_TOGGLE: Final = "light_toggle"

# Capabilities (config flow)
CONF_HAS_DIRECTION: Final = "has_direction"
CONF_HAS_NATURAL_PRESET: Final = "has_natural_preset"
CONF_HAS_COLOR_TEMP: Final = "has_color_temp"
CONF_HAS_TIMERS: Final = "has_timers"
CONF_HAS_SOUND: Final = "has_sound"

# New actions
ACTION_FAN_REVERSE: Final = "fan_reverse"
ACTION_FAN_NATURAL: Final = "fan_natural"
ACTION_LIGHT_KELVIN: Final = "light_kelvin"
ACTION_SOUND_TOGGLE: Final = "sound_toggle"
TIMER_HOURS: Final = (1, 2, 4, 8)

# Relative/toggle actions that must fire EXACTLY once. Each press flips a state
# (toggle the light or sound, flip direction or the natural preset). The fan debounces
# a rapid repeat burst into a single actuation, so replaying such a code repeat_count>1
# times would double-actuate and cancel the toggle back out. These always transmit once,
# regardless of the configured repeat_count. Absolute actions (speeds, timers, on/off)
# keep repeat_count for reliability.
#
# NOTE: the colour cycle (ACTION_LIGHT_KELVIN) is deliberately NOT single-shot. The fan
# debounces a repeat burst into a single colour step (exactly as it does for a speed
# press), so each step is sent with repeat_count for reliability; distinct steps are
# separated by KELVIN_STEP_GAP_SEC so the receiver registers them as separate presses
# (see select.py).
SINGLE_SHOT_ACTIONS: Final = frozenset(
    {
        ACTION_LIGHT_TOGGLE,
        ACTION_SOUND_TOGGLE,
        ACTION_FAN_REVERSE,
        ACTION_FAN_NATURAL,
    }
)

# Natural airflow preset
PRESET_NORMAL: Final = "normal"
PRESET_NATURAL: Final = "natural"

# Color positions (kelvin select): hardware cycle order
COLOR_TEMP_OPTIONS: Final = ["Chaud", "Neutre", "Froid"]

# Pause (seconds) between successive colour-cycle steps so a debouncing receiver
# registers each as a separate press. A rapid burst with no gap merges into one step.
KELVIN_STEP_GAP_SEC: Final = 0.4

# Global per-entry anti-echo window: after any transmission, all RF reception for the
# entry is ignored for this number of seconds to discard the echo of our own transmission
# sent back by the gateway (side effect: a physical remote press within this window, just
# after an HA command, is ignored).
ECHO_SUPPRESS_SEC: Final = 1.0


def speed_action(index: int) -> str:
    """Return the speed action key for a given index."""
    return f"fan_speed_{index}"


def timer_action(hours: int) -> str:
    """Action key for the N-hour timer."""
    return f"timer_{hours}h"
