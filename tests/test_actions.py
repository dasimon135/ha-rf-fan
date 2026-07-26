from actions import (
    caps_from_data,
    classify_reconfigure_actions,
    expected_unique_ids,
    split_actions,
    validate_codes,
)
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
    required, _ = split_actions(6, light_control="none", has_direction=True,
                                has_natural_preset=True)
    assert ACTION_FAN_REVERSE in required
    assert ACTION_FAN_NATURAL in required


def test_split_actions_color_temp_and_sound_required_when_enabled():
    required, _ = split_actions(6, light_control="toggle", has_color_temp=True,
                                has_sound=True)
    assert ACTION_LIGHT_KELVIN in required
    assert ACTION_SOUND_TOGGLE in required


def test_split_actions_timers_add_four_actions():
    required, _ = split_actions(6, light_control="none", has_timers=True)
    for hours in (1, 2, 4, 8):
        assert timer_action(hours) in required


def test_caps_from_data_defaults_false():
    assert caps_from_data({}) == {
        "has_direction": False, "has_natural_preset": False,
        "has_color_temp": False, "has_timers": False, "has_sound": False,
    }


def test_caps_from_data_reads_true():
    assert caps_from_data({"has_direction": True})["has_direction"] is True



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


def test_single_shot_actions_cover_relative_actions_only():
    from const import (
        ACTION_FAN_NATURAL,
        ACTION_FAN_ON,
        ACTION_FAN_REVERSE,
        ACTION_LIGHT_KELVIN,
        ACTION_SOUND_TOGGLE,
        SINGLE_SHOT_ACTIONS,
    )

    # Relative / toggle actions must fire exactly once (a repeat would cancel the toggle).
    for relative in (
        ACTION_LIGHT_TOGGLE,
        ACTION_SOUND_TOGGLE,
        ACTION_FAN_REVERSE,
        ACTION_FAN_NATURAL,
    ):
        assert relative in SINGLE_SHOT_ACTIONS

    # Absolute actions keep repeat_count for reliability → NOT single-shot. The colour
    # cycle (kelvin) is also NOT single-shot: the fan debounces a repeat burst into one
    # step, so each step is repeated for reliability and steps are gap-separated.
    for absolute in (
        ACTION_FAN_OFF,
        ACTION_FAN_ON,
        speed_action(1),
        timer_action(4),
        ACTION_LIGHT_KELVIN,
    ):
        assert absolute not in SINGLE_SHOT_ACTIONS


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
    """`has_light` defaults to True, matching light.py's own default."""
    assert expected_unique_ids("e1", {}) == {"e1_fan", "e1_light"}


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
