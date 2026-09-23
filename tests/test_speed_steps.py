"""`fan.increase_speed` and `fan.decrease_speed`, called the way scripts call them.

With no `percentage_step` in the call, Home Assistant plans the next speed from
the entity's `speed_count`. The fan never set it, so it read Home Assistant's
default of 100 and every call re-sent the speed the fan was already at: a wall
switch wired to "one notch faster" did nothing at all.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant

from tests.ha_helpers import actions_sent, one_id, setup_full

SIX_SPEEDS = {f"fan_speed_{i}": f"c_s{i}" for i in range(4, 7)}


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def _six_speed_fan(hass: HomeAssistant):
    _entry, calls = await setup_full(
        hass, extra_codes=SIX_SPEEDS, extra_data={"speed_count": 6}
    )
    return one_id(hass, "fan"), calls


async def _at_speed(hass: HomeAssistant, fan_id: str, calls: list, speed: int) -> None:
    await hass.services.async_call(
        "fan",
        "set_percentage",
        {"entity_id": fan_id, "percentage": round(speed * 100 / 6)},
        blocking=True,
    )
    calls.clear()


@pytest.mark.parametrize("speed", range(1, 6))
async def test_increase_speed_moves_one_notch_up(hass: HomeAssistant, speed: int) -> None:
    fan_id, calls = await _six_speed_fan(hass)
    await _at_speed(hass, fan_id, calls, speed)

    await hass.services.async_call(
        "fan", "increase_speed", {"entity_id": fan_id}, blocking=True
    )

    assert actions_sent(calls) == [f"fan_speed_{speed + 1}"]
    assert hass.states.get(fan_id).attributes["percentage"] == round((speed + 1) * 100 / 6)


@pytest.mark.parametrize("speed", range(2, 7))
async def test_decrease_speed_moves_one_notch_down(hass: HomeAssistant, speed: int) -> None:
    fan_id, calls = await _six_speed_fan(hass)
    await _at_speed(hass, fan_id, calls, speed)

    await hass.services.async_call(
        "fan", "decrease_speed", {"entity_id": fan_id}, blocking=True
    )

    assert actions_sent(calls) == [f"fan_speed_{speed - 1}"]
    assert hass.states.get(fan_id).attributes["percentage"] == round((speed - 1) * 100 / 6)


async def test_decrease_from_the_lowest_speed_turns_the_fan_off(hass: HomeAssistant) -> None:
    """What Home Assistant does for every fan: one notch below the bottom is off."""
    fan_id, calls = await _six_speed_fan(hass)
    await _at_speed(hass, fan_id, calls, 1)

    await hass.services.async_call(
        "fan", "decrease_speed", {"entity_id": fan_id}, blocking=True
    )

    assert actions_sent(calls) == ["fan_off"]
    assert hass.states.get(fan_id).state == "off"


async def test_increase_from_off_starts_at_the_lowest_speed(hass: HomeAssistant) -> None:
    fan_id, calls = await _six_speed_fan(hass)

    await hass.services.async_call(
        "fan", "increase_speed", {"entity_id": fan_id}, blocking=True
    )

    assert actions_sent(calls) == ["fan_speed_1"]
    assert hass.states.get(fan_id).state == "on"


async def test_an_explicit_step_is_still_honoured(hass: HomeAssistant) -> None:
    """`percentage_step` in the call keeps Home Assistant's own arithmetic."""
    fan_id, calls = await _six_speed_fan(hass)
    await _at_speed(hass, fan_id, calls, 1)

    await hass.services.async_call(
        "fan",
        "increase_speed",
        {"entity_id": fan_id, "percentage_step": 50},
        blocking=True,
    )

    assert actions_sent(calls) == ["fan_speed_4"]
