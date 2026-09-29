"""Timer keys pressed on the physical remote are followed (#86).

The fan, the light, the colour select and the sound switch all follow the remote;
the sleep timer did not. Pressing `2h` on the remote started the fan's countdown
and the sensor stayed empty; pressing the cancel key left a switch-off time on
display -- and since #85, a timer cancelled from the remote switched the fan
"off" in Home Assistant while it was still running.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.ha_helpers import button_id, fire_rf, one_id, setup_full

TIMER_OFF = {
    "extra_codes": {"timer_off": "c_toff"},
    "extra_data": {"has_timer_off": True},
}


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


def _ends_at(hass: HomeAssistant):
    state = hass.states.get(one_id(hass, "sensor")).state
    return dt_util.parse_datetime(state)


def _to_second(moment):
    """A timestamp sensor's state is written to the second."""
    return moment.replace(microsecond=0)


async def _run_at(hass: HomeAssistant, fan_id: str, percentage: int) -> None:
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": percentage}, blocking=True
    )
    await hass.async_block_till_done()


async def _move_on(hass: HomeAssistant, freezer, delta: timedelta) -> None:
    future = dt_util.utcnow() + delta
    freezer.move_to(future)
    async_fire_time_changed(hass, future)
    await hass.async_block_till_done()


async def test_a_timer_key_on_the_remote_sets_the_switch_off_time(
    hass: HomeAssistant, freezer
) -> None:
    """The reported gap: `2h` on the remote, and the sensor stayed empty."""
    await setup_full(hass)
    before = dt_util.utcnow()

    await fire_rf(hass, "c_t2")

    assert _ends_at(hass) == _to_second(before + timedelta(hours=2))


async def test_the_cancel_key_on_the_remote_clears_the_switch_off_time(
    hass: HomeAssistant, freezer
) -> None:
    """A timer set from Home Assistant, cancelled from the remote."""
    entry, _calls = await setup_full(hass, **TIMER_OFF)
    await hass.services.async_call(
        "button", "press", {"entity_id": button_id(hass, "4h")}, blocking=True
    )
    await hass.async_block_till_done()
    assert _ends_at(hass) is not None
    # Close the echo window of our own transmission, so the next frame is a press.
    entry.runtime_data.echo_codes.clear()

    await fire_rf(hass, "c_toff")

    assert hass.states.get(one_id(hass, "sensor")).state == "unknown"


async def test_a_timer_cancelled_from_the_remote_does_not_stop_the_fan(
    hass: HomeAssistant, freezer
) -> None:
    """Since #85 the fan follows the timer; a cancelled one must not switch it off."""
    await setup_full(hass, **TIMER_OFF)
    fan_id = one_id(hass, "fan")
    await _run_at(hass, fan_id, 67)
    await fire_rf(hass, "c_t1")
    await fire_rf(hass, "c_toff")

    await _move_on(hass, freezer, timedelta(hours=1, minutes=1))

    state = hass.states.get(fan_id)
    assert state.state == "on"
    assert state.attributes.get("percentage") == 67


async def test_a_timer_set_from_the_remote_stops_the_fan_when_it_elapses(
    hass: HomeAssistant, freezer
) -> None:
    """The other half of #85: a remote timer is a timer like any other."""
    _entry, calls = await setup_full(hass)
    fan_id = one_id(hass, "fan")
    await _run_at(hass, fan_id, 67)
    await fire_rf(hass, "c_t1")
    sent = len(calls)

    await _move_on(hass, freezer, timedelta(hours=1, minutes=1))

    assert hass.states.get(fan_id).state == "off"
    assert len(calls) == sent, "hearing a key transmits nothing"


async def test_a_repeated_frame_does_not_restart_the_countdown(
    hass: HomeAssistant, freezer
) -> None:
    """One press is several frames on the air; the deadline is set by the first.

    The de-bounce runs on `hass.loop.time()`, which the frozen clock does not move,
    so the second frame is a repeat; the wall clock moves, so a restart would show.
    """
    await setup_full(hass)
    before = dt_util.utcnow()
    await fire_rf(hass, "c_t2")

    await _move_on(hass, freezer, timedelta(seconds=5))
    await fire_rf(hass, "c_t2")

    assert _ends_at(hass) == _to_second(before + timedelta(hours=2))


async def test_a_timer_key_heard_by_another_gateway_is_ignored(hass: HomeAssistant) -> None:
    """Same YAML on a neighbouring node: its frames are not this fan's."""
    await setup_full(hass)

    await fire_rf(hass, "c_t2", device="esp32-elsewhere")

    assert hass.states.get(one_id(hass, "sensor")).state == "unknown"


async def test_our_own_timer_frame_coming_back_is_not_a_second_press(
    hass: HomeAssistant, freezer
) -> None:
    """The echo of Home Assistant's own `2h` must not be read as a new press.

    The echo window runs on `hass.loop.time()` and is still open; the wall clock
    moves, so a restarted countdown would show.
    """
    await setup_full(hass)
    await hass.services.async_call(
        "button", "press", {"entity_id": button_id(hass, "2h")}, blocking=True
    )
    await hass.async_block_till_done()
    first = _ends_at(hass)

    await _move_on(hass, freezer, timedelta(seconds=5))
    await fire_rf(hass, "c_t2")

    assert _ends_at(hass) == first
