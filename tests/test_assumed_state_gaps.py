"""Places where the assumed state and the frames on the air could part ways.

Found by reading, in the September 2026 review, rather than reported: none of
them had a test, and each one leaves Home Assistant showing a state the hardware
is not in -- which on a device that never reports back is the only kind of bug
there is.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.core import HomeAssistant

from tests.ha_helpers import actions_sent, fire_rf, id_by_unique_suffix, one_id
from tests.ha_helpers import setup_full, setup_relative


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


# --- A second gateway in range ------------------------------------------------


async def test_another_gateways_frame_does_not_swallow_our_own(
    hass: HomeAssistant,
) -> None:
    """Two gateways hear the same press; ours must still count when it comes second.

    Both run the same YAML, so both report the same code string. The de-bounce is
    keyed on the code, and it used to be consulted before the frame's origin was:
    the neighbour's copy opened the window, and ours fell inside it as a "repeat".
    """
    await setup_full(hass)
    fan_id = one_id(hass, "fan")

    await fire_rf(hass, "c_s2", device="some-other-gateway")
    await fire_rf(hass, "c_s2")

    state = hass.states.get(fan_id)
    assert state.state == "on"
    assert state.attributes["percentage"] == 67


# --- fan.turn_on on a remote with no `fan_on` key ------------------------------


async def test_turn_on_while_running_resends_the_speed_it_shows(
    hass: HomeAssistant,
) -> None:
    """Without a `fan_on` key the fallback is a speed key -- the CURRENT one.

    It used to be speed 1 whatever the fan was doing, while the percentage was only
    touched when it read zero: a fan running at full speed dropped to its lowest
    and Home Assistant went on showing 100 %.
    """
    _entry, calls = await setup_full(hass)
    fan_id = one_id(hass, "fan")
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 100}, blocking=True
    )
    calls.clear()

    await hass.services.async_call("fan", "turn_on", {"entity_id": fan_id}, blocking=True)
    await hass.async_block_till_done()

    assert actions_sent(calls) == ["fan_speed_3"]
    assert hass.states.get(fan_id).attributes["percentage"] == 100


async def test_turn_on_by_speed_key_leaves_a_dedicated_preset(
    hass: HomeAssistant,
) -> None:
    """A speed key ends a `dedicated` preset (#34) -- on the fallback path as well."""
    _entry, calls = await setup_relative(hass, natural_control="dedicated")
    fan_id = one_id(hass, "fan")
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 67}, blocking=True
    )
    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": fan_id, "preset_mode": "natural"}, blocking=True
    )
    assert hass.states.get(fan_id).attributes["preset_mode"] == "natural"
    calls.clear()

    await hass.services.async_call("fan", "turn_on", {"entity_id": fan_id}, blocking=True)
    await hass.async_block_till_done()

    assert actions_sent(calls) == ["fan_speed_2"]
    assert hass.states.get(fan_id).attributes["preset_mode"] == "normal"


# --- A preset asked for while the fan was stopped ------------------------------


async def test_a_deferred_preset_is_pressed_when_a_speed_starts_the_fan(
    hass: HomeAssistant,
) -> None:
    """`set_percentage` starts the fan as surely as `turn_on` does.

    It is what the bundled card's speed segments and the more-info slider call, so
    a preset deferred until "the fan is running" has to be honoured here too.
    """
    _entry, calls = await setup_relative(hass, natural_control="dedicated")
    fan_id = one_id(hass, "fan")
    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": fan_id, "preset_mode": "natural"}, blocking=True
    )
    assert actions_sent(calls) == [], "the key is deaf while the fan is stopped"

    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 67}, blocking=True
    )
    await hass.async_block_till_done()

    assert actions_sent(calls) == ["fan_speed_2", "fan_natural"]
    assert hass.states.get(fan_id).attributes["preset_mode"] == "natural"


async def test_a_deferred_preset_does_not_outlive_a_start_from_the_remote(
    hass: HomeAssistant,
) -> None:
    """Started from the physical remote, the fan is in `normal` and stays there.

    The deferred press used to stay armed behind a state that already read
    `normal`, and went on the air at the next `turn_on` -- hours later, unasked.
    """
    _entry, calls = await setup_relative(hass, natural_control="dedicated")
    fan_id = one_id(hass, "fan")
    await hass.services.async_call(
        "fan", "set_preset_mode", {"entity_id": fan_id, "preset_mode": "natural"}, blocking=True
    )
    await fire_rf(hass, "r_s2")
    assert hass.states.get(fan_id).attributes["preset_mode"] == "normal"

    await hass.services.async_call("fan", "turn_off", {"entity_id": fan_id}, blocking=True)
    calls.clear()
    await hass.services.async_call("fan", "turn_on", {"entity_id": fan_id}, blocking=True)
    await hass.async_block_till_done()

    assert "fan_natural" not in actions_sent(calls)
    assert hass.states.get(fan_id).attributes["preset_mode"] == "normal"


# --- The brightness resynchronisation and a walk in flight ---------------------


async def test_resync_cancels_a_brightness_walk_in_flight(
    hass: HomeAssistant, monkeypatch
) -> None:
    """The resynchronisation is a move on the brightness axis like any other.

    It used to press its way down beside a walk still climbing, then declare the
    bottom reached while the abandoned walk went on pressing up.
    """
    entry, calls = await setup_relative(hass)
    light_id = one_id(hass, "light")
    await hass.services.async_call("light", "turn_on", {"entity_id": light_id}, blocking=True)
    calls.clear()

    # Freeze the first walk after its first press; every later gap is instant.
    first_step_done = asyncio.Event()
    release = asyncio.Event()

    async def _gated_sleep(delay: float) -> None:
        if not first_step_done.is_set():
            first_step_done.set()
            await release.wait()

    monkeypatch.setattr("custom_components.rf_fan.entity.sleep", _gated_sleep)

    climbing = asyncio.create_task(
        hass.services.async_call(
            "light", "turn_on", {"entity_id": light_id, "brightness": 255}, blocking=True
        )
    )
    await asyncio.wait_for(first_step_done.wait(), timeout=5)

    button = id_by_unique_suffix(hass, entry, "button", "_brightness_calibrate")
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)

    release.set()
    await climbing
    await hass.async_block_till_done()

    sent = actions_sent(calls)
    assert sent.count("light_bright_up") == 1, "the abandoned walk must not keep climbing"
    assert sent.count("light_bright_down") == 9
    assert hass.states.get(light_id).attributes["brightness"] == 26  # position 0
