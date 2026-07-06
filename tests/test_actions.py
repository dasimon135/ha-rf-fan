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
    required, optional = split_actions(speed_count=6, has_light=False)
    assert required == [ACTION_FAN_OFF, *(speed_action(i) for i in range(1, 7))]
    assert ACTION_FAN_ON in optional


def test_split_actions_light_codes_are_optional():
    required, optional = split_actions(speed_count=3, has_light=True)
    for action in (ACTION_LIGHT_ON, ACTION_LIGHT_OFF, ACTION_LIGHT_TOGGLE):
        assert action in optional
        assert action not in required


def test_split_actions_no_light_omits_light_actions():
    required, optional = split_actions(speed_count=3, has_light=False)
    for action in (ACTION_LIGHT_ON, ACTION_LIGHT_OFF, ACTION_LIGHT_TOGGLE):
        assert action not in required
        assert action not in optional


def _speeds(n):
    return {ACTION_FAN_OFF: "c", **{speed_action(i): "c" for i in range(1, n + 1)}}


def test_validate_codes_missing_required_speed():
    required, _ = split_actions(6, has_light=False)
    codes = _speeds(6)
    del codes[speed_action(4)]
    errors = validate_codes(codes, required, has_light=False)
    assert errors == {speed_action(4): "required"}


def test_validate_codes_toggle_only_light_is_valid():
    required, _ = split_actions(6, has_light=True)
    codes = {**_speeds(6), ACTION_LIGHT_TOGGLE: "c"}
    assert validate_codes(codes, required, has_light=True) == {}


def test_validate_codes_light_without_any_code_errors():
    required, _ = split_actions(6, has_light=True)
    errors = validate_codes(_speeds(6), required, has_light=True)
    assert errors == {ACTION_LIGHT_TOGGLE: "light_code_required"}


def test_split_actions_capabilities_off_by_default():
    required, optional = split_actions(6, has_light=False)
    for action in (ACTION_FAN_REVERSE, ACTION_FAN_NATURAL, ACTION_LIGHT_KELVIN,
                   ACTION_SOUND_TOGGLE, timer_action(1)):
        assert action not in required
        assert action not in optional


def test_split_actions_direction_and_preset_required_when_enabled():
    required, _ = split_actions(6, has_light=False, has_direction=True,
                                has_natural_preset=True)
    assert ACTION_FAN_REVERSE in required
    assert ACTION_FAN_NATURAL in required


def test_split_actions_color_temp_and_sound_required_when_enabled():
    required, _ = split_actions(6, has_light=True, has_color_temp=True,
                                has_sound=True)
    assert ACTION_LIGHT_KELVIN in required
    assert ACTION_SOUND_TOGGLE in required


def test_split_actions_timers_add_four_actions():
    required, _ = split_actions(6, has_light=False, has_timers=True)
    for hours in (1, 2, 4, 8):
        assert timer_action(hours) in required


def test_caps_from_data_defaults_false():
    assert caps_from_data({}) == {
        "has_direction": False, "has_natural_preset": False,
        "has_color_temp": False, "has_timers": False, "has_sound": False,
    }


def test_caps_from_data_reads_true():
    assert caps_from_data({"has_direction": True})["has_direction"] is True
