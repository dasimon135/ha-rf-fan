from actions import (
    caps_from_data,
    classify_reconfigure_actions,
    color_temp_options,
    color_temp_steps,
    expected_unique_ids,
    extra_button_count,
    light_level_steps,
    split_actions,
    timer_hours_from_data,
    transmit_repeat_count,
    validate_codes,
    walk_steps,
)
from const import (
    ACTION_FAN_NATURAL,
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
    COLOR_TEMP_NAMED,
    DEFAULT_COLOR_TEMP_STEPS,
    DEFAULT_LIGHT_LEVEL_STEPS,
    MAX_EXTRA_COUNT,
    MAX_STEP_COUNT,
    MIN_STEP_COUNT,
    STEP_DOWN,
    STEP_UP,
    speed_action,
    timer_action,
)


def test_split_actions_fan_off_and_speeds_required():
    required, optional = split_actions(speed_count=6, light_control="none")
    assert required == [ACTION_FAN_OFF, *(speed_action(i) for i in range(1, 7))]
    assert optional == []


def test_split_light_none_has_no_light_action():
    required, optional = split_actions(6, light_control="none")
    for a in (ACTION_LIGHT_ON, ACTION_LIGHT_OFF, ACTION_LIGHT_TOGGLE):
        assert a not in required and a not in optional


def test_split_light_toggle_requires_only_toggle():
    required, _ = split_actions(6, light_control="toggle")
    assert ACTION_LIGHT_TOGGLE in required
    assert ACTION_LIGHT_ON not in required and ACTION_LIGHT_OFF not in required


def test_split_light_on_off_requires_on_and_off():
    required, _ = split_actions(6, light_control="on_off")
    assert ACTION_LIGHT_ON in required and ACTION_LIGHT_OFF in required
    assert ACTION_LIGHT_TOGGLE not in required


def test_fan_off_reverse_is_optional_and_only_for_per_speed():
    """The only optional action there is, and only on the remote that has one."""
    for control in ("none", "toggle"):
        required, optional = split_actions(
            6, light_control="none", direction_control=control
        )
        assert ACTION_FAN_OFF_REVERSE not in required
        assert ACTION_FAN_OFF_REVERSE not in optional

    required, optional = split_actions(
        6, light_control="none", direction_control="per_speed"
    )
    assert optional == [ACTION_FAN_OFF_REVERSE]
    assert ACTION_FAN_OFF_REVERSE not in required


def test_validate_codes_accepts_a_missing_optional_action():
    """An entry configured before `fan_off_reverse` existed must still validate."""
    required, optional = split_actions(
        2, light_control="none", direction_control="per_speed"
    )
    codes = {action: f"c_{action}" for action in required}
    assert validate_codes(codes, required, optional=optional) == {}
    # ...and the flow passes one combined list, which must not make the optional
    # action collide with itself.
    assert validate_codes(codes, [*required, *optional], optional=optional) == {}


def test_validate_codes_still_rejects_a_duplicate_optional_code():
    """Optional means "may be absent", never "may steal another action's frame"."""
    required, optional = split_actions(
        2, light_control="none", direction_control="per_speed"
    )
    codes = {action: f"c_{action}" for action in required}
    codes[ACTION_FAN_OFF_REVERSE] = codes[ACTION_FAN_OFF]
    errors = validate_codes(codes, [*required, *optional], optional=optional)
    assert errors == {ACTION_FAN_OFF_REVERSE: "duplicate_code"}


def test_validate_codes_optional_defaults_to_none():
    """Every existing caller passes two arguments and must keep its old meaning."""
    required, optional = split_actions(
        2, light_control="none", direction_control="per_speed"
    )
    codes = {action: f"c_{action}" for action in required}
    assert validate_codes(codes, [*required, *optional]) == {
        ACTION_FAN_OFF_REVERSE: "required"
    }


def test_split_fan_on_only_when_declared():
    req_no, opt_no = split_actions(6, light_control="none")
    assert ACTION_FAN_ON not in req_no and ACTION_FAN_ON not in opt_no
    req_yes, _ = split_actions(6, light_control="none", has_fan_on=True)
    assert ACTION_FAN_ON in req_yes


