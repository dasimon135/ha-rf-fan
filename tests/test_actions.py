from actions import split_actions, validate_codes
from const import (
    ACTION_FAN_OFF,
    ACTION_FAN_ON,
    ACTION_LIGHT_OFF,
    ACTION_LIGHT_ON,
    ACTION_LIGHT_TOGGLE,
    speed_action,
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
