"""Stepped controls: relative colour, relative brightness, per-speed direction.

Requires a Home Assistant environment via phcc (same constraint as
`test_entities.py`: the module skips cleanly where the HA stack is not importable).

These cover the shapes reported on issue #18 by @elmr91 for an Inspire Aruba Plus:
a remote whose colour and brightness keys MOVE the value one notch instead of
setting it, and whose winter/summer switch emits no code at all — it stores the
mode itself and sends a different speed code per direction.

What is being asserted throughout is dead reckoning: the lamp never reports back,
so the only thing the integration can be right about is how many presses it has
counted. Every test therefore checks the frames that went on the air, not just the
resulting state.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.components.fan import DIRECTION_FORWARD, DIRECTION_REVERSE
from homeassistant.components.light import ColorMode
from homeassistant.core import HomeAssistant

from custom_components.rf_fan.const import EVENT_RF_FAN_RECEIVED
from tests.ha_helpers import DEVICE
from tests.ha_helpers import actions_sent as _actions_sent
from tests.ha_helpers import id_by_unique_suffix as _id_by
from tests.ha_helpers import one_id as _one_id
from tests.ha_helpers import setup_full as _setup_full
from tests.ha_helpers import setup_relative as _setup_relative


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom component for all tests in the module."""
    yield


@pytest.fixture
def no_gap(monkeypatch):
    """Record the inter-step gaps without actually waiting on the event loop."""
    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("custom_components.rf_fan.entity.sleep", _fake_sleep)
    return sleeps


async def _light_on(hass: HomeAssistant, light_id: str, calls: list) -> None:
    """Power the lamp and drop the frames that took, so a test starts from clean."""
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id}, blocking=True
    )
    await hass.async_block_till_done()
    calls.clear()


# --- Brightness ---------------------------------------------------------------


async def test_light_declares_brightness_when_the_remote_can_step_it(
    hass: HomeAssistant,
) -> None:
    """A remote with +/- keys gets a real brightness slider."""
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _light_on(hass, light_id, calls)

    attributes = hass.states.get(light_id).attributes
    assert attributes["supported_color_modes"] == [ColorMode.BRIGHTNESS]
    assert attributes["color_mode"] == ColorMode.BRIGHTNESS


async def test_light_without_step_keys_stays_on_off(hass: HomeAssistant) -> None:
    """A slider that cannot move anything is worse than no slider at all.

    The capability is declared from what the remote actually has, not from what the
    light entity could in principle express.
    """
    _entry, calls = await _setup_full(hass)
    light_id = _one_id(hass, "light")
    await _light_on(hass, light_id, calls)

    attributes = hass.states.get(light_id).attributes
    assert attributes["supported_color_modes"] == [ColorMode.ONOFF]
    assert attributes.get("brightness") is None


async def test_brightness_walks_up_one_press_per_step(
    hass: HomeAssistant, no_gap: list
) -> None:
    """Ten modelled positions, so 255 is nine presses up from the bottom one."""
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _light_on(hass, light_id, calls)

    # Position is unknown on a fresh entity, so it is dead-reckoned from the
    # bottom: target position 9 (full) is nine presses away.
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id, "brightness": 255}, blocking=True
    )
    await hass.async_block_till_done()

    ups = [c for c in calls if c.get("action") == "light_bright_up"]
    assert len(ups) == 9
    assert not [c for c in calls if c.get("action") == "light_bright_down"]
    # Each step keeps the full repeat_count: a step is absolute, not a flip.
    assert all(c["repeat_count"] == 2 for c in ups)
    assert len(no_gap) == 8, "one gap between each pair of presses, none after the last"
    assert hass.states.get(light_id).attributes["brightness"] == 255


async def test_brightness_walks_back_down_the_short_way(
    hass: HomeAssistant, no_gap: list
) -> None:
    """A range clamps, so the direction is just the sign of the delta."""
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _light_on(hass, light_id, calls)

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id, "brightness": 255}, blocking=True
    )
    await hass.async_block_till_done()
    calls.clear()

    # Position 9 -> roughly half: 255*5/10 = 128 rounds to position 4, five down.
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id, "brightness": 128}, blocking=True
    )
    await hass.async_block_till_done()

    assert len([c for c in calls if c.get("action") == "light_bright_down"]) == 5
    assert not [c for c in calls if c.get("action") == "light_bright_up"]