def _speeds(n):
    """Codes for fan_off + n speeds. Distinct, as a real entry always is: a code
    reused by two actions is itself a validation error (`duplicate_code`)."""
    return {
        ACTION_FAN_OFF: "c_off",
        **{speed_action(i): f"c_s{i}" for i in range(1, n + 1)},
    }


def test_validate_codes_missing_required_speed():
    required, _ = split_actions(6, light_control="none")
    codes = _speeds(6)
    del codes[speed_action(4)]
    errors = validate_codes(codes, required)
    assert errors == {speed_action(4): "required"}


def test_validate_codes_no_special_light_rule():
    required, _ = split_actions(6, light_control="toggle")
    codes = _speeds(6)
    errors = validate_codes(codes, required)
    assert errors.get(ACTION_LIGHT_TOGGLE) == "required"


def test_split_actions_capabilities_off_by_default():
    required, optional = split_actions(6, light_control="none")
    for action in (ACTION_FAN_REVERSE, ACTION_FAN_NATURAL, ACTION_LIGHT_KELVIN,
                   ACTION_SOUND_TOGGLE, timer_action(1)):
        assert action not in required
        assert action not in optional


def test_split_actions_direction_and_preset_required_when_enabled():
    required, _ = split_actions(6, light_control="none", direction_control="toggle",
                                natural_control="toggle")
    assert ACTION_FAN_REVERSE in required
    assert ACTION_FAN_NATURAL in required


def test_split_actions_asks_for_the_airflow_key_whatever_the_shape():
    """`toggle` and `dedicated` press the same key; they differ in what a press means."""
    for shape in ("toggle", "dedicated"):
        required, _ = split_actions(6, light_control="none", natural_control=shape)
        assert ACTION_FAN_NATURAL in required

    required, _ = split_actions(6, light_control="none", natural_control="none")
    assert ACTION_FAN_NATURAL not in required


def test_split_actions_color_temp_and_sound_required_when_enabled():
    required, _ = split_actions(6, light_control="toggle", color_control="cycle",
                                has_sound=True)
    assert ACTION_LIGHT_KELVIN in required
    assert ACTION_SOUND_TOGGLE in required


def test_an_extra_key_is_counted_as_a_toggle():
    """Its effect is unknowable, and the two mistakes are not symmetric.

    Odd repeats of an absolute code land where even repeats would. Even repeats of
    a real toggle net zero flips, and the button looks dead with nothing to see.
    """
    assert transmit_repeat_count("extra_1", 4) == 3
    assert transmit_repeat_count("extra_8", 2) == 1


def test_split_actions_asks_for_one_code_per_extra_key():
    """A free-form key is a code and a name; the code is all `split_actions` knows."""
    required, _ = split_actions(3, light_control="none", extra_count=2)

    assert "extra_1" in required
    assert "extra_2" in required
    assert "extra_3" not in required


def test_split_actions_without_extra_keys_asks_for_none():
    required, _ = split_actions(3, light_control="none", extra_count=0)

    assert [action for action in required if action.startswith("extra_")] == []


def test_extra_button_count_is_clamped_on_read():
    """Stored data outlives the dropdown that validated it, so it is never trusted.

    The cap is not only prudence: every reachable action must carry a label in
    three translation files, which an unbounded count could not satisfy.
    """
    assert extra_button_count({"extra_count": 3}) == 3
    assert extra_button_count({}) == 0
    assert extra_button_count({"extra_count": 99}) == MAX_EXTRA_COUNT
    assert extra_button_count({"extra_count": -1}) == 0
    assert extra_button_count({"extra_count": "two"}) == 0


def test_extra_keys_own_one_registry_row_each():
    ids = expected_unique_ids("e1", {"has_light": False, "extra_count": 2})

    assert ids == {"e1_fan", "e1_extra_1", "e1_extra_2"}


def test_shrinking_the_count_gives_up_the_last_row_only():
    """The count is a length, never a renumbering.

    Reassigning a learned code to a different button is the worst defect this
    feature could have, and nothing in the interface would report it.
    """
    three = expected_unique_ids("e1", {"has_light": False, "extra_count": 3})
    two = expected_unique_ids("e1", {"has_light": False, "extra_count": 2})

    assert three - two == {"e1_extra_3"}


def test_split_actions_timers_add_one_action_per_declared_duration():
    required, _ = split_actions(6, light_control="none", timer_hours=(1, 2, 4, 8))
    for hours in (1, 2, 4, 8):
        assert timer_action(hours) in required


