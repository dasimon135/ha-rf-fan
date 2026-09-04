"""Pure RF action selection/validation logic (testable without Home Assistant)."""

from __future__ import annotations

from collections.abc import Iterable

try:  # Home Assistant runtime: relative import within the package
    from .const import (
        ACTION_FAN_NATURAL,
        ACTION_FAN_NATURAL_REVERSE,
        ACTION_FAN_OFF,
        ACTION_FAN_OFF_REVERSE,
        ACTION_FAN_ON,
        ACTION_FAN_REVERSE,
        ACTION_LIGHT_BRIGHT_DOWN,
        ACTION_LIGHT_BRIGHT_UP,
        ACTION_LIGHT_KELVIN,
        ACTION_LIGHT_KELVIN_DOWN,
        ACTION_LIGHT_KELVIN_UP,
        ACTION_LIGHT_OFF,
        ACTION_LIGHT_ON,
        ACTION_LIGHT_TOGGLE,
        ACTION_SOUND_TOGGLE,
        ACTION_TIMER_OFF,
        COLOR_CONTROL_CYCLE,
        COLOR_CONTROL_NONE,
        COLOR_CONTROL_RELATIVE,
        COLOR_TEMP_NAMED,
        CONF_COLOR_TEMP_STEPS,
        CONF_EXTRA_COUNT,
        CONF_EXTRA_NAMES,
        CONF_HAS_TIMER_OFF,
        CONF_HAS_TIMERS,
        CONF_LIGHT_LEVEL_STEPS,
        CONF_TIMER_HOURS,
        DEFAULT_COLOR_TEMP_STEPS,
        DEFAULT_LIGHT_LEVEL_STEPS,
        DIRECTION_CONTROL_NONE,
        DIRECTION_CONTROL_PER_SPEED,
        DIRECTION_CONTROL_TOGGLE,
        LIGHT_CONTROL_ON_OFF,
        LIGHT_CONTROL_TOGGLE,
        LIGHT_LEVEL_NONE,
        LIGHT_LEVEL_RELATIVE,
        MAX_EXTRA_COUNT,
        MAX_STEP_COUNT,
        MIN_STEP_COUNT,
        NATURAL_CONTROL_NONE,
        NATURAL_CONTROL_TOGGLE,
        STEP_DOWN,
        STEP_UP,
        TIMER_HOURS,
        TOGGLE_ACTIONS,
        extra_action,
        speed_action,
        timer_action,
    )
except ImportError:  # pragma: no cover - tests: top-level import via conftest
    from const import (
        ACTION_FAN_NATURAL,
        ACTION_FAN_NATURAL_REVERSE,
        ACTION_FAN_OFF,
        ACTION_FAN_OFF_REVERSE,
        ACTION_FAN_ON,
        ACTION_FAN_REVERSE,
        ACTION_LIGHT_BRIGHT_DOWN,
        ACTION_LIGHT_BRIGHT_UP,
        ACTION_LIGHT_KELVIN,
        ACTION_LIGHT_KELVIN_DOWN,
        ACTION_LIGHT_KELVIN_UP,
        ACTION_LIGHT_OFF,
        ACTION_LIGHT_ON,
        ACTION_LIGHT_TOGGLE,
        ACTION_SOUND_TOGGLE,
        ACTION_TIMER_OFF,
        COLOR_CONTROL_CYCLE,
        COLOR_CONTROL_NONE,
        COLOR_CONTROL_RELATIVE,
        COLOR_TEMP_NAMED,
        CONF_COLOR_TEMP_STEPS,
        CONF_EXTRA_COUNT,
        CONF_EXTRA_NAMES,
        CONF_HAS_TIMER_OFF,
        CONF_HAS_TIMERS,
        CONF_LIGHT_LEVEL_STEPS,
        CONF_TIMER_HOURS,
        DEFAULT_COLOR_TEMP_STEPS,
        DEFAULT_LIGHT_LEVEL_STEPS,
        DIRECTION_CONTROL_NONE,
        DIRECTION_CONTROL_PER_SPEED,
        DIRECTION_CONTROL_TOGGLE,
        LIGHT_CONTROL_ON_OFF,
        LIGHT_CONTROL_TOGGLE,
        LIGHT_LEVEL_NONE,
        LIGHT_LEVEL_RELATIVE,
        MAX_EXTRA_COUNT,
        MAX_STEP_COUNT,
        MIN_STEP_COUNT,
        NATURAL_CONTROL_NONE,
        NATURAL_CONTROL_TOGGLE,
        STEP_DOWN,
        STEP_UP,
        TIMER_HOURS,
        TOGGLE_ACTIONS,
        extra_action,
        speed_action,
        timer_action,
    )


