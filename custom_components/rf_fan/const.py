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

# Toggle actions: each press FLIPS a state (the light, the sound, the direction, the
# natural preset) instead of setting one. The fan must therefore end up actuated an ODD
# number of times, which is what `actions.transmit_repeat_count` enforces: it rounds the
# configured repeat_count down to the nearest odd value for these, and leaves absolute
# actions (speeds, timers, on/off) alone.
#
# Why odd rather than exactly once, which is what this used to do: the two plausible
# receiver behaviours disagree about a burst, and odd is correct under both. A receiver
# that debounces a repeat burst registers a single press whatever the count. One that
# treats every frame as a separate press registers a net flip only when the count is odd.
# Forcing 1 was safe under both too, but it left nothing for a noisy link or a receiver
# that simply ignores a lone frame — see issue #15, where light_toggle never reached the
# lamp while fan_on did, on the same hardware and the same code shape.
#
# NOTE: the colour cycle (ACTION_LIGHT_KELVIN) is deliberately NOT in here. It is a
# relative action, but the select walks to a target by sending N discrete steps
# (see select.py), and each of those steps needs the full repeat_count for reliability;
# distinct steps are separated by KELVIN_STEP_GAP_SEC.
TOGGLE_ACTIONS: Final = frozenset(
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

# Anti-echo window: the gateway sniffs its own transmissions, so every code we send
# comes back as a reception a moment later. For this number of seconds after sending a
# code, receptions OF THAT SAME CODE are discarded. Matching per code (rather than
# muting all reception) means a press of a different remote button right after a Home
# Assistant command is still honoured. Remaining side effect: pressing on the remote the
# very button Home Assistant just triggered, within the window, is ignored — the window
# is sized to cover a slow gateway rather than to be minimal, because the alternative
# (a late echo) silently flips the toggle actions back.
ECHO_SUPPRESS_SEC: Final = 2.0


def speed_action(index: int) -> str:
    """Return the speed action key for a given index."""
    return f"fan_speed_{index}"


def timer_action(hours: int) -> str:
    """Action key for the N-hour timer."""
    return f"timer_{hours}h"