def test_split_actions_timers_are_individually_optional():
    """A remote with off/2/4/8 could not declare timers at all before (#59)."""
    required, _ = split_actions(6, light_control="none", timer_hours=(2, 4, 8))
    assert timer_action(1) not in required
    for hours in (2, 4, 8):
        assert timer_action(hours) in required


def test_split_actions_timer_order_follows_the_menu_not_the_selection():
    """The learning walk must not depend on the order the boxes were ticked."""
    required, _ = split_actions(6, light_control="none", timer_hours=[8, 1, 4])
    timers = [a for a in required if a.startswith("timer_")]
    assert timers == [timer_action(1), timer_action(4), timer_action(8)]


def test_split_actions_timer_off_only_when_declared():
    required, _ = split_actions(6, light_control="none", timer_hours=(2,))
    assert ACTION_TIMER_OFF not in required
    required, _ = split_actions(
        6, light_control="none", timer_hours=(2,), has_timer_off=True
    )
    assert ACTION_TIMER_OFF in required


def test_timer_hours_reads_the_legacy_boolean():
    """`has_timers: True` meant all four; an unmigrated entry must keep them."""
    assert timer_hours_from_data({"has_timers": True}) == (1, 2, 4, 8)
    assert timer_hours_from_data({"has_timers": False}) == ()
    assert timer_hours_from_data({}) == ()


def test_timer_hours_explicit_empty_beats_the_legacy_boolean():
    """An explicit answer outranks the boolean it replaced, even when empty."""
    assert timer_hours_from_data({"timer_hours": [], "has_timers": True}) == ()


def test_timer_hours_normalises_what_the_multi_select_stores():
    """Strings from the selector, out of order, with an impossible value in it."""
    assert timer_hours_from_data({"timer_hours": ["8", "2", "99"]}) == (2, 8)
    assert timer_hours_from_data({"timer_hours": "nonsense"}) == ()
    assert timer_hours_from_data({"timer_hours": 4}) == ()


def test_caps_from_data_defaults_off():
    assert caps_from_data({}) == {
        "has_timer_off": False, "has_sound": False, "timer_hours": (),
        "direction_control": "none", "color_control": "none", "light_level": "none",
        "natural_control": "none",
    }


def test_caps_from_data_reads_true():
    assert caps_from_data({"has_timer_off": True})["has_timer_off"] is True
    # The legacy boolean still resolves, so an unmigrated entry keeps its timers.
    assert caps_from_data({"has_timers": True})["timer_hours"] == (1, 2, 4, 8)


def test_caps_feed_split_actions_directly():
    """`split_actions(**caps)` is how the flow calls it: the keys must line up."""
    caps = caps_from_data({"timer_hours": ["2", "8"], "has_timer_off": True})
    required, _ = split_actions(2, light_control="none", **caps)
    assert timer_action(2) in required and timer_action(8) in required
    assert timer_action(1) not in required
    assert ACTION_TIMER_OFF in required


def test_caps_from_data_reads_the_selectors():
    caps = caps_from_data(
        {"direction_control": "per_speed", "color_control": "relative",
         "light_level": "relative"}
    )
    assert caps["direction_control"] == "per_speed"
    assert caps["color_control"] == "relative"
    assert caps["light_level"] == "relative"


def test_caps_from_data_falls_back_to_the_legacy_booleans():
    """An entry that has not been through the v3 migration still resolves.

    The migration rewrites the booleans into selectors, but `caps_from_data` is
    also handed raw dicts (diagnostics, tests, a half-migrated entry), so the
    fallback is the guard rather than the migration being the only one.
    """
    caps = caps_from_data({"has_direction": True, "has_color_temp": True})
    assert caps["direction_control"] == "toggle"
    assert caps["color_control"] == "cycle"


def test_caps_from_data_selector_wins_over_the_legacy_boolean():
    caps = caps_from_data({"has_direction": True, "direction_control": "per_speed"})
    assert caps["direction_control"] == "per_speed"