def split_actions(
    speed_count: int,
    light_control: str = "none",
    *,
    has_fan_on: bool = False,
    direction_control: str = DIRECTION_CONTROL_NONE,
    natural_control: str = NATURAL_CONTROL_NONE,
    color_control: str = COLOR_CONTROL_NONE,
    light_level: str = LIGHT_LEVEL_NONE,
    timer_hours: Iterable[int] = (),
    has_timer_off: bool = False,
    has_sound: bool = False,
    extra_count: int = 0,
) -> tuple[list[str], list[str]]:
    """Required actions based on the control style and the declared capabilities.

    Mandatory: `fan_off` + one action per speed, plus the actions for the
    declared capabilities: `fan_on` if `has_fan_on`, the light action(s)
    depending on `light_control` (`toggle` -> `light_toggle`; `on_off` -> `light_on`
    and `light_off`; `none` -> none), then the actions for the enabled capabilities
    (direction, natural airflow, colour, brightness, timers, sound).

    Exactly one action is optional, and only for a `per_speed` remote:
    `fan_off_reverse`. See `const.ACTION_FAN_OFF_REVERSE` for why it exists and why
    it cannot be required — every entry configured before it was added would stop
    validating.

    Four capabilities are selectors rather than booleans, because the remote can
    express them in more than one shape:

    - `direction_control: per_speed` has NO direction key at all. The remote stores
      the mode itself and emits a different speed code per direction, so the reverse
      set is learned alongside the forward one (`fan_speed_N_reverse`) — and, when
      the fan also has the preset, `fan_natural_reverse` beside `fan_natural`.
    - `color_control: relative` and `light_level: relative` have two dedicated keys
      instead of one cycling key, so they take an up/down pair.
    - `natural_control` changes no code at all: `toggle` and `dedicated` learn the
      same keys, and differ only in what a press means (#34). It is a selector
      because the entity behaviour cannot be derived from the codes.
    """
    required = [ACTION_FAN_OFF]
    required.extend(speed_action(index) for index in range(1, speed_count + 1))
    # Kept adjacent to the forward speeds: learning goes key by key down the remote,
    # and the reverse set is the same keys pressed with the internal switch flipped.
    optional: list[str] = []
    if direction_control == DIRECTION_CONTROL_PER_SPEED:
        required.extend(
            speed_action(index, reverse=True) for index in range(1, speed_count + 1)
        )
        # Offered right after the reverse speeds, which is where it sits on the
        # remote: the same off key, pressed with the internal switch flipped.
        optional.append(ACTION_FAN_OFF_REVERSE)
    if has_fan_on:
        required.append(ACTION_FAN_ON)
    if light_control == LIGHT_CONTROL_TOGGLE:
        required.append(ACTION_LIGHT_TOGGLE)
    elif light_control == LIGHT_CONTROL_ON_OFF:
        required.extend([ACTION_LIGHT_ON, ACTION_LIGHT_OFF])
    if direction_control == DIRECTION_CONTROL_TOGGLE:
        required.append(ACTION_FAN_REVERSE)
    if natural_control != NATURAL_CONTROL_NONE:
        required.append(ACTION_FAN_NATURAL)
        # Same reasoning as the reverse speeds, and the same combination: a remote
        # that has no direction key gives its natural-airflow key a code per
        # direction too, so one more key has to be learned — and only here.
        if direction_control == DIRECTION_CONTROL_PER_SPEED:
            required.append(ACTION_FAN_NATURAL_REVERSE)
    if color_control == COLOR_CONTROL_CYCLE:
        required.append(ACTION_LIGHT_KELVIN)
    elif color_control == COLOR_CONTROL_RELATIVE:
        required.extend([ACTION_LIGHT_KELVIN_UP, ACTION_LIGHT_KELVIN_DOWN])
    if light_level == LIGHT_LEVEL_RELATIVE:
        required.extend([ACTION_LIGHT_BRIGHT_UP, ACTION_LIGHT_BRIGHT_DOWN])
    # Each duration stands alone. Demanding all four is what stopped a remote with
    # off/2/4/8 from declaring timers at all (#59); the order comes from TIMER_HOURS
    # so the form and the learning walk never depend on how the user ticked them.
    wanted = set(timer_hours)
    required.extend(timer_action(hours) for hours in TIMER_HOURS if hours in wanted)
    if has_timer_off:
        required.append(ACTION_TIMER_OFF)
    if has_sound:
        required.append(ACTION_SOUND_TOGGLE)
    # Last, and deliberately: these are the keys nothing above could describe.
    required.extend(extra_action(index) for index in range(1, extra_count + 1))
    return required, optional


