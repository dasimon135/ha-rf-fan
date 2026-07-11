from actions import caps_from_data, split_actions, validate_codes
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
    return {ACTION_FAN_OFF: "c", **{speed_action(i): "c" for i in range(1, n + 1)}}


def test_validate_codes_missing_required_speed():
    required, _ = split_actions(6, light_control="none")
    codes = _speeds(6)
    del codes[speed_action(4)]
    errors = validate_codes(codes, required)
    assert errors == {speed_action(4): "required"}


def test_validate_codes_no_special_light_rule():
    required, _ = split_actions(6, light_control="toggle")
    codes = {ACTION_FAN_OFF: "c", **{speed_action(i): "c" for i in range(1, 7)}}
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


from actions import classify_reconfigure_actions
from const import ACTION_FAN_OFF, ACTION_LIGHT_TOGGLE, speed_action, timer_action


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
    to_learn, kept, forgotten = classify_reconfigure_actions(required, existing)
    assert to_learn == [speed_action(1)]
    assert kept == [ACTION_FAN_OFF]


def test_classify_preserves_required_order():
    required = [ACTION_FAN_OFF, speed_action(1), speed_action(2), ACTION_LIGHT_TOGGLE]
    existing = {speed_action(1): "b", ACTION_LIGHT_TOGGLE: "c"}
    to_learn, kept, forgotten = classify_reconfigure_actions(required, existing)
    assert to_learn == [ACTION_FAN_OFF, speed_action(2)]
    assert kept == [speed_action(1), ACTION_LIGHT_TOGGLE]