def test_classify_all_kept_when_codes_complete():
    required = [ACTION_FAN_OFF, speed_action(1), ACTION_LIGHT_TOGGLE]
    existing = {ACTION_FAN_OFF: "a", speed_action(1): "b", ACTION_LIGHT_TOGGLE: "c"}
    to_learn, kept, forgotten = classify_reconfigure_actions(required, existing)
    assert to_learn == []
    assert kept == [ACTION_FAN_OFF, speed_action(1), ACTION_LIGHT_TOGGLE]
    assert forgotten == []


def test_classify_new_required_without_code_goes_to_learn():
    required = [ACTION_FAN_OFF, timer_action(1), timer_action(2)]
    existing = {ACTION_FAN_OFF: "a"}
    to_learn, kept, forgotten = classify_reconfigure_actions(required, existing)
    assert to_learn == [timer_action(1), timer_action(2)]
    assert kept == [ACTION_FAN_OFF]
    assert forgotten == []


def test_classify_forgotten_action_dropped():
    required = [ACTION_FAN_OFF]
    existing = {ACTION_FAN_OFF: "a", ACTION_LIGHT_TOGGLE: "old"}
    to_learn, kept, forgotten = classify_reconfigure_actions(required, existing)
    assert to_learn == []
    assert kept == [ACTION_FAN_OFF]
    assert forgotten == [ACTION_LIGHT_TOGGLE]


def test_classify_empty_code_counts_as_missing():
    required = [ACTION_FAN_OFF, speed_action(1)]
    existing = {ACTION_FAN_OFF: "a", speed_action(1): ""}
    to_learn, kept, _forgotten = classify_reconfigure_actions(required, existing)
    assert to_learn == [speed_action(1)]
    assert kept == [ACTION_FAN_OFF]


def test_classify_preserves_required_order():
    required = [ACTION_FAN_OFF, speed_action(1), speed_action(2), ACTION_LIGHT_TOGGLE]
    existing = {speed_action(1): "b", ACTION_LIGHT_TOGGLE: "c"}
    to_learn, kept, _forgotten = classify_reconfigure_actions(required, existing)
    assert to_learn == [ACTION_FAN_OFF, speed_action(2)]
    assert kept == [speed_action(1), ACTION_LIGHT_TOGGLE]


def test_toggle_actions_cover_flipping_actions_only():
    from const import (
        ACTION_FAN_NATURAL,
        ACTION_FAN_ON,
        ACTION_FAN_REVERSE,
        ACTION_LIGHT_KELVIN,
        ACTION_SOUND_TOGGLE,
        TOGGLE_ACTIONS,
    )

    # Actions that FLIP a state: their repeat count has to stay odd.
    for toggle in (
        ACTION_LIGHT_TOGGLE,
        ACTION_SOUND_TOGGLE,
        ACTION_FAN_REVERSE,
        ACTION_FAN_NATURAL,
    ):
        assert toggle in TOGGLE_ACTIONS

    # Absolute actions keep repeat_count untouched. The colour cycle (kelvin) is also
    # NOT a toggle: the select walks to a target by sending N discrete steps, each of
    # which is repeated for reliability and gap-separated from the next.
    for absolute in (
        ACTION_FAN_OFF,
    ACTION_FAN_OFF_REVERSE,
        ACTION_FAN_ON,
        speed_action(1),
        timer_action(4),
        ACTION_LIGHT_KELVIN,
    ):
        assert absolute not in TOGGLE_ACTIONS


def test_pick_best_code_none_for_empty():
    from actions import pick_best_code

    assert pick_best_code([]) is None


def test_pick_best_code_single_frame():
    from actions import pick_best_code

    assert pick_best_code(["raw:1,-2,3"]) == "raw:1,-2,3"


def test_pick_best_code_modal_wins_over_noise():
    from actions import pick_best_code

    frames = ["real", "noise-a", "real", "noise-b", "real"]
    assert pick_best_code(frames) == "real"


def test_pick_best_code_tie_breaks_to_earliest():
    from actions import pick_best_code

    assert pick_best_code(["a", "b"]) == "a"


def test_expected_unique_ids_minimal_entry():
    """A speeds-only fan owns just the fan entity."""
    ids = expected_unique_ids("e1", {"has_light": False})
    assert ids == {"e1_fan"}


def test_expected_unique_ids_light_is_on_by_default():
    """`has_light` defaults to True, matching light.py's own default.

    A light brings two rows: the entity itself, and the select that declares what
    state it is believed to be in (#45).
    """
    assert expected_unique_ids("e1", {}) == {"e1_fan", "e1_light", "e1_light_state"}


