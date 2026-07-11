"""Pure RF action selection/validation logic (testable without Home Assistant)."""

from __future__ import annotations

try:  # Home Assistant runtime: relative import within the package
    from .const import (
        ACTION_FAN_NATURAL,
        ACTION_FAN_OFF,
        ACTION_FAN_ON,
        ACTION_FAN_REVERSE,
        ACTION_LIGHT_KELVIN,
        ACTION_LIGHT_OFF,
        ACTION_LIGHT_ON,
        ACTION_LIGHT_TOGGLE,
        ACTION_SOUND_TOGGLE,
        LIGHT_CONTROL_ON_OFF,
        LIGHT_CONTROL_TOGGLE,
        TIMER_HOURS,
        speed_action,
        timer_action,
    )
except ImportError:  # pragma: no cover - tests: top-level import via conftest
    from const import (
        ACTION_FAN_NATURAL,
        ACTION_FAN_OFF,
        ACTION_FAN_ON,
        ACTION_FAN_REVERSE,
        ACTION_LIGHT_KELVIN,
        ACTION_LIGHT_OFF,
        ACTION_LIGHT_ON,
        ACTION_LIGHT_TOGGLE,
        ACTION_SOUND_TOGGLE,
        LIGHT_CONTROL_ON_OFF,
        LIGHT_CONTROL_TOGGLE,
        TIMER_HOURS,
        speed_action,
        timer_action,
    )


def split_actions(
    speed_count: int,
    light_control: str = "none",
    *,
    has_fan_on: bool = False,
    has_direction: bool = False,
    has_natural_preset: bool = False,
    has_color_temp: bool = False,
    has_timers: bool = False,
    has_sound: bool = False,
) -> tuple[list[str], list[str]]:
    """Required actions based on the control style and the declared capabilities.

    Mandatory: `fan_off` + one action per speed, plus the actions for the
    declared capabilities: `fan_on` if `has_fan_on`, the light action(s)
    depending on `light_control` (`toggle` -> `light_toggle`; `on_off` -> `light_on`
    and `light_off`; `none` -> none), then the actions for the enabled capabilities
    (reverse, natural airflow, kelvin color, timers, sound).
    No optional action: the returned list is always empty.
    """
    required = [ACTION_FAN_OFF]
    required.extend(speed_action(index) for index in range(1, speed_count + 1))
    if has_fan_on:
        required.append(ACTION_FAN_ON)
    if light_control == LIGHT_CONTROL_TOGGLE:
        required.append(ACTION_LIGHT_TOGGLE)
    elif light_control == LIGHT_CONTROL_ON_OFF:
        required.extend([ACTION_LIGHT_ON, ACTION_LIGHT_OFF])
    if has_direction:
        required.append(ACTION_FAN_REVERSE)
    if has_natural_preset:
        required.append(ACTION_FAN_NATURAL)
    if has_color_temp:
        required.append(ACTION_LIGHT_KELVIN)
    if has_timers:
        required.extend(timer_action(hours) for hours in TIMER_HOURS)
    if has_sound:
        required.append(ACTION_SOUND_TOGGLE)
    return required, []


def validate_codes(codes: dict[str, str], required: list[str]) -> dict[str, str]:
    """Return {field: error_key}; empty dict if everything is valid."""
    errors: dict[str, str] = {}
    for action in required:
        if not codes.get(action):
            errors[action] = "required"
    return errors


CAPABILITY_FLAGS = (
    "has_direction",
    "has_natural_preset",
    "has_color_temp",
    "has_timers",
    "has_sound",
)


def caps_from_data(data: dict[str, object]) -> dict[str, bool]:
    """Extract the capabilities from a config entry dict (default False)."""
    return {flag: bool(data.get(flag, False)) for flag in CAPABILITY_FLAGS}


def classify_reconfigure_actions(
    required: list[str], existing_codes: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """Split the actions for a reconfiguration.

    - to_learn: required with no existing code (newly required).
    - kept: required that already have a code (kept).
    - forgotten: coded but no longer required (to be removed).
    Order: to_learn/kept follow `required`; forgotten follows `existing_codes`.
    """
    to_learn = [a for a in required if not existing_codes.get(a)]
    kept = [a for a in required if existing_codes.get(a)]
    forgotten = [a for a in existing_codes if a not in required]
    return to_learn, kept, forgotten