def transmit_repeat_count(action: str, configured: int) -> int:
    """Number of RF repeats to put on the air for an action.

    Absolute actions (speeds, on/off, timers, one colour step) use the configured
    count as-is: resending the same frame lands the fan in the same state, so more
    repeats only buy reliability.

    Toggle actions flip a state, so the fan has to end up actuated an ODD number of
    times. The two plausible receiver behaviours disagree about what a burst means,
    and an odd count is correct under both: a receiver that debounces the burst
    registers one press whatever the count, and one that treats every frame as a
    press registers a net flip only when the count is odd. So the configured value is
    rounded DOWN to the nearest odd number rather than forced to 1 — a lone frame is
    what some receivers drop outright (issue #15).

    Never returns less than 1: a nonsensical configured value still transmits once.
    """
    count = max(1, int(configured))
    if action in TOGGLE_ACTIONS and count % 2 == 0:
        count -= 1
    return max(1, count)


def validate_codes(
    codes: dict[str, str],
    required: list[str],
    optional: Iterable[str] = (),
) -> dict[str, str]:
    """Return {field: error_key}; empty dict if everything is valid.

    Besides missing codes, a code reused by two actions is rejected: the reverse
    lookup that maps a received frame back to an action compares codes, so a
    duplicate makes one of the two actions unreachable from the physical remote.
    The first action to claim a code keeps it; later ones are flagged.

    An action listed in `optional` may be absent, but if it IS given it takes part
    in the duplicate check like any other — an optional code that collides is worse
    than a missing one, because it silently steals a frame from the action that
    owns it. `required` is scanned first so a required action always wins a tie.

    `required` may already contain the optional actions (the config flow builds one
    combined list for the form); the scan is deduplicated so passing them twice does
    not make an action collide with itself.
    """
    optional_list = list(optional)
    optional_set = set(optional_list)
    errors: dict[str, str] = {}
    seen: set[str] = set()
    for action in dict.fromkeys([*required, *optional_list]):
        code = codes.get(action)
        if not code:
            if action not in optional_set:
                errors[action] = "required"
            continue
        if code in seen:
            errors[action] = "duplicate_code"
            continue
        seen.add(code)
    return errors