def test_expected_unique_ids_color_temp_adds_select_and_calibrate():
    ids = expected_unique_ids("e1", {"has_light": False, "has_color_temp": True})
    assert ids == {"e1_fan", "e1_color_temp", "e1_kelvin_calibrate"}


def test_expected_unique_ids_timers_add_sensor_and_one_button_per_delay():
    ids = expected_unique_ids("e1", {"has_light": False, "has_timers": True})
    assert ids == {
        "e1_fan",
        "e1_sleep_timer",
        "e1_timer_1h",
        "e1_timer_2h",
        "e1_timer_4h",
        "e1_timer_8h",
    }


def test_expected_unique_ids_sound_adds_the_switch():
    ids = expected_unique_ids("e1", {"has_light": False, "has_sound": True})
    assert ids == {"e1_fan", "e1_sound"}


def test_validate_codes_flags_a_code_reused_by_two_actions():
    """Two actions sharing one code make the reverse lookup ambiguous.

    `_event_action` maps a received frame back to an action by comparing codes, so
    a duplicate silently makes one of the two actions unreachable from the remote.
    The first occurrence is kept; the later one is flagged.
    """
    errors = validate_codes(
        {"fan_off": "AAA", "fan_speed_1": "AAA"}, ["fan_off", "fan_speed_1"]
    )
    assert errors == {"fan_speed_1": "duplicate_code"}


def test_validate_codes_missing_wins_over_duplicate():
    """A blank field is reported as missing, never as a duplicate."""
    errors = validate_codes(
        {"fan_off": "AAA", "fan_speed_1": "", "fan_speed_2": "AAA"},
        ["fan_off", "fan_speed_1", "fan_speed_2"],
    )
    assert errors == {"fan_speed_1": "required", "fan_speed_2": "duplicate_code"}


def test_validate_codes_accepts_all_distinct_codes():
    errors = validate_codes(
        {"fan_off": "A", "fan_speed_1": "B"}, ["fan_off", "fan_speed_1"]
    )
    assert errors == {}


def test_the_default_never_gives_a_toggle_a_lone_frame():
    """The invariant the old default of 2 broke, in both directions.

    `transmit_repeat_count` rounds an even count down to odd for toggles, so an even
    default of 2 sent ONE frame — exactly what its own docstring says some receivers
    drop outright (#15). And @Ltek's fan needed three (#59). Both are satisfied only
    by an odd default of at least 3, so assert the property rather than the number:
    changing DEFAULT_REPEAT_COUNT to something even would silently reintroduce this.
    """
    from const import ACTION_LIGHT_TOGGLE, DEFAULT_REPEAT_COUNT

    toggle = transmit_repeat_count(ACTION_LIGHT_TOGGLE, DEFAULT_REPEAT_COUNT)
    absolute = transmit_repeat_count(ACTION_FAN_OFF, DEFAULT_REPEAT_COUNT)

    assert toggle % 2 == 1, "a toggle must net exactly one flip"
    assert toggle >= 3, "a lone frame is what some receivers drop (#15)"
    assert absolute >= 3, "the only fan ever measured needed three (#59)"


def test_toggle_repeat_count_rounds_down_to_odd():
    """A toggle must end up actuated an odd number of times.

    A receiver that debounces a burst registers one press whatever the count; one
    that treats every frame as a press registers a net flip only for an odd count.
    Rounding down to the nearest odd value is correct under both.
    """
    from actions import transmit_repeat_count

    for toggle in (
        ACTION_LIGHT_TOGGLE,
        ACTION_SOUND_TOGGLE,
        ACTION_FAN_REVERSE,
        ACTION_FAN_NATURAL,
    ):
        assert transmit_repeat_count(toggle, 2) == 1
        assert transmit_repeat_count(toggle, 4) == 3
        assert transmit_repeat_count(toggle, 5) == 5
        assert transmit_repeat_count(toggle, 1) == 1


def test_absolute_repeat_count_is_untouched():
    """Absolute actions keep the configured count: resending lands the same state."""
    from actions import transmit_repeat_count

    for absolute in (
        ACTION_FAN_OFF,
    ACTION_FAN_OFF_REVERSE,
        ACTION_FAN_ON,
        speed_action(1),
        timer_action(4),
        ACTION_LIGHT_KELVIN,
    ):
        for configured in (1, 2, 3, 4, 5):
            assert transmit_repeat_count(absolute, configured) == configured