async def test_brightness_emits_nothing_when_already_at_the_target(
    hass: HomeAssistant, no_gap: list
) -> None:
    """Re-sending the same brightness must not creep the assumed position."""
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _light_on(hass, light_id, calls)

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id, "brightness": 255}, blocking=True
    )
    await hass.async_block_till_done()
    calls.clear()

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id, "brightness": 255}, blocking=True
    )
    await hass.async_block_till_done()

    assert not [c for c in calls if c.get("action", "").startswith("light_bright")]
    assert hass.states.get(light_id).attributes["brightness"] == 255


async def test_brightness_follows_the_physical_remote(hass: HomeAssistant) -> None:
    """A press on the remote's own +/- keys is a known delta, so it is tracked.

    This is where a stepping remote beats a cycling one: the integration does not
    need to recognise an absolute code, only to count a direction.

    The starting position is DECLARED rather than walked to, deliberately: walking
    would put `light_bright_up` on the air and open the anti-echo window on that
    exact code, so the simulated remote press would be discarded as our own echo —
    correctly, but it would test the echo guard instead of the tracking.
    """
    entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _light_on(hass, light_id, calls)

    select_id = _id_by(hass, entry, "select", "_brightness_position")
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": "5"}, blocking=True
    )
    await hass.async_block_till_done()
    before = hass.states.get(light_id).attributes["brightness"]

    # A press Home Assistant did not make, sniffed by the gateway.
    hass.bus.async_fire(
        EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": "r_bu", "action": "sniff"}
    )
    await hass.async_block_till_done()
    assert hass.states.get(light_id).attributes["brightness"] > before

    # And back down again: the assumed position moves both ways.
    hass.bus.async_fire(
        EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": "r_bd", "action": "sniff"}
    )
    await hass.async_block_till_done()
    assert hass.states.get(light_id).attributes["brightness"] == before


async def test_brightness_resync_button_walks_to_the_bottom(
    hass: HomeAssistant, no_gap: list
) -> None:
    """N-1 presses reach the stop from anywhere; the extra ones do nothing there.

    The button emits, unlike the colour calibration button beside it: a range has an
    end stop, so the position can be established from physical fact rather than
    declared.
    """
    entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _light_on(hass, light_id, calls)

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id, "brightness": 255}, blocking=True
    )
    await hass.async_block_till_done()
    calls.clear()

    button_id = _id_by(hass, entry, "button", "_brightness_calibrate")
    await hass.services.async_call(
        "button", "press", {"entity_id": button_id}, blocking=True
    )
    await hass.async_block_till_done()

    downs = [c for c in calls if c.get("action") == "light_bright_down"]
    assert len(downs) == 9, "LIGHT_LEVEL_STEPS - 1 presses reach the bottom"
    assert hass.states.get(light_id).attributes["brightness"] == 26  # position 0


async def test_brightness_position_select_declares_without_emitting(
    hass: HomeAssistant,
) -> None:
    """The silent way back from a drift: say where the lamp is, touch nothing."""
    entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _light_on(hass, light_id, calls)

    select_id = _id_by(hass, entry, "select", "_brightness_position")
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": "7"}, blocking=True
    )
    await hass.async_block_till_done()

    assert not calls, "declaring a position must not put anything on the air"
    assert hass.states.get(select_id).state == "7"
    # The light entity reads the same assumed position: 7th of 10 steps.
    assert hass.states.get(light_id).attributes["brightness"] == 178


# --- Colour -------------------------------------------------------------------


