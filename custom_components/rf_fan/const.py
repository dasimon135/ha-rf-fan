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

# Speed-count bounds. The old cap of 6 had no technical reason behind it: a remote
# with more speeds is only more tedious to learn, not harder to drive. Widened for
# the 9-speed remotes reported on the forum.
MIN_SPEED_COUNT: Final = 2
MAX_SPEED_COUNT: Final = 12

ACTION_FAN_ON: Final = "fan_on"
ACTION_FAN_OFF: Final = "fan_off"
ACTION_LIGHT_ON: Final = "light_on"
ACTION_LIGHT_OFF: Final = "light_off"
ACTION_LIGHT_TOGGLE: Final = "light_toggle"

# Capabilities (config flow)
CONF_HAS_NATURAL_PRESET: Final = "has_natural_preset"
CONF_HAS_TIMERS: Final = "has_timers"
CONF_HAS_SOUND: Final = "has_sound"

# Legacy booleans, replaced by the selectors below in entry version 3. Kept because
# the migration still has to read them, and because `caps_from_data` falls back to
# them for any dict that has not been through the migration (tests, diagnostics).
CONF_HAS_DIRECTION: Final = "has_direction"
CONF_HAS_COLOR_TEMP: Final = "has_color_temp"

# How the remote controls the rotation direction.
#   none      - no direction control at all
#   toggle    - one `fan_reverse` key that flips the direction (dead-reckoned)
#   per_speed - no direction key: the remote stores the mode and sends a DIFFERENT
#               speed code per direction, so the direction is a dimension of the
#               speed code set. Twice the codes to learn, but the direction becomes
#               ABSOLUTE instead of dead-reckoned (reported on issue #18).
CONF_DIRECTION_CONTROL: Final = "direction_control"
DIRECTION_CONTROL_NONE: Final = "none"
DIRECTION_CONTROL_TOGGLE: Final = "toggle"
DIRECTION_CONTROL_PER_SPEED: Final = "per_speed"
DIRECTION_CONTROL_OPTIONS: Final = [
    DIRECTION_CONTROL_NONE,
    DIRECTION_CONTROL_TOGGLE,
    DIRECTION_CONTROL_PER_SPEED,
]

# How the remote controls the colour temperature.
#   none     - no colour control
#   cycle    - one key that walks the positions in a fixed loop (wraps)
#   relative - two dedicated keys, warmer and cooler, that clamp at each end
CONF_COLOR_CONTROL: Final = "color_control"
COLOR_CONTROL_NONE: Final = "none"
COLOR_CONTROL_CYCLE: Final = "cycle"
COLOR_CONTROL_RELATIVE: Final = "relative"
COLOR_CONTROL_OPTIONS: Final = [
    COLOR_CONTROL_NONE,
    COLOR_CONTROL_CYCLE,
    COLOR_CONTROL_RELATIVE,
]

# How the remote controls the light brightness.
#   none     - the light is on/off only (ColorMode.ONOFF)
#   relative - two dedicated keys, brighter and dimmer (ColorMode.BRIGHTNESS)
CONF_LIGHT_LEVEL: Final = "light_level"
LIGHT_LEVEL_NONE: Final = "none"
LIGHT_LEVEL_RELATIVE: Final = "relative"
LIGHT_LEVEL_OPTIONS: Final = [LIGHT_LEVEL_NONE, LIGHT_LEVEL_RELATIVE]

# Number of assumed brightness positions modelled for `light_level: relative`.
#
# The remote's ± keys walk an unknown number of hardware levels and the lamp never
# reports back, so the count is ours to pick: a position is simply "how many presses
# up from the bottom". Ten gives a slider that feels continuous while keeping a full
# resynchronisation to nine presses. Picking fewer than the hardware has means the
# top of the slider never reaches full brightness; picking more means the last few
# presses do nothing (harmless — the lamp clamps). Ten is a starting point to be
# confirmed against real hardware, not a measured value.
LIGHT_LEVEL_STEPS: Final = 10

# New actions
ACTION_FAN_REVERSE: Final = "fan_reverse"
ACTION_FAN_NATURAL: Final = "fan_natural"
ACTION_LIGHT_KELVIN: Final = "light_kelvin"
ACTION_LIGHT_KELVIN_UP: Final = "light_kelvin_up"
ACTION_LIGHT_KELVIN_DOWN: Final = "light_kelvin_down"
ACTION_LIGHT_BRIGHT_UP: Final = "light_bright_up"
ACTION_LIGHT_BRIGHT_DOWN: Final = "light_bright_down"
ACTION_SOUND_TOGGLE: Final = "sound_toggle"
TIMER_HOURS: Final = (1, 2, 4, 8)

# Walk directions returned by `actions.walk_steps`.
STEP_UP: Final = "up"
STEP_DOWN: Final = "down"

# Walk axes. Two walks on the SAME axis cancel each other (restart semantics); two
# walks on different axes run side by side, since colour and brightness are separate
# controls on the remote and pressing one does not disturb the other.
AXIS_COLOR: Final = "color"
AXIS_LEVEL: Final = "level"

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
# NOTE: none of the stepping actions (the colour cycle ACTION_LIGHT_KELVIN, and the
# ± pairs for colour and brightness) is in here. A step is absolute, not a flip: it
# moves the value one notch in a known direction, so resending the same frame lands
# in the same place. The walk reaches a target by sending N discrete steps (see
# `entity._async_walk`), and each of those steps needs the full repeat_count for
# reliability. What makes a receiver count them as separate presses is STEP_GAP_SEC,
# not the repeat count.
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

# Pause (seconds) between successive steps of a walk (colour, brightness) so a
# debouncing receiver registers each as a separate press. A rapid burst with no gap
# merges into a single step.
STEP_GAP_SEC: Final = 0.4
# Historical name, kept so an external reference to it does not break.
KELVIN_STEP_GAP_SEC: Final = STEP_GAP_SEC

# Anti-echo window: the gateway sniffs its own transmissions, so every code we send
# comes back as a reception a moment later. For this number of seconds after sending a
# code, receptions OF THAT SAME CODE are discarded. Matching per code (rather than
# muting all reception) means a press of a different remote button right after a Home
# Assistant command is still honoured. Remaining side effect: pressing on the remote the
# very button Home Assistant just triggered, within the window, is ignored — the window
# is sized to cover a slow gateway rather than to be minimal, because the alternative
# (a late echo) silently flips the toggle actions back.
ECHO_SUPPRESS_SEC: Final = 2.0


def speed_action(index: int, *, reverse: bool = False) -> str:
    """Return the speed action key for a given index.

    With `direction_control: per_speed` the remote emits a different code per
    direction, so the reverse set gets its own keys. The forward keys keep their
    historical names (`fan_speed_1`…) so no learned code is invalidated.
    """
    return f"fan_speed_{index}_reverse" if reverse else f"fan_speed_{index}"


def timer_action(hours: int) -> str:
    """Action key for the N-hour timer."""
    return f"timer_{hours}h"