def test_repeat_count_never_below_one():
    """A nonsensical configured value still puts exactly one frame on the air."""
    from actions import transmit_repeat_count

    assert transmit_repeat_count(ACTION_LIGHT_TOGGLE, 0) == 1
    assert transmit_repeat_count(ACTION_LIGHT_TOGGLE, -3) == 1
    assert transmit_repeat_count(ACTION_FAN_OFF, 0) == 1


# --- Relative controls (v1.9.0) ------------------------------------------------


def test_speed_action_reverse_keys_are_distinct():
    """`per_speed` learns a second code set; the forward names must not change.

    The forward keys are what every existing entry already stores, so renaming
    them would invalidate every learned code (see the migration note in §5 of the
    design doc).
    """
    assert speed_action(3) == "fan_speed_3"
    assert speed_action(3, reverse=True) == "fan_speed_3_reverse"


def test_split_actions_per_speed_learns_both_code_sets():
    required, _ = split_actions(6, light_control="none", direction_control="per_speed")
    for index in range(1, 7):
        assert speed_action(index) in required
        assert speed_action(index, reverse=True) in required
    # No direction key at all: the remote stores the mode itself.
    assert ACTION_FAN_REVERSE not in required


def test_split_actions_per_speed_does_not_ask_for_a_reverse_key():
    """`toggle` and `per_speed` are alternatives, never both."""
    toggled, _ = split_actions(3, light_control="none", direction_control="toggle")
    assert ACTION_FAN_REVERSE in toggled
    assert speed_action(1, reverse=True) not in toggled


def test_split_actions_direction_none_learns_only_forward_speeds():
    required, _ = split_actions(3, light_control="none", direction_control="none")
    assert required == [ACTION_FAN_OFF, *(speed_action(i) for i in range(1, 4))]


def test_split_actions_color_relative_takes_a_key_pair():
    required, _ = split_actions(3, light_control="toggle", color_control="relative")
    assert ACTION_LIGHT_KELVIN_UP in required
    assert ACTION_LIGHT_KELVIN_DOWN in required
    # The single cycling key belongs to the other shape, not to this one.
    assert ACTION_LIGHT_KELVIN not in required


def test_split_actions_brightness_relative_takes_a_key_pair():
    required, _ = split_actions(3, light_control="toggle", light_level="relative")
    assert ACTION_LIGHT_BRIGHT_UP in required
    assert ACTION_LIGHT_BRIGHT_DOWN in required


def test_split_actions_brightness_absent_by_default():
    required, _ = split_actions(3, light_control="toggle")
    assert ACTION_LIGHT_BRIGHT_UP not in required
    assert ACTION_LIGHT_BRIGHT_DOWN not in required


def test_split_actions_inspire_aruba_plus_full_shape():
    """The remote from issue #18, end to end.

    6 speeds with a second reverse set behind the remote's internal switch, a
    toggling light, and ± pairs for colour and brightness: 12 + 1 + 1 + 2 + 2 = 18.
    """
    required, _ = split_actions(
        6,
        light_control="toggle",
        direction_control="per_speed",
        color_control="relative",
        light_level="relative",
    )
    assert len(required) == 18
    assert len(set(required)) == 18


def test_expected_unique_ids_brightness_adds_position_and_calibrate():
    ids = expected_unique_ids("e1", {"light_level": "relative"})
    assert ids == {
        "e1_fan",
        "e1_light",
        "e1_light_state",
        "e1_brightness_position",
        "e1_brightness_calibrate",
    }


def test_expected_unique_ids_color_relative_owns_the_same_entities_as_cycle():
    """The colour select and its calibrate button exist in both shapes.

    Only the codes behind them differ, so switching a fan from `cycle` to
    `relative` must not orphan a registry row (the 1.6.0 ghost-entity bug).
    """
    cycle = expected_unique_ids("e1", {"has_light": False, "color_control": "cycle"})
    relative = expected_unique_ids("e1", {"has_light": False, "color_control": "relative"})
    assert cycle == relative == {"e1_fan", "e1_color_temp", "e1_kelvin_calibrate"}