def walk_steps(
    current: int | None, target: int, size: int, *, wrap: bool
) -> tuple[str, int]:
    """Plan a walk from `current` to `target` over `size` positions.

    Returns `(direction, steps)` where direction is STEP_UP or STEP_DOWN. Pure
    arithmetic, so the whole stepping mechanism is testable without Home Assistant.

    `wrap` is what separates a cycle from a range:

    - `wrap=True` (a colour cycle) has no end stop, so the shortest path wins in
      either direction. A tie goes up, arbitrarily but consistently.
    - `wrap=False` (a brightness or speed range) clamps at both ends, so the
      direction simply follows the sign of the delta.

    `current is None` means the position was never established — a brand-new entity
    that has not yet restored a state. It is treated as 0 rather than refusing to
    move: a relative control with an unknown position is still usable, it is just
    dead-reckoning from a guess, and the resynchronise button exists to fix it. Every
    entity here already carries `assumed_state`.
    """
    if size <= 1:
        return STEP_UP, 0
    target = max(0, min(size - 1, int(target)))
    position = 0 if current is None else max(0, min(size - 1, int(current)))

    if not wrap:
        delta = target - position
        return (STEP_UP, delta) if delta >= 0 else (STEP_DOWN, -delta)

    forward = (target - position) % size
    backward = size - forward
    if forward and backward < forward:
        return STEP_DOWN, backward
    return STEP_UP, forward


CAPABILITY_FLAGS = (
    "has_timer_off",
    "has_sound",
)

# Capabilities the remote can express in more than one shape, so they are selectors
# rather than booleans. Mapped here with the legacy boolean they replaced, so a dict
# that predates the version-3 migration still resolves to the right value.
CAPABILITY_SELECTORS = (
    ("direction_control", DIRECTION_CONTROL_NONE, "has_direction", DIRECTION_CONTROL_TOGGLE),
    ("color_control", COLOR_CONTROL_NONE, "has_color_temp", COLOR_CONTROL_CYCLE),
    ("light_level", LIGHT_LEVEL_NONE, None, None),
    (
        "natural_control",
        NATURAL_CONTROL_NONE,
        "has_natural_preset",
        NATURAL_CONTROL_TOGGLE,
    ),
)


