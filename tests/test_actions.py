from actions import split_actions
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