def test_expected_unique_ids_drops_brightness_when_switched_off():
    assert "e1_brightness_position" not in expected_unique_ids("e1", {"light_level": "none"})


def test_walk_clamped_range_goes_up_by_the_delta():
    assert walk_steps(2, 7, 10, wrap=False) == (STEP_UP, 5)


def test_walk_clamped_range_goes_down_by_the_delta():
    assert walk_steps(7, 2, 10, wrap=False) == (STEP_DOWN, 5)


def test_walk_clamped_range_emits_nothing_when_already_there():
    assert walk_steps(4, 4, 10, wrap=False) == (STEP_UP, 0)


def test_walk_clamps_a_target_past_the_end():
    """The caller maps 0-255 onto positions, so a rounding overshoot is expected."""
    assert walk_steps(0, 99, 10, wrap=False) == (STEP_UP, 9)


def test_walk_clamps_a_negative_target():
    assert walk_steps(5, -3, 10, wrap=False) == (STEP_DOWN, 5)


def test_walk_cycle_takes_the_short_way_round():
    """Three colours: 0 -> 2 is one step DOWN, not two up."""
    assert walk_steps(0, 2, 3, wrap=True) == (STEP_DOWN, 1)


def test_walk_cycle_goes_up_when_that_is_shorter():
    assert walk_steps(0, 1, 3, wrap=True) == (STEP_UP, 1)


def test_walk_cycle_wraps_past_the_end():
    assert walk_steps(2, 0, 3, wrap=True) == (STEP_UP, 1)


def test_walk_cycle_breaks_an_exact_tie_upwards():
    """Four positions, half a turn away: both directions cost 2. Ties go up."""
    assert walk_steps(0, 2, 4, wrap=True) == (STEP_UP, 2)


def test_walk_unknown_position_is_treated_as_the_bottom():
    """A brand-new entity has no restored position but must still move.

    Dead-reckoning from a guess is what the resynchronise button exists to fix;
    refusing to move would make the control look broken instead of assumed.
    """
    assert walk_steps(None, 3, 10, wrap=False) == (STEP_UP, 3)
    assert walk_steps(None, 2, 3, wrap=True) == (STEP_DOWN, 1)


def test_walk_single_position_never_emits():
    assert walk_steps(0, 0, 1, wrap=False) == (STEP_UP, 0)
    assert walk_steps(None, 5, 1, wrap=True) == (STEP_UP, 0)


def test_color_temp_options_keep_the_named_positions_at_three():
    """The three-way labels are the entity's state; renaming them breaks automations."""
    assert color_temp_options(3) == COLOR_TEMP_NAMED


def test_color_temp_options_are_numbered_at_any_other_count():
    """"Warm / Neutral / Cold" describes a three-way switch, and eight is not one."""
    assert color_temp_options(8) == ["1", "2", "3", "4", "5", "6", "7", "8"]
    assert color_temp_options(2) == ["1", "2"]


def test_step_counts_fall_back_for_an_entry_that_predates_them():
    """An entry created before the counts existed keeps the behaviour it had."""
    assert color_temp_steps({}) == DEFAULT_COLOR_TEMP_STEPS
    assert light_level_steps({}) == DEFAULT_LIGHT_LEVEL_STEPS


def test_step_counts_are_clamped_into_the_supported_range():
    """Stored data outlives the form that validated it, and every consumer divides by it."""
    assert light_level_steps({"light_level_steps": 0}) == MIN_STEP_COUNT
    assert light_level_steps({"light_level_steps": -4}) == MIN_STEP_COUNT
    assert color_temp_steps({"color_temp_steps": 999}) == MAX_STEP_COUNT


def test_step_counts_survive_a_value_that_is_not_a_number():
    """A corrupted entry falls back rather than raising during setup."""
    assert light_level_steps({"light_level_steps": "eight"}) == DEFAULT_LIGHT_LEVEL_STEPS
    assert color_temp_steps({"color_temp_steps": None}) == DEFAULT_COLOR_TEMP_STEPS


def test_a_declared_count_is_read_back():
    """@elmr91's fan: eight of each, measured on the hardware (issue #18)."""
    data = {"color_temp_steps": 8, "light_level_steps": 8}
    assert color_temp_steps(data) == 8
    assert light_level_steps(data) == 8