def timer_hours_from_data(data: dict[str, object]) -> tuple[int, ...]:
    """Sleep-timer durations this remote has a key for, in TIMER_HOURS order.

    Normalised on read rather than trusted, like the step counts: the stored value
    outlives the selector that produced it, and it arrives as strings from a
    multi-select. Anything that is not one of the offered durations is dropped.

    An absent value falls back to the legacy `has_timers` boolean, which meant all
    four -- so an entry that has not been through the version-5 migration keeps the
    timers it already had, and nobody relearns a key. An explicitly EMPTY list is a
    real answer ("no timers") and is never overridden by the boolean.
    """
    raw = data.get(CONF_TIMER_HOURS)
    if raw is None:
        return TIMER_HOURS if bool(data.get(CONF_HAS_TIMERS, False)) else ()
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Iterable):
        return ()
    wanted: set[int] = set()
    for value in raw:
        try:
            wanted.add(int(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
    return tuple(hours for hours in TIMER_HOURS if hours in wanted)


def caps_from_data(data: dict[str, object]) -> dict[str, object]:
    """Extract the capabilities from a config entry dict.

    Booleans default to False and selectors to their "none" value. A selector that
    is absent falls back to the legacy boolean it replaced, so this is correct for
    an entry that has not been through the version-3 migration as well as for one
    that has — the migration is then belt and braces rather than the only guard.
    """
    caps: dict[str, object] = {
        flag: bool(data.get(flag, False)) for flag in CAPABILITY_FLAGS
    }
    caps[CONF_TIMER_HOURS] = timer_hours_from_data(data)
    for name, default, legacy_flag, legacy_value in CAPABILITY_SELECTORS:
        value = data.get(name)
        if isinstance(value, str) and value:
            caps[name] = value
        elif legacy_flag is not None and bool(data.get(legacy_flag, False)):
            caps[name] = legacy_value
        else:
            caps[name] = default
    return caps


def extra_button_count(data: dict[str, object]) -> int:
    """Number of free-form buttons declared for this fan, clamped on read.

    Clamped rather than trusted, like the step counts: the value reaches here from
    stored entry data, which outlives the dropdown that validated it. Anything
    unreadable means none -- a fan with no extra keys is the normal case, and
    inventing one would ask for a code nobody can teach.
    """
    try:
        count = int(data.get(CONF_EXTRA_COUNT, 0))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(0, min(MAX_EXTRA_COUNT, count))


def extra_names(data: dict[str, object]) -> dict[str, str]:
    """Labels for the declared free-form buttons, keyed by action.

    Only the declared ones: a name left behind by a count that shrank describes a
    button that no longer exists.
    """
    stored = data.get(CONF_EXTRA_NAMES)
    stored = stored if isinstance(stored, dict) else {}
    names: dict[str, str] = {}
    for index in range(1, extra_button_count(data) + 1):
        action = extra_action(index)
        label = stored.get(action)
        names[action] = label.strip() if isinstance(label, str) and label.strip() else ""
    return names


def _step_count(data: dict[str, object], key: str, default: int) -> int:
    """Read one declared step count, clamped into the supported range.

    Clamped rather than trusted: the count reaches here from stored entry data,
    which outlives the form that validated it, and every consumer uses it as a
    modulus or a press count. A zero would divide by zero in the brightness
    mapping; a negative would make `walk_steps` plan a walk that never terminates.
    """
    value = data.get(key, default)
    try:
        count = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(MIN_STEP_COUNT, min(MAX_STEP_COUNT, count))


def light_level_steps(data: dict[str, object]) -> int:
    """Number of assumed brightness positions declared for this fan."""
    return _step_count(data, CONF_LIGHT_LEVEL_STEPS, DEFAULT_LIGHT_LEVEL_STEPS)


def color_temp_steps(data: dict[str, object]) -> int:
    """Number of assumed colour positions declared for this fan."""
    return _step_count(data, CONF_COLOR_TEMP_STEPS, DEFAULT_COLOR_TEMP_STEPS)


def color_temp_options(steps: int) -> list[str]:
    """Labels for the colour select's positions.

    Three positions keep the historical names, because those strings are the
    entity's state and renaming them would break automations and history alike.
    Any other count is labelled 1..N: "Warm / Neutral / Cold" describes a three-way
    switch, and a remote with eight positions does not have one — the honest label
    for position five of eight is "5".
    """
    if steps == len(COLOR_TEMP_NAMED):
        return list(COLOR_TEMP_NAMED)
    return [str(position) for position in range(1, steps + 1)]


def expected_unique_ids(entry_id: str, data: dict[str, object]) -> set[str]:
    """Unique ids of every entity a config entry should own, given its capabilities.

    Single source of truth for the entity-registry cleanup: when a capability is
    switched off during a reconfiguration its platform simply stops creating the
    entity, and the registry row would otherwise linger as a permanently
    unavailable ghost. Must be kept in step with the `async_setup_entry` guards
    and the `_attr_unique_id` of each platform.
    """
    caps = caps_from_data(data)
    ids = {f"{entry_id}_fan"}
    ids.update(
        f"{entry_id}_{extra_action(index)}"
        for index in range(1, extra_button_count(data) + 1)
    )
    # light.py defaults `has_light` to True for entries predating the flag.
    if data.get("has_light", True):
        ids.add(f"{entry_id}_light")
        ids.add(f"{entry_id}_light_state")
    if caps["color_control"] != COLOR_CONTROL_NONE:
        ids.add(f"{entry_id}_color_temp")
        ids.add(f"{entry_id}_kelvin_calibrate")
    if caps["light_level"] == LIGHT_LEVEL_RELATIVE:
        ids.add(f"{entry_id}_brightness_position")
        ids.add(f"{entry_id}_brightness_calibrate")
    if data.get("has_sound", False):
        ids.add(f"{entry_id}_sound")
    declared_hours = timer_hours_from_data(data)
    if declared_hours:
        ids.add(f"{entry_id}_sleep_timer")
        ids.update(f"{entry_id}_{timer_action(hours)}" for hours in declared_hours)
    if data.get(CONF_HAS_TIMER_OFF, False):
        ids.add(f"{entry_id}_{ACTION_TIMER_OFF}")
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
