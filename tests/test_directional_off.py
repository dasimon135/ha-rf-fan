"""Stopping a `per_speed` fan from reverse (#59, measured by @Ltek).

A remote with a speed code per direction puts the direction in every frame it
sends, its off key included. Stopping a reversed fan with the forward off code
does stop it, but leaves the receiver storing "forward" while Home Assistant still
shows reverse — so the next speed code starts it the wrong way round.

`fan_off_reverse` is the fix, and it is OPTIONAL: the fallback to `fan_off` is what
keeps every entry configured before it working unchanged, which is most of the
coverage below.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.components.fan import ATTR_DIRECTION
from homeassistant.core import HomeAssistant

from custom_components.rf_fan.const import ACTION_FAN_OFF, ACTION_FAN_OFF_REVERSE
from tests.ha_helpers import actions_sent, fire_rf, one_id, setup_relative

REVERSE_OFF = {ACTION_FAN_OFF_REVERSE: "r_offr"}


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def _face(hass: HomeAssistant, fan: str, direction: str) -> None:
    """Put the fan in a known direction before stopping it."""
    await hass.services.async_call(
        "fan",
        "set_direction",
        {"entity_id": fan, ATTR_DIRECTION: direction},
        blocking=True,
    )


async def _turn_off(hass: HomeAssistant, fan: str) -> None:
    await hass.services.async_call(
        "fan", "turn_off", {"entity_id": fan}, blocking=True
    )


async def test_stopping_from_reverse_uses_the_reverse_off_code(
    hass: HomeAssistant,
) -> None:
    """The whole point: the frame that stops the fan also names the direction."""
    _entry, calls = await setup_relative(hass, extra_codes=REVERSE_OFF)
    fan = one_id(hass, "fan")

    await _face(hass, fan, "reverse")
    calls.clear()
    await _turn_off(hass, fan)

    assert actions_sent(calls) == [ACTION_FAN_OFF_REVERSE]
    assert hass.states.get(fan).state == "off"


async def test_stopping_from_forward_still_uses_the_plain_off_code(
    hass: HomeAssistant,
) -> None:
    """Declaring the reverse key must not change what forward does."""
    _entry, calls = await setup_relative(hass, extra_codes=REVERSE_OFF)
    fan = one_id(hass, "fan")

    await _face(hass, fan, "forward")
    calls.clear()
    await _turn_off(hass, fan)

    assert actions_sent(calls) == [ACTION_FAN_OFF]


async def test_a_remote_without_the_reverse_off_key_falls_back(
    hass: HomeAssistant,
) -> None:
    """An entry configured before this existed sends exactly what it always did.

    This is the compatibility guarantee the optional action was designed around:
    no code, no error, no missing transmission — just `fan_off`.
    """
    _entry, calls = await setup_relative(hass)
    fan = one_id(hass, "fan")

    await _face(hass, fan, "reverse")
    calls.clear()
    await _turn_off(hass, fan)

    assert actions_sent(calls) == [ACTION_FAN_OFF]
    assert hass.states.get(fan).state == "off"


async def test_hearing_the_reverse_off_key_records_the_direction(
    hass: HomeAssistant,
) -> None:
    """Both off keys name their direction, so hearing one is an ABSOLUTE reading."""
    _entry, _calls = await setup_relative(hass, extra_codes=REVERSE_OFF)
    fan = one_id(hass, "fan")

    await _face(hass, fan, "forward")
    await fire_rf(hass, "r_offr")

    state = hass.states.get(fan)
    assert state.state == "off"
    assert state.attributes[ATTR_DIRECTION] == "reverse"


async def test_hearing_the_plain_off_key_records_forward_only_with_the_pair(
    hass: HomeAssistant,
) -> None:
    """With `fan_off` alone the frame carries no direction, so none is invented."""
    _entry, _calls = await setup_relative(hass, extra_codes=REVERSE_OFF)
    fan = one_id(hass, "fan")
    await _face(hass, fan, "reverse")
    await fire_rf(hass, "r_off")
    assert hass.states.get(fan).attributes[ATTR_DIRECTION] == "forward"

    # ...and now the same remote WITHOUT the reverse off key: the direction it was
    # left in must survive, because nothing in the frame contradicts it.
    _entry2, _calls2 = await setup_relative(hass)
    fans = [e for e in hass.states.async_entity_ids("fan") if e != fan]
    plain = fans[0]
    await _face(hass, plain, "reverse")
    await fire_rf(hass, "r_off")
    assert hass.states.get(plain).attributes[ATTR_DIRECTION] == "reverse"
