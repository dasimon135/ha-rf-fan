"""When the sleep timer runs out, the fan has switched itself off (#85).

The timer sensor already cleared its switch-off time at that moment, and nothing
told the fan entity: Home Assistant went on showing the fan running at its last
speed, for as long as nothing else corrected it.

The timer is itself a belief -- a timer cancelled from a remote Home Assistant
cannot hear would make "off" wrong. But a timer that elapsed is by far the common
case, and the one a person sets a timer for, so the fan follows it.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.ha_helpers import button_id, one_id, setup_full


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


async def _run_at(hass: HomeAssistant, fan_id: str, percentage: int) -> None:
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": percentage}, blocking=True
    )
    await hass.async_block_till_done()


async def _press_timer(hass: HomeAssistant, label: str) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": button_id(hass, label)}, blocking=True
    )
    await hass.async_block_till_done()


async def _move_on(hass: HomeAssistant, freezer, delta: timedelta) -> None:
    future = dt_util.utcnow() + delta
    freezer.move_to(future)
    async_fire_time_changed(hass, future)
    await hass.async_block_till_done()


async def test_the_fan_is_off_when_its_timer_elapses(hass: HomeAssistant, freezer) -> None:
    """The reported gap: the timer ran out, and the fan still read `on` at 67 %."""
    _entry, calls = await setup_full(hass)
    fan_id = one_id(hass, "fan")
    await _run_at(hass, fan_id, 67)
    await _press_timer(hass, "1h")
    sent = len(calls)

    await _move_on(hass, freezer, timedelta(hours=1, minutes=1))

    state = hass.states.get(fan_id)
    assert state.state == "off"
    assert state.attributes.get("percentage") == 0
    assert len(calls) == sent, "the fan switched itself off: nothing goes on the air"


async def test_the_fan_runs_on_until_the_timer_is_reached(hass: HomeAssistant, freezer) -> None:
    """Not early: half-way through, the fan is still running."""
    await setup_full(hass)
    fan_id = one_id(hass, "fan")
    await _run_at(hass, fan_id, 67)
    await _press_timer(hass, "2h")

    await _move_on(hass, freezer, timedelta(hours=1))

    assert hass.states.get(fan_id).state == "on"


async def test_a_timer_cleared_by_switching_off_does_not_stop_the_fan_later(
    hass: HomeAssistant, freezer
) -> None:
    """Off then on again ends the timer on the fan too; its old deadline means nothing."""
    await setup_full(hass)
    fan_id = one_id(hass, "fan")
    await _run_at(hass, fan_id, 67)
    await _press_timer(hass, "1h")
    await hass.services.async_call("fan", "turn_off", {"entity_id": fan_id}, blocking=True)
    await _run_at(hass, fan_id, 33)

    await _move_on(hass, freezer, timedelta(hours=1, minutes=1))

    state = hass.states.get(fan_id)
    assert state.state == "on"
    assert state.attributes.get("percentage") == 33
