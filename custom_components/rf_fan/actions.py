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
    """Return {field: error_key}; empty dict if everything is valid.

    Besides missing codes, a code reused by two actions is rejected: the reverse
    lookup that maps a received frame back to an action compares codes, so a
    duplicate makes one of the two actions unreachable from the physical remote.
    The first action to claim a code keeps it; later ones are flagged.
    """
    errors: dict[str, str] = {}
    seen: set[str] = set()
    for action in required:
        code = codes.get(action)
        if not code:
            errors[action] = "required"
            continue
        if code in seen:
            errors[action] = "duplicate_code"
            continue
        seen.add(code)
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


def expected_unique_ids(entry_id: str, data: dict[str, object]) -> set[str]:
    """Unique ids of every entity a config entry should own, given its capabilities.

    Single source of truth for the entity-registry cleanup: when a capability is
    switched off during a reconfiguration its platform simply stops creating the
    entity, and the registry row would otherwise linger as a permanently
    unavailable ghost. Must be kept in step with the `async_setup_entry` guards
    and the `_attr_unique_id` of each platform.
    """
    ids = {f"{entry_id}_fan"}
    # light.py defaults `has_light` to True for entries predating the flag.
    if data.get("has_light", True):
        ids.add(f"{entry_id}_light")
    if data.get("has_color_temp", False):
        ids.add(f"{entry_id}_color_temp")
        ids.add(f"{entry_id}_kelvin_calibrate")
    if data.get("has_sound", False):
        ids.add(f"{entry_id}_sound")
    if data.get("has_timers", False):
        ids.add(f"{entry_id}_sleep_timer")
        ids.update(f"{entry_id}_{timer_action(hours)}" for hours in TIMER_HOURS)
    return ids


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


def pick_best_code(frames: list[str]) -> str | None:
    """Pick the most frequently repeated captured code.

    A real remote press repeats the same frame (especially when the button is held
    briefly), while ambient 433 MHz noise produces random, non-repeating frames.
    Returning the modal frame filters out that noise. Ties break to the earliest
    frame seen. Returns None if no frames were captured.
    """
    if not frames:
        return None
    counts: dict[str, int] = {}
    for frame in frames:
        counts[frame] = counts.get(frame, 0) + 1
    best: str | None = None
    best_count = 0
    for frame in frames:
        if counts[frame] > best_count:
            best = frame
            best_count = counts[frame]
    return best