async def test_colour_relative_can_walk_backwards(
    hass: HomeAssistant, no_gap: list
) -> None:
    """Two keys mean the walk has a reverse gear: Neutre(1) -> Chaud(0) is ONE press.

    A cycling remote needs two presses for the same move, because the only key it
    has goes forwards and it has to come round.

    The old name said "the short way ROUND", and the old text claimed 0 -> 2 was one
    press. That was true while a relative walk wrapped, and it stopped being true
    when the ends became stops — @elmr91 measured that his lamp does not roll over
    (#18). Going 0 -> 2 is now two presses up; what two keys still buy is the ability
    to go DOWN, which is what this test actually exercises.
    """
    entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _light_on(hass, light_id, calls)

    select_id = _id_by(hass, entry, "select", "_color_temp")
    # The OFF->ON transition bumped the assumed position to 1 (Neutre).
    assert hass.states.get(select_id).state == "Neutre"

    # Neutre(1) -> Chaud(0) is one step back, not two forward.
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": "Chaud"}, blocking=True
    )
    await hass.async_block_till_done()

    assert _actions_sent(calls) == ["light_kelvin_down"]
    assert hass.states.get(select_id).state == "Chaud"


async def test_colour_relative_goes_up_when_that_is_shorter(
    hass: HomeAssistant, no_gap: list
) -> None:
    """Neutre(1) -> Froid(2) is one step forward."""
    entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _light_on(hass, light_id, calls)

    select_id = _id_by(hass, entry, "select", "_color_temp")
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": "Froid"}, blocking=True
    )
    await hass.async_block_till_done()

    assert _actions_sent(calls) == ["light_kelvin_up"]


async def test_colour_relative_follows_both_remote_keys(hass: HomeAssistant) -> None:
    """The assumed colour tracks the remote in both directions, not just forwards."""
    entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _light_on(hass, light_id, calls)

    select_id = _id_by(hass, entry, "select", "_color_temp")
    assert hass.states.get(select_id).state == "Neutre"

    hass.bus.async_fire(
        EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": "r_kd", "action": "sniff"}
    )
    await hass.async_block_till_done()
    assert hass.states.get(select_id).state == "Chaud"

    hass.bus.async_fire(
        EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": "r_ku", "action": "sniff"}
    )
    await hass.async_block_till_done()
    assert hass.states.get(select_id).state == "Neutre"


# --- Direction as a dimension of the speed code set ---------------------------


async def test_per_speed_direction_sends_the_forward_code_set_by_default(
    hass: HomeAssistant,
) -> None:
    """An unknown direction sends forward, and that is what makes it known."""
    _entry, calls = await _setup_relative(hass)
    fan_id = _one_id(hass, "fan")

    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 100}, blocking=True
    )
    await hass.async_block_till_done()

    assert _actions_sent(calls) == ["fan_speed_3"]
    assert hass.states.get(fan_id).attributes["direction"] == DIRECTION_FORWARD


async def test_per_speed_direction_is_absolute_not_dead_reckoned(
    hass: HomeAssistant,
) -> None:
    """Setting the direction re-sends the CURRENT speed from the other code set.

    With a single reverse key the best the integration can do from an unknown state
    is flip and hope. Here the code itself carries the direction, so the requested
    direction is the one that ends up on the air.
    """
    _entry, calls = await _setup_relative(hass)
    fan_id = _one_id(hass, "fan")

    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 67}, blocking=True
    )
    await hass.async_block_till_done()
    calls.clear()

    await hass.services.async_call(
        "fan",
        "set_direction",
        {"entity_id": fan_id, "direction": DIRECTION_REVERSE},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert _actions_sent(calls) == ["fan_speed_2_reverse"]
    state = hass.states.get(fan_id)
    assert state.attributes["direction"] == DIRECTION_REVERSE
    # The speed is unchanged: only the code set moved.
    assert state.attributes["percentage"] == 67

    # And a later speed change stays in the reverse set.
    calls.clear()
    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": fan_id, "percentage": 100}, blocking=True
    )
    await hass.async_block_till_done()
    assert _actions_sent(calls) == ["fan_speed_3_reverse"]


