"""Sleep-timer button + sensor behaviour (requires a Home Assistant environment).

The fan gives no feedback, so the switch-off time is a local estimate: pressing a
timer button records `now + N hours`. The sensor must therefore clear itself when
that moment arrives — nothing else will refresh it.
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


async def test_timer_button_records_the_switch_off_time(hass: HomeAssistant) -> None:
    """Pressing the 1h button publishes a switch-off time about an hour ahead."""
    await setup_full(hass)
    sensor_id = one_id(hass, "sensor")

    await hass.services.async_call(
        "button", "press", {"entity_id": button_id(hass, "1h")}, blocking=True
    )
    await hass.async_block_till_done()

    state = hass.states.get(sensor_id)
    assert state.state not in ("unknown", "unavailable")
    recorded = dt_util.parse_datetime(state.state)
    assert timedelta(minutes=59) < recorded - dt_util.utcnow() <= timedelta(hours=1)


async def test_timer_sensor_clears_itself_when_it_expires(
    hass: HomeAssistant, freezer
) -> None:
    """Once the switch-off time is reached the sensor must go back to unknown."""
    await setup_full(hass)
    sensor_id = one_id(hass, "sensor")

    await hass.services.async_call(
        "button", "press", {"entity_id": button_id(hass, "1h")}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(sensor_id).state not in ("unknown", "unavailable")

    future = dt_util.utcnow() + timedelta(hours=1, minutes=1)
    freezer.move_to(future)
    async_fire_time_changed(hass, future)
    await hass.async_block_till_done()

    assert hass.states.get(sensor_id).state == "unknown"


async def test_turning_the_fan_off_clears_the_timer(hass: HomeAssistant) -> None:
    """Switching the fan off cancels the assumed sleep timer."""
    await setup_full(hass)
    sensor_id = one_id(hass, "sensor")
    fan_id = one_id(hass, "fan")

    await hass.services.async_call(
        "button", "press", {"entity_id": button_id(hass, "2h")}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(sensor_id).state not in ("unknown", "unavailable")

    await hass.services.async_call(
        "fan", "turn_off", {"entity_id": fan_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.states.get(sensor_id).state == "unknown"


async def test_timer_is_not_recorded_when_the_code_is_missing(
    hass: HomeAssistant,
) -> None:
    """An unmapped timer code sends nothing, so no switch-off time may be claimed."""
    entry, _calls = await setup_full(hass)
    sensor_id = one_id(hass, "sensor")

    codes = dict(entry.data["codes"])
    codes.pop("timer_4h")
    hass.config_entries.async_update_entry(entry, data={**entry.data, "codes": codes})
    # Entities cache their code map at init; reload so they pick the change up
    # (this is what `async_update_reload_and_abort` does after a reconfiguration).
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "button", "press", {"entity_id": button_id(hass, "4h")}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.states.get(sensor_id).state == "unknown"