async def test_per_speed_direction_while_off_emits_nothing_but_is_remembered(
    hass: HomeAssistant,
) -> None:
    """There is no direction key to press, so an off fan simply records the choice.

    Recording it is not cosmetic: it is what makes the NEXT speed code the right one.
    """
    _entry, calls = await _setup_relative(hass)
    fan_id = _one_id(hass, "fan")

    await hass.services.async_call(
        "fan",
        "set_direction",
        {"entity_id": fan_id, "direction": DIRECTION_REVERSE},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert not calls, "no key exists to press while the fan is off"

    await hass.services.async_call(
        "fan", "turn_on", {"entity_id": fan_id, "percentage": 33}, blocking=True
    )
    await hass.async_block_till_done()
    assert _actions_sent(calls) == ["fan_speed_1_reverse"]


async def test_per_speed_direction_follows_a_reverse_code_from_the_remote(
    hass: HomeAssistant,
) -> None:
    """One sniffed frame carries the speed AND the direction."""
    _entry, _calls = await _setup_relative(hass)
    fan_id = _one_id(hass, "fan")

    hass.bus.async_fire(
        EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": "r_s2r", "action": "sniff"}
    )
    await hass.async_block_till_done()

    state = hass.states.get(fan_id)
    assert state.state == "on"
    assert state.attributes["percentage"] == 67
    assert state.attributes["direction"] == DIRECTION_REVERSE

    # And a forward code takes it back, again without any toggle to interpret.
    hass.bus.async_fire(
        EVENT_RF_FAN_RECEIVED, {"device": DEVICE, "code": "r_s1", "action": "sniff"}
    )
    await hass.async_block_till_done()
    assert hass.states.get(fan_id).attributes["direction"] == DIRECTION_FORWARD


# --- Two walks at once --------------------------------------------------------


async def test_a_second_move_cancels_the_first_and_resumes_from_the_air(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Restart semantics: the running walk is dropped, the new one starts from truth.

    A nine-step walk takes several seconds. Move the slider again during it and two
    walks interleave, leaving the assumed position wrong — the bug the colour select
    has carried since 1.0, harmless with three colours and routine with ten
    brightness levels.

    What makes the restart correct is that the abandoned walk has already recorded
    every frame it actually put on the air, so the replacement plans from where the
    lamp IS, not from where the first walk intended to end up.
    """
    _entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _light_on(hass, light_id, calls)

    # Freeze the first walk between its steps until the test lets it go.
    first_step_done = asyncio.Event()
    release = asyncio.Event()

    async def _gated_sleep(delay: float) -> None:
        first_step_done.set()
        await release.wait()

    monkeypatch.setattr("custom_components.rf_fan.entity.sleep", _gated_sleep)

    # Walk towards full brightness: nine presses up, paused after the first.
    climbing = asyncio.create_task(
        hass.services.async_call(
            "light", "turn_on", {"entity_id": light_id, "brightness": 255}, blocking=True
        )
    )
    await asyncio.wait_for(first_step_done.wait(), timeout=5)
    assert len([c for c in calls if c.get("action") == "light_bright_up"]) == 1

    # Second move while the first is still in flight: one press up happened, so the
    # lamp sits at position 1 and the bottom is exactly one press DOWN from there.
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id, "brightness": 26}, blocking=True
    )
    await hass.async_block_till_done()

    release.set()
    await climbing
    await hass.async_block_till_done()

    ups = [c for c in calls if c.get("action") == "light_bright_up"]
    downs = [c for c in calls if c.get("action") == "light_bright_down"]
    assert len(ups) == 1, "the abandoned walk must not keep climbing"
    assert len(downs) == 1, "one press back down, planned from where the lamp actually was"
    assert hass.states.get(light_id).attributes["brightness"] == 26


async def test_walks_on_different_axes_do_not_cancel_each_other(
    hass: HomeAssistant, no_gap: list
) -> None:
    """Colour and brightness are separate keys on the remote, so they are separate walks.

    Cancelling per config entry rather than per axis would make a colour change
    silently truncate a brightness change that happened to overlap it.
    """
    entry, calls = await _setup_relative(hass)
    light_id = _one_id(hass, "light")
    await _light_on(hass, light_id, calls)

    select_id = _id_by(hass, entry, "select", "_color_temp")
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light_id, "brightness": 255}, blocking=True
    )
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": "Chaud"}, blocking=True
    )
    await hass.async_block_till_done()

    assert len([c for c in calls if c.get("action") == "light_bright_up"]) == 9
    assert len([c for c in calls if c.get("action") == "light_kelvin_down"]) == 1
    assert hass.states.get(light_id).attributes["brightness"] == 255
    assert hass.states.get(select_id).state == "Chaud"
